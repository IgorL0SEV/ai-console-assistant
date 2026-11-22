"""Настройки приложения и пресеты провайдеров.

Один и тот же CLI умеет работать с несколькими LLM-клиентами:
ProxyAPI (агрегатор), Anthropic напрямую, OpenAI напрямую и OpenRouter.
Провайдер выбирается переменной ``LLM_PROVIDER`` или аргументом ``--provider``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
MODES = ("normal", "thinking")
EFFORT_LEVELS = ("minimal", "low", "medium", "high")


class ConfigError(RuntimeError):
    """Настройки заполнены неверно — пользователю нужно объяснить, что поправить."""


@dataclass(frozen=True)
class ProviderPreset:
    key: str
    title: str
    key_env: str
    normal_model: str
    thinking_model: str
    description: str
    openai_base_url: str | None = None
    anthropic_base_url: str | None = None


PRESETS: dict[str, ProviderPreset] = {
    "proxyapi": ProviderPreset(
        key="proxyapi",
        title="ProxyAPI",
        key_env="PROXYAPI_KEY",
        normal_model="openai/gpt-5-mini",
        thinking_model="anthropic/claude-sonnet-4-5",
        description="один ключ к OpenAI, Anthropic, DeepSeek и другим моделям",
        openai_base_url="https://api.proxyapi.ru/v1",
        anthropic_base_url="https://api.proxyapi.ru",
    ),
    "anthropic": ProviderPreset(
        key="anthropic",
        title="Anthropic (напрямую)",
        key_env="ANTHROPIC_API_KEY",
        normal_model="claude-haiku-4-5",
        thinking_model="claude-sonnet-4-5",
        description="прямой доступ к Claude через api.anthropic.com",
        anthropic_base_url="https://api.anthropic.com",
    ),
    "openai": ProviderPreset(
        key="openai",
        title="OpenAI (напрямую)",
        key_env="OPENAI_API_KEY",
        normal_model="gpt-5-mini",
        thinking_model="gpt-5",
        description="прямой доступ к моделям OpenAI через api.openai.com",
        openai_base_url="https://api.openai.com/v1",
    ),
    "openrouter": ProviderPreset(
        key="openrouter",
        title="OpenRouter",
        key_env="OPENROUTER_API_KEY",
        normal_model="openai/gpt-5-mini",
        thinking_model="anthropic/claude-sonnet-4-5",
        description="агрегатор OpenRouter с сотнями моделей",
        openai_base_url="https://openrouter.ai/api/v1",
    ),
}


@dataclass(frozen=True)
class Settings:
    provider: str
    provider_title: str
    provider_description: str
    api_key: str
    key_env: str
    normal_model: str
    thinking_model: str
    default_mode: str
    reasoning_budget: int
    max_tokens: int
    normal_max_tokens: int
    normal_reasoning_effort: str
    system_prompt: str
    timeout: float
    max_retries: int
    max_history_messages: int
    history_file: Path
    log_file: Path
    data_dir: Path
    openai_base_url: str | None
    anthropic_base_url: str | None
    project_root: Path

    def model_for(self, mode: str) -> str:
        return self.thinking_model if mode == "thinking" else self.normal_model


def _read_str(value: str | None) -> str:
    return (value or "").strip()


def _read_int(value: str | None, default: int, *, name: str, minimum: int = 1) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом, получено: {value!r}") from exc
    if number < minimum:
        raise ConfigError(f"{name} должен быть не меньше {minimum}")
    return number


def _read_float(value: str | None, default: float, *, name: str) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        number = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть числом, получено: {value!r}") from exc
    if number <= 0:
        raise ConfigError(f"{name} должен быть положительным")
    return number


def _normalize_provider(value: str | None, override: str | None = None) -> str:
    provider = (override or value or "proxyapi").strip().lower()
    aliases = {
        "proxy": "proxyapi",
        "proxy-api": "proxyapi",
        "openai_compatible": "proxyapi",
        "claude": "anthropic",
        "openai-direct": "openai",
        "open-router": "openrouter",
    }
    provider = aliases.get(provider, provider)
    if provider not in PRESETS:
        allowed = ", ".join(PRESETS)
        raise ConfigError(f"Неизвестный провайдер: {provider!r}. Допустимые: {allowed}")
    return provider


def _mask_placeholder(value: str) -> str:
    upper = value.upper()
    if not value or "ВАШ" in upper or "YOUR_" in upper or upper.startswith("SK-..."):
        return ""
    return value


def load_settings(
    env_file: str | Path | None = None,
    *,
    provider_override: str | None = None,
) -> Settings:
    """Читает .env и переменные окружения. Ключ проверяется отдельно.

    Значения из файла .env имеют приоритет над окружением. Адреса API
    берутся только из .env или пресета: в окружении могут быть чужие
    переменные вроде ANTHROPIC_BASE_URL от других инструментов.
    """
    env_path = Path(env_file) if env_file else ROOT / ".env"
    file_values = dotenv_values(env_path) if env_path.exists() else {}

    def value(name: str) -> str | None:
        if name in file_values:
            return file_values.get(name)
        return os.getenv(name)

    provider = _normalize_provider(value("LLM_PROVIDER"), provider_override)
    preset = PRESETS[provider]

    key = _mask_placeholder(_read_str(value(preset.key_env)))
    normal_model = _read_str(value("NORMAL_MODEL")) or preset.normal_model
    thinking_model = _read_str(value("THINKING_MODEL")) or preset.thinking_model

    default_mode = _read_str(value("DEFAULT_MODE")).lower() or "thinking"
    if default_mode not in MODES:
        raise ConfigError(f"DEFAULT_MODE должен быть normal или thinking, получено: {default_mode!r}")

    reasoning_budget = _read_int(
        value("REASONING_BUDGET"), 1500, name="REASONING_BUDGET", minimum=1024
    )
    max_tokens = _read_int(value("MAX_TOKENS"), 4096, name="MAX_TOKENS", minimum=256)
    normal_max_tokens = _read_int(
        value("NORMAL_MAX_TOKENS"), 2048, name="NORMAL_MAX_TOKENS", minimum=1
    )
    if provider in {"proxyapi", "anthropic"} and max_tokens <= reasoning_budget:
        raise ConfigError(
            "MAX_TOKENS должен быть больше REASONING_BUDGET: "
            f"сейчас {max_tokens} <= {reasoning_budget}"
        )

    effort = _read_str(value("NORMAL_REASONING_EFFORT")).lower() or "medium"
    if effort not in EFFORT_LEVELS:
        raise ConfigError(
            f"NORMAL_REASONING_EFFORT должен быть одним из {', '.join(EFFORT_LEVELS)}"
        )

    history_file = Path(value("HISTORY_FILE") or "data/history.json")
    if not history_file.is_absolute():
        history_file = ROOT / history_file
    log_file = Path(value("LOG_FILE") or "data/assistant.log")
    if not log_file.is_absolute():
        log_file = ROOT / log_file

    # Только .env или пресет: в окружении могут быть чужие ANTHROPIC_BASE_URL.
    openai_base_url = _read_str(file_values.get("OPENAI_BASE_URL")) or preset.openai_base_url
    anthropic_base_url = _read_str(file_values.get("ANTHROPIC_BASE_URL")) or preset.anthropic_base_url

    return Settings(
        provider=provider,
        provider_title=preset.title,
        provider_description=preset.description,
        api_key=key,
        key_env=preset.key_env,
        normal_model=normal_model,
        thinking_model=thinking_model,
        default_mode=default_mode,
        reasoning_budget=reasoning_budget,
        max_tokens=max_tokens,
        normal_max_tokens=normal_max_tokens,
        normal_reasoning_effort=effort,
        system_prompt=_read_str(value("SYSTEM_PROMPT"))
        or "Вы полезный ассистент. Отвечайте на русском языке.",
        timeout=_read_float(value("REQUEST_TIMEOUT"), 90.0, name="REQUEST_TIMEOUT"),
        max_retries=_read_int(value("MAX_RETRIES"), 1, name="MAX_RETRIES", minimum=0),
        max_history_messages=_read_int(
            value("MAX_HISTORY_MESSAGES"), 40, name="MAX_HISTORY_MESSAGES", minimum=2
        ),
        history_file=history_file,
        log_file=log_file,
        data_dir=history_file.parent,
        openai_base_url=openai_base_url,
        anthropic_base_url=anthropic_base_url,
        project_root=ROOT,
    )


def require_key(settings: Settings) -> str:
    if not settings.api_key:
        raise ConfigError(
            f"Не задан {settings.key_env} для провайдера «{settings.provider_title}». "
            "Создайте ключ и добавьте его в .env."
        )
    return settings.api_key
