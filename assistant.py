"""Консольный AI-ассистент.

Запуск:
    python assistant.py
    python assistant.py --mode normal
    python assistant.py --provider anthropic --mode thinking
    python assistant.py --once "Привет"
    python assistant.py --check
    python assistant.py --demo
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from config import (
    MODES,
    PRESETS,
    ConfigError,
    Settings,
    load_settings,
    require_key,
)
from conversation import Conversation, ConversationError
from errors import LLMError
from providers import Reply, build_provider, list_models
from ui import (
    ask_user,
    choose_mode,
    console,
    print_banner,
    print_error,
    print_history,
    print_help,
    print_info,
    print_reply,
    print_status,
    print_warning,
)

VERSION = "1.0.0"
log = logging.getLogger(__name__)


@dataclass
class CommandResult:
    handled: bool
    exit: bool = False
    mode: str | None = None


def _close_assistant_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_assistant_handler", False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # noqa: BLE001 — закрытие не должно ломать запуск
                pass


def shutdown_logging() -> None:
    _close_assistant_handlers()


def setup_logging(settings: Settings) -> None:
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    _close_assistant_handlers()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler._assistant_handler = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    console_handler._assistant_handler = True  # type: ignore[attr-defined]
    root.addHandler(console_handler)


def load_history(settings: Settings) -> Conversation:
    try:
        conversation = Conversation.load(settings.history_file)
    except ConversationError as exc:
        print_warning(f"{exc}. Начинаю с пустой историей.")
        return Conversation()
    if conversation.messages:
        print_info(
            f"Загружена история: {len(conversation.messages)} сообщений "
            f"({conversation.turns} реплик пользователя)."
        )
    return conversation


def send_message(
    provider,
    conversation: Conversation,
    settings: Settings,
    mode: str,
    text: str,
) -> tuple[Reply, int]:
    history_limit = max(2, settings.max_history_messages - 1)
    messages = conversation.api_messages(history_limit)
    messages.append({"role": "user", "content": text})
    reply = provider.complete(messages, settings.system_prompt)

    conversation.add_user(text)
    conversation.add_assistant(
        reply.text,
        mode=mode,
        thinking=reply.thinking,
        usage=reply.usage,
    )
    dropped = conversation.trim(settings.max_history_messages)
    conversation.save(settings.history_file)
    return reply, dropped


def handle_command(
    text: str,
    conversation: Conversation,
    settings: Settings,
    mode: str,
) -> CommandResult:
    command = text.strip().lower()
    if not command.startswith("/"):
        if command in {"exit", "quit", "выход"}:
            return CommandResult(handled=True, exit=True)
        return CommandResult(handled=False)

    if command in {"/exit", "/quit"}:
        return CommandResult(handled=True, exit=True)
    if command in {"/help", "/?"}:
        print_help()
        return CommandResult(handled=True)
    if command == "/history":
        print_history(conversation)
        return CommandResult(handled=True)
    if command == "/clear":
        conversation.clear()
        conversation.save(settings.history_file)
        print_info("История очищена.")
        return CommandResult(handled=True)
    if command == "/status":
        print_status(settings, mode, len(conversation))
        return CommandResult(handled=True)
    if command == "/mode":
        return CommandResult(handled=True, mode=choose_mode(settings))
    if command == "/normal":
        return CommandResult(handled=True, mode="normal")
    if command == "/thinking":
        return CommandResult(handled=True, mode="thinking")
    print_warning(f"Неизвестная команда: {command}. Справка — /help.")
    return CommandResult(handled=True)


def resolve_mode(requested: str | None, settings: Settings, interactive: bool) -> str:
    if requested:
        return requested
    if interactive and sys.stdin.isatty():
        return choose_mode(settings)
    return settings.default_mode


def run_check(settings: Settings) -> int:
    print_status(settings, settings.default_mode, 0)
    try:
        require_key(settings)
        models = list_models(settings)
    except ConfigError as exc:
        print_error(exc)
        return 2
    except LLMError as exc:
        print_error(exc)
        return 1 if exc.kind in {"auth", "balance", "forbidden", "network"} else 2

    print_info(f"API ответил, доступно моделей: {len(models)}")
    checks = [("обычная", settings.normal_model), ("думающая", settings.thinking_model)]
    for label, model in checks:
        found = any(item == model or model in item for item in models)
        console.print(
            f"  {label}: [green]{model}[/green] — "
            + ("[green]найдена[/green]" if found else "[yellow]нет в списке[/yellow]")
        )
    return 0


def run_once(settings: Settings, mode: str, text: str, use_history: bool) -> int:
    try:
        provider = build_provider(settings, mode)
    except LLMError as exc:
        print_error(exc)
        return 1
    conversation = load_history(settings) if use_history else Conversation()
    try:
        reply, _ = send_message(provider, conversation, settings, mode, text)
    except LLMError as exc:
        print_error(exc)
        return 1
    print_reply(reply, mode)
    return 0


def interactive(settings: Settings, mode: str, use_history: bool) -> int:
    try:
        provider = build_provider(settings, mode)
    except LLMError as exc:
        print_error(exc)
        return 1
    conversation = load_history(settings) if use_history else Conversation()
    conversation.trim(settings.max_history_messages)
    print_banner(settings, mode, len(conversation))

    while True:
        text = ask_user()
        if not text:
            continue

        result = handle_command(text, conversation, settings, mode)
        if result.exit:
            break
        if result.handled:
            if result.mode and result.mode != mode:
                try:
                    new_provider = build_provider(settings, result.mode)
                except LLMError as exc:
                    print_error(exc)
                    continue
                mode = result.mode
                provider = new_provider
                print_info(
                    f"Режим переключён: {mode} · модель {settings.model_for(mode)}"
                )
            continue

        try:
            with console.status("[dim]Модель думает…[/dim]", spinner="dots"):
                reply, dropped = send_message(provider, conversation, settings, mode, text)
        except LLMError as exc:
            print_error(exc)
            continue

        print_reply(reply, mode)
        if dropped:
            log.info("Контекст обрезан на %s сообщений", dropped)

    print_history(conversation)
    conversation.save(settings.history_file)
    print_info("История сохранена. До встречи.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Консольный AI-ассистент с разными LLM-провайдерами"
    )
    parser.add_argument(
        "--provider",
        choices=sorted(PRESETS),
        help="провайдер (по умолчанию из LLM_PROVIDER или proxyapi)",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        help="режим: normal или thinking",
    )
    parser.add_argument(
        "--once",
        metavar="ТЕКСТ",
        help="отправить один запрос и выйти",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="проверить ключ и список моделей, не тратя токены",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="офлайн-демонстрация без ключа и сети",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="не загружать прошлую историю",
    )
    parser.add_argument(
        "--clear-history",
        action="store_true",
        help="очистить историю перед запуском",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(provider_override=args.provider)
    except ConfigError as exc:
        console.print(f"[red]Ошибка настроек:[/red] {exc}")
        return 2

    setup_logging(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        from demo import run_demo

        return run_demo(settings)

    if args.clear_history:
        Conversation().save(settings.history_file)
        print_info("История очищена.")

    if args.check:
        return run_check(settings)

    try:
        require_key(settings)
    except ConfigError as exc:
        print_error(exc)
        print_info("Подсказка: запустите python assistant.py --demo для демонстрации без ключа.")
        return 2

    mode = resolve_mode(args.mode, settings, interactive=not args.once)
    log.info(
        "Старт: provider=%s mode=%s model=%s",
        settings.provider,
        mode,
        settings.model_for(mode),
    )

    if args.once:
        return run_once(settings, mode, args.once, use_history=not args.no_history)

    try:
        return interactive(settings, mode, use_history=not args.no_history)
    except KeyboardInterrupt:
        console.print("\n[dim]Остановлено пользователем.[/dim]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
