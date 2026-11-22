"""Понятные ошибки LLM и преобразование исключений SDK."""

from __future__ import annotations

import re

_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


class LLMError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: str = "error",
        status: int | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retryable = retryable


def scrub(text: str, limit: int = 300) -> str:
    """Убирает ключи и лишнюю длину из технического текста."""
    clean = _KEY_PATTERN.sub("sk-***", text or "")
    clean = " ".join(clean.split())
    return clean[:limit]


def map_sdk_error(exc: Exception, *, provider_title: str, model: str) -> LLMError:
    """Превращает ошибку SDK в сообщение, понятное пользователю."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    name = type(exc).__name__.lower()
    detail = scrub(str(exc))

    if status == 401:
        return LLMError(
            f"{provider_title}: ключ не принят. Проверьте ключ в .env.",
            kind="auth",
            status=401,
        )
    if status == 402:
        return LLMError(
            f"{provider_title}: на балансе недостаточно средств. Пополните баланс.",
            kind="balance",
            status=402,
        )
    if status == 403:
        return LLMError(
            f"{provider_title}: доступ запрещён. Проверьте ограничения ключа и модели.",
            kind="forbidden",
            status=403,
        )
    if status == 404:
        return LLMError(
            f"{provider_title}: модель «{model}» не найдена. Проверьте имя модели в .env.",
            kind="model_not_found",
            status=404,
        )
    if status == 429:
        return LLMError(
            f"{provider_title}: слишком много запросов. Подождите и повторите.",
            kind="rate_limit",
            status=429,
            retryable=True,
        )
    if status is not None and 500 <= status < 600:
        return LLMError(
            f"{provider_title}: сервис временно недоступен ({status}). Повторите позже.",
            kind="server",
            status=status,
            retryable=True,
        )
    if "timeout" in name or "timed out" in detail.lower():
        return LLMError(
            f"{provider_title}: превышено время ожидания ответа. Повторите запрос.",
            kind="timeout",
            retryable=True,
        )
    if "connection" in name or "connect" in name:
        return LLMError(
            f"{provider_title}: нет связи с API. Проверьте интернет и адрес.",
            kind="network",
            retryable=True,
        )
    if status == 400:
        return LLMError(
            f"{provider_title}: запрос отклонён. Проверьте имя модели и параметры. "
            f"Детали: {detail}",
            kind="bad_request",
            status=400,
        )
    return LLMError(
        f"{provider_title}: ошибка запроса ({type(exc).__name__}). Детали: {detail}",
        kind="error",
        status=status,
    )
