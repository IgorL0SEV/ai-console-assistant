"""История диалога: список сообщений, обрезка контекста и сохранение в JSON."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


class ConversationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Message:
    role: str
    text: str
    mode: str | None = None
    thinking: str | None = None
    usage: dict[str, int] | None = None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at,
        }
        if self.mode:
            data["mode"] = self.mode
        if self.thinking:
            data["thinking"] = self.thinking
        if self.usage:
            data["usage"] = self.usage
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        role = str(data.get("role", ""))
        text = str(data.get("text", ""))
        if role not in {"user", "assistant"} or not text:
            raise ConversationError("Некорректное сообщение в истории")
        usage = data.get("usage")
        if usage is not None and not isinstance(usage, dict):
            usage = None
        return cls(
            role=role,
            text=text,
            mode=data.get("mode"),
            thinking=data.get("thinking"),
            usage=usage,
            created_at=str(data.get("created_at") or _now()),
        )


class Conversation:
    def __init__(self, messages: list[Message] | None = None):
        self.messages: list[Message] = list(messages or [])

    def __len__(self) -> int:
        return len(self.messages)

    @property
    def turns(self) -> int:
        return sum(1 for message in self.messages if message.role == "user")

    def add_user(self, text: str) -> Message:
        text = text.strip()
        if not text:
            raise ValueError("Пустое сообщение")
        message = Message(role="user", text=text)
        self.messages.append(message)
        return message

    def add_assistant(
        self,
        text: str,
        *,
        mode: str,
        thinking: str | None = None,
        usage: dict[str, int] | None = None,
    ) -> Message:
        message = Message(
            role="assistant",
            text=text,
            mode=mode,
            thinking=thinking,
            usage=usage,
        )
        self.messages.append(message)
        return message

    def api_messages(self, max_messages: int | None = None) -> list[dict[str, str]]:
        """Сообщения для API: только роли и текст, без служебных полей."""
        return [
            {"role": message.role, "content": message.text}
            for message in self._tail(max_messages)
        ]

    def _tail(self, max_messages: int | None) -> list[Message]:
        if not max_messages or len(self.messages) <= max_messages:
            return list(self.messages)
        limit = max(2, max_messages - max_messages % 2)
        tail = self.messages[-limit:]
        while tail and tail[0].role != "user":
            tail.pop(0)
        return tail

    def trim(self, max_messages: int) -> int:
        """Оставляет последние пары сообщений. Возвращает число удалённых."""
        before = len(self.messages)
        self.messages = self._tail(max_messages)
        return before - len(self.messages)

    def clear(self) -> None:
        self.messages.clear()

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": _now(),
            "messages": [message.to_dict() for message in self.messages],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> "Conversation":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            raise ConversationError(f"Не удалось прочитать историю: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise ConversationError("Файл истории имеет неожиданный формат")
        messages: list[Message] = []
        for item in payload["messages"]:
            if not isinstance(item, dict):
                continue
            try:
                messages.append(Message.from_dict(item))
            except ConversationError:
                continue
        return cls(messages)

    def export_text(self, limit: int | None = None) -> str:
        messages = self.messages[-limit:] if limit else self.messages
        lines: list[str] = []
        for message in messages:
            if message.role == "user":
                lines.append(f"Вы: {message.text}")
            else:
                tag = " (размышления)" if message.thinking else ""
                lines.append(f"Ассистент{tag}: {message.text}")
        return "\n".join(lines)
