# Справка по ProxyAPI

Документ фиксирует то, что используется в `providers.py`. Проверено по
документации ProxyAPI 22.11.2026; перед изменениями сверяйтесь с сайтом.

## Общее

- Сайт: `https://proxyapi.ru`, кабинет: `https://console.proxyapi.ru`.
- Ключ начинается с `sk-`, создаётся в разделе «Ключи API».
- Оплата в рублях; без баланса запросы возвращают `402`.
- Один ключ работает с моделями OpenAI, Anthropic, DeepSeek, Google и
  других вендоров.

## OpenAI-совместимый API

```http
POST https://api.proxyapi.ru/v1/chat/completions
Authorization: Bearer sk-КЛЮЧ
Content-Type: application/json
```

```json
{
  "model": "openai/gpt-5-mini",
  "messages": [
    {"role": "system", "content": "Отвечай по-русски."},
    {"role": "user", "content": "Привет!"}
  ]
}
```

Ответ — стандартный Chat Completions: `choices[0].message.content`,
`usage.prompt_tokens`, `usage.completion_tokens`.

Для reasoning передаётся `reasoning_effort` со значениями от `minimal` до
`high`. Параметр работает с моделями разных вендоров; ProxyAPI приводит его
к тому виду, который понимает конечный сервис.

Список моделей: `GET https://api.proxyapi.ru/v1/models`.

## Anthropic Messages

```http
POST https://api.proxyapi.ru/v1/messages
X-API-Key: sk-КЛЮЧ
Content-Type: application/json
```

```json
{
  "model": "anthropic/claude-sonnet-4-5",
  "max_tokens": 4096,
  "system": "Отвечай по-русски.",
  "messages": [
    {"role": "user", "content": "Привет!"}
  ],
  "thinking": {"type": "enabled", "budget_tokens": 1500}
}
```

Обязательные поля: `model`, `messages`, `max_tokens`. `max_tokens` должен
быть больше `budget_tokens`.

Ответ:

```json
{
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "thinking", "thinking": "..."},
    {"type": "text", "text": "Привет! Чем помочь?"}
  ],
  "usage": {"input_tokens": 39, "output_tokens": 65}
}
```

Официальный SDK `anthropic` направляется на `https://api.proxyapi.ru`
(без `/v1`): библиотека сама добавляет `/v1/messages`.

## Модели

Идентификатор — `вендор/название`, регистр не важен.

| Модель | ID в ProxyAPI | Особенности |
|---|---|---|
| Claude Sonnet 4.5 | `anthropic/claude-sonnet-4-5` | reasoning, 200K контекст |
| Claude Haiku 4.5 | `anthropic/claude-haiku-4-5` | быстрая, без reasoning в карточке |
| GPT-5 mini | `openai/gpt-5-mini` | недорогая обычная модель |
| Claude Sonnet 5.5 | `anthropic/claude-sonnet-5-5` | новее и дороже |

Полный каталог с ценами: `https://proxyapi.ru/models/browse`.
Цены меняются; в проекте они не зашиты.

## Ошибки

| Код | Смысл | Что делать |
|---|---|---|
| 400 | неверный запрос или параметр | проверить модель и поля |
| 401 | ключ не принят | проверить `PROXYAPI_KEY` |
| 402 | недостаточно средств | пополнить баланс |
| 403 | доступ запрещён | проверить ограничения ключа |
| 404 | модель не найдена | проверить ID модели |
| 429 | превышен лимит | подождать, повторить |
| 502/504 | временная ошибка | повторить позже |

Тело ошибки обычно содержит `detail` или `error.message`; в проекте оно
очищается от ключей и обрезается.

## Прямые провайдеры

| Провайдер | Base URL | Ключ | SDK |
|---|---|---|---|
| ProxyAPI (OpenAI) | `https://api.proxyapi.ru/v1` | `PROXYAPI_KEY` | `openai` |
| ProxyAPI (Anthropic) | `https://api.proxyapi.ru` | `PROXYAPI_KEY` | `anthropic` |
| Anthropic | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | `anthropic` |
| OpenAI | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `openai` |
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `openai` |

Прямые API могут быть недоступны из России без дополнительных средств;
поэтому основной вариант — ProxyAPI.

## Как это встроено в проект

- `OpenAICompatibleProvider` — Chat Completions, `reasoning_effort`,
  OpenRouter `extra_body.reasoning`.
- `AnthropicMessagesProvider` — Messages, `thinking.budget_tokens`.
- `build_provider()` выбирает адаптер по провайдеру и режиму.
- `errors.map_sdk_error()` превращает коды в понятные сообщения.
- `--check` вызывает список моделей и не тратит токены.
