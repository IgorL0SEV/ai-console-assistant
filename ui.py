"""Оформление консольного интерфейса через rich."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from config import Settings
from conversation import Conversation, Message
from errors import LLMError
from providers import Reply

console = Console()


def format_usage(usage: dict[str, int], latency: float | None = None) -> str:
    if not usage:
        base = "токены: нет данных"
    else:
        parts = []
        if usage.get("input"):
            parts.append(f"вход {usage['input']}")
        if usage.get("output"):
            parts.append(f"выход {usage['output']}")
        if usage.get("reasoning"):
            parts.append(f"reasoning {usage['reasoning']}")
        if usage.get("cache_read"):
            parts.append(f"кэш {usage['cache_read']}")
        base = "токены: " + " · ".join(parts) if parts else "токены: нет данных"
    if latency is not None:
        base += f" · {latency:.1f} с"
    return base


def print_banner(settings: Settings, mode: str, history_count: int) -> None:
    model = settings.model_for(mode)
    mode_title = "думающая" if mode == "thinking" else "обычная"
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[bold]{settings.provider_title}[/bold] · [cyan]{settings.provider_description}[/cyan]\n"
                f"Режим: [bold]{mode_title}[/bold] ({mode}) · модель [green]{model}[/green]\n"
                f"История: {history_count} сообщений\n\n"
                "[dim]Команды: /help · /mode · /history · /clear · exit[/dim]"
            ),
            title="AI-ассистент",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )


def print_reply(reply: Reply, mode: str) -> None:
    if reply.thinking:
        console.print(
            Panel(
                Text(reply.thinking),
                title="Размышления модели",
                border_style="yellow",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
    body = Markdown(reply.text) if reply.text else Text("(пустой ответ)")
    console.print(
        Panel(
            body,
            title=f"Ассистент · {reply.model}",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )
    console.print(f"[dim]{format_usage(reply.usage, reply.latency)}[/dim]")
    console.print()


def print_error(error: LLMError | Exception) -> None:
    message = str(error)
    console.print(
        Panel(
            Text(message),
            title="Ошибка",
            border_style="red",
            box=box.ROUNDED,
        )
    )


def print_info(message: str) -> None:
    console.print(f"[dim]{message}[/dim]")


def print_warning(message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")


def print_history(conversation: Conversation, limit: int | None = None) -> None:
    messages = conversation.messages[-limit:] if limit else conversation.messages
    console.print()
    console.print(Rule("История диалога"))
    if not messages:
        console.print("[dim]История пуста.[/dim]")
        console.print()
        return
    for message in messages:
        _print_history_message(message)
    console.print(Rule())
    console.print()


def _print_history_message(message: Message) -> None:
    moment = message.created_at[11:16] if len(message.created_at) >= 16 else ""
    if message.role == "user":
        console.print(f"[bold green]Вы[/bold green] [dim]{moment}[/dim]")
        console.print(Text(message.text))
    else:
        tag = " · размышления" if message.thinking else ""
        console.print(f"[bold cyan]Ассистент{tag}[/bold cyan] [dim]{moment}[/dim]")
        console.print(Text(message.text))
    console.print()


def print_help() -> None:
    console.print(
        Panel(
            Text.from_markup(
                "[bold]/help[/bold] — эта справка\n"
                "[bold]/mode[/bold] — выбрать обычную или думающую модель\n"
                "[bold]/normal[/bold], [bold]/thinking[/bold] — переключить режим сразу\n"
                "[bold]/history[/bold] — показать историю диалога\n"
                "[bold]/clear[/bold] — очистить историю\n"
                "[bold]/status[/bold] — провайдер, модели и файлы\n"
                "[bold]exit[/bold] или [bold]/exit[/bold] — выйти и показать историю"
            ),
            title="Команды",
            border_style="blue",
            box=box.ROUNDED,
        )
    )


def print_status(settings: Settings, mode: str, history_count: int) -> None:
    lines = [
        f"Провайдер: [bold]{settings.provider_title}[/bold] ({settings.provider})",
        f"Ключ: {'задан' if settings.api_key else 'не задан'} ({settings.key_env})",
        f"Режим: [bold]{mode}[/bold]",
        f"Модель: [green]{settings.model_for(mode)}[/green]",
        f"Обычная модель: {settings.normal_model}",
        f"Думающая модель: {settings.thinking_model}",
        f"Бюджет reasoning: {settings.reasoning_budget} токенов",
        f"История: {history_count} сообщений · {settings.history_file}",
        f"Таймаут: {settings.timeout:g} с · повторы: {settings.max_retries}",
    ]
    console.print(
        Panel(
            Text.from_markup("\n".join(lines)),
            title="Статус",
            border_style="blue",
            box=box.ROUNDED,
        )
    )


def choose_mode(settings: Settings) -> str:
    console.print("\n[bold]Выберите режим работы:[/bold]")
    console.print(f"  [bold]1[/bold] — обычная модель: {settings.normal_model}")
    console.print(
        f"  [bold]2[/bold] — думающая модель: {settings.thinking_model} "
        f"(reasoning, бюджет {settings.reasoning_budget})"
    )
    default_label = "2" if settings.default_mode == "thinking" else "1"
    while True:
        try:
            answer = console.input(
                f"Режим [1/2] (Enter — {default_label}): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return settings.default_mode
        if not answer:
            return settings.default_mode
        if answer == "1":
            return "normal"
        if answer == "2":
            return "thinking"
        console.print("[yellow]Введите 1, 2 или нажмите Enter.[/yellow]")


def ask_user() -> str:
    try:
        return console.input("[bold cyan]Вы:[/bold cyan] ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return "exit"
