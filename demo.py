"""Офлайн-демонстрация: интерфейс и история без ключа и без сети."""

from __future__ import annotations

from config import Settings
from conversation import Conversation
from providers import Reply
from ui import console, print_banner, print_history, print_info, print_reply


class DemoThinkingProvider:
    title = "Демо · Claude"
    model = "anthropic/claude-sonnet-4-5"
    mode = "thinking"

    def complete(self, messages, system):
        last = messages[-1]["content"] if messages else ""
        return Reply(
            text=(
                "Я консольный ассистент. В демо-режиме я отвечаю заготовками, "
                "но в реальном запуске текст приходит из выбранной LLM.\n\n"
                f"Вы написали: «{last}».\n"
                "Контекст сохраняется в списке сообщений и передаётся в каждом запросе."
            ),
            thinking=(
                "Пользователь здоровается и спрашивает, кто я. "
                "Нужно ответить коротко, объяснить режим демо и напомнить, "
                "что реальный ответ придёт из модели."
            ),
            model=self.model,
            usage={"input": 48, "output": 96},
            latency=1.1,
        )


class DemoNormalProvider:
    title = "Демо · GPT"
    model = "openai/gpt-5-mini"
    mode = "normal"

    def complete(self, messages, system):
        return Reply(
            text=(
                "Обычная модель отвечает быстрее и дешевле. "
                "Она подходит для переписывания текста и коротких справок, "
                "а думающая — для задач, где важен разбор шагов."
            ),
            thinking=None,
            model=self.model,
            usage={"input": 22, "output": 41},
            latency=0.4,
        )


def run_demo(settings: Settings) -> int:
    print_banner(settings, "thinking", 0)
    print_info("Офлайн-демо: сеть и ключ не используются. Реальный запуск — python assistant.py.")
    console.print()

    conversation = Conversation()
    thinking = DemoThinkingProvider()
    normal = DemoNormalProvider()

    user_text = "Привет! Кто ты и как сохраняешь контекст?"
    conversation.add_user(user_text)
    console.print(f"[bold cyan]Вы:[/bold cyan] {user_text}")
    reply = thinking.complete(conversation.api_messages(), settings.system_prompt)
    conversation.add_assistant(
        reply.text, mode="thinking", thinking=reply.thinking, usage=reply.usage
    )
    print_reply(reply, "thinking")

    user_text = "А чем обычная модель отличается от думающей?"
    conversation.add_user(user_text)
    console.print(f"[bold cyan]Вы:[/bold cyan] {user_text}")
    reply = normal.complete(conversation.api_messages(), settings.system_prompt)
    conversation.add_assistant(reply.text, mode="normal", usage=reply.usage)
    print_reply(reply, "normal")

    print_history(conversation)
    print_info(
        "В реальном приложении история сохраняется в "
        f"{settings.history_file} и загружается при следующем запуске."
    )
    return 0


if __name__ == "__main__":
    from config import load_settings

    raise SystemExit(run_demo(load_settings()))
