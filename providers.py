"""Адаптеры LLM-клиентов: ProxyAPI, Anthropic, OpenAI и OpenRouter.

CLI не знает, какой SDK используется: он получает объект с методом
``complete(messages, system)`` и печатает результат. Поэтому одну и ту же
программу можно запускать на разных провайдерах и ветках-пресетах.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from config import Settings, require_key
from errors import LLMError, map_sdk_error

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reply:
    text: str
    thinking: str | None
    model: str
    usage: dict[str, int]
    latency: float


class Provider(Protocol):
    title: str
    model: str
    mode: str

    def complete(self, messages: list[dict[str, str]], system: str) -> Reply: ...


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(getattr(item, "text", "") or ""))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "")
    return str(value)


def _openai_usage(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    result = {
        "input": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output": int(getattr(usage, "completion_tokens", 0) or 0),
        "total": int(getattr(usage, "total_tokens", 0) or 0),
    }
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None) if details else None
    if reasoning:
        result["reasoning"] = int(reasoning)
    return {key: value for key, value in result.items() if value}


def _anthropic_usage(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    result = {
        "input": int(getattr(usage, "input_tokens", 0) or 0),
        "output": int(getattr(usage, "output_tokens", 0) or 0),
    }
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    if cache_read:
        result["cache_read"] = cache_read
    if cache_write:
        result["cache_write"] = cache_write
    return {key: value for key, value in result.items() if value}


class OpenAICompatibleProvider:
    """Любой API, совместимый с OpenAI Chat Completions."""

    def __init__(
        self,
        *,
        title: str,
        api_key: str,
        base_url: str | None,
        model: str,
        mode: str,
        max_tokens: int,
        timeout: float,
        max_retries: int,
        max_tokens_param: str = "max_tokens",
        reasoning_style: str | None = None,
        reasoning_effort: str | None = None,
        client: Any | None = None,
    ):
        if not base_url:
            raise LLMError(f"{title}: не задан базовый адрес API")
        self.title = title
        self.model = model
        self.mode = mode
        self.max_tokens = max_tokens
        self.max_tokens_param = max_tokens_param
        self.reasoning_style = reasoning_style
        self.reasoning_effort = reasoning_effort
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
            )
        self.client = client

    def complete(self, messages: list[dict[str, str]], system: str) -> Reply:
        payload: list[dict[str, str]] = []
        if system:
            payload.append({"role": "system", "content": system})
        payload.extend(messages)

        kwargs: dict[str, Any] = {"model": self.model, "messages": payload}
        if self.max_tokens > 0:
            kwargs[self.max_tokens_param] = self.max_tokens
        if self.reasoning_style == "effort" and self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        elif self.reasoning_style == "openrouter" and self.reasoning_effort:
            kwargs["extra_body"] = {"reasoning": {"effort": self.reasoning_effort}}

        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # SDK-исключения разных версий
            raise map_sdk_error(exc, provider_title=self.title, model=self.model) from exc
        latency = time.perf_counter() - started

        try:
            message = response.choices[0].message
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.title}: ответ модели пуст или имеет неожиданный формат") from exc

        text = _as_text(getattr(message, "content", None)).strip()
        thinking = _as_text(
            getattr(message, "reasoning_content", None)
            or getattr(message, "reasoning", None)
        ).strip()
        usage = _openai_usage(getattr(response, "usage", None))

        if not text and not thinking:
            raise LLMError(f"{self.title}: модель вернула пустой ответ")

        log.info(
            "LLM %s model=%s mode=%s latency=%.2fs tokens=%s",
            self.title,
            self.model,
            self.mode,
            latency,
            usage,
        )
        return Reply(
            text=text or "(модель не вернула текст, только размышления)",
            thinking=thinking or None,
            model=self.model,
            usage=usage,
            latency=latency,
        )


class AnthropicMessagesProvider:
    """Anthropic Messages API: обычный ответ или extended thinking."""

    def __init__(
        self,
        *,
        title: str,
        api_key: str,
        base_url: str | None,
        model: str,
        mode: str,
        max_tokens: int,
        timeout: float,
        max_retries: int,
        thinking_budget: int | None = None,
        client: Any | None = None,
    ):
        if not base_url:
            raise LLMError(f"{title}: не задан базовый адрес API")
        self.title = title
        self.model = model
        self.mode = mode
        self.max_tokens = max_tokens
        self.thinking_budget = thinking_budget
        if client is None:
            import anthropic

            client = anthropic.Anthropic(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
            )
        self.client = client

    def complete(self, messages: list[dict[str, str]], system: str) -> Reply:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if self.thinking_budget:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }

        started = time.perf_counter()
        try:
            response = self.client.messages.create(**kwargs)
        except Exception as exc:
            raise map_sdk_error(exc, provider_title=self.title, model=self.model) from exc
        latency = time.perf_counter() - started

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", "")
            if block_type == "thinking":
                value = _as_text(getattr(block, "thinking", None)).strip()
                if value:
                    thinking_parts.append(value)
            elif block_type == "text":
                value = _as_text(getattr(block, "text", None)).strip()
                if value:
                    text_parts.append(value)

        text = "\n".join(text_parts).strip()
        thinking = "\n\n".join(thinking_parts).strip()
        usage = _anthropic_usage(getattr(response, "usage", None))

        if not text:
            raise LLMError(f"{self.title}: модель не вернула текст ответа")

        log.info(
            "LLM %s model=%s mode=%s latency=%.2fs tokens=%s",
            self.title,
            self.model,
            self.mode,
            latency,
            usage,
        )
        return Reply(
            text=text,
            thinking=thinking or None,
            model=self.model,
            usage=usage,
            latency=latency,
        )


def build_provider(settings: Settings, mode: str) -> Provider:
    """Создаёт клиент под выбранного провайдера и режим."""
    if mode not in {"normal", "thinking"}:
        raise LLMError(f"Неизвестный режим: {mode}")
    key = require_key(settings)
    common = dict(
        api_key=key,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
    )

    if settings.provider == "proxyapi":
        if mode == "thinking":
            return AnthropicMessagesProvider(
                title=f"{settings.provider_title} · Claude",
                base_url=settings.anthropic_base_url,
                model=settings.thinking_model,
                mode=mode,
                max_tokens=settings.max_tokens,
                thinking_budget=settings.reasoning_budget,
                **common,
            )
        return OpenAICompatibleProvider(
            title=settings.provider_title,
            base_url=settings.openai_base_url,
            model=settings.normal_model,
            mode=mode,
            max_tokens=settings.normal_max_tokens,
            **common,
        )

    if settings.provider == "anthropic":
        return AnthropicMessagesProvider(
            title=settings.provider_title,
            base_url=settings.anthropic_base_url,
            model=settings.model_for(mode),
            mode=mode,
            max_tokens=settings.max_tokens if mode == "thinking" else settings.normal_max_tokens,
            thinking_budget=settings.reasoning_budget if mode == "thinking" else None,
            **common,
        )

    if settings.provider == "openai":
        return OpenAICompatibleProvider(
            title=settings.provider_title,
            base_url=settings.openai_base_url,
            model=settings.model_for(mode),
            mode=mode,
            max_tokens=settings.max_tokens if mode == "thinking" else settings.normal_max_tokens,
            max_tokens_param="max_completion_tokens",
            reasoning_style="effort" if mode == "thinking" else None,
            reasoning_effort=settings.normal_reasoning_effort,
            **common,
        )

    if settings.provider == "openrouter":
        return OpenAICompatibleProvider(
            title=settings.provider_title,
            base_url=settings.openai_base_url,
            model=settings.model_for(mode),
            mode=mode,
            max_tokens=settings.max_tokens if mode == "thinking" else settings.normal_max_tokens,
            reasoning_style="openrouter" if mode == "thinking" else None,
            reasoning_effort=settings.normal_reasoning_effort,
            **common,
        )

    raise LLMError(f"Провайдер {settings.provider!r} пока не поддержан")


def list_models(settings: Settings) -> list[str]:
    """Список моделей для --check. Не тратит токены."""
    key = require_key(settings)
    try:
        if settings.provider == "anthropic":
            import anthropic

            client = anthropic.Anthropic(
                api_key=key,
                base_url=settings.anthropic_base_url,
                timeout=settings.timeout,
                max_retries=0,
            )
            page = client.models.list()
            return [str(item.id) for item in getattr(page, "data", [])]
        from openai import OpenAI

        client = OpenAI(
            api_key=key,
            base_url=settings.openai_base_url,
            timeout=settings.timeout,
            max_retries=0,
        )
        return [str(item.id) for item in client.models.list().data]
    except Exception as exc:
        raise map_sdk_error(
            exc,
            provider_title=settings.provider_title,
            model=settings.model_for(settings.default_mode),
        ) from exc
