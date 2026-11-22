# План проекта VPd06 — AI API

## Цель

Консольный ассистент через ProxyAPI: диалог с контекстом, два режима
(обычная модель и Claude с reasoning), история, ошибки и понятные логи.
Дополнительно — ветки-пресеты под Anthropic, OpenAI и OpenRouter.

## Шаги

| # | Шаг | Статус |
|---|---|---|
| 1 | Каркас проекта, venv, `.env.example`, `.gitignore`, зависимости | ✅ |
| 2 | `config.py`: провайдеры, ключи, модели, режим, бюджет reasoning, таймауты | ✅ |
| 3 | `conversation.py`: история, обрезка парами, сохранение и загрузка JSON | ✅ |
| 4 | `providers.py`: OpenAI-совместимый адаптер и Anthropic Messages | ✅ |
| 5 | ProxyAPI: обычная модель `openai/gpt-5-mini` | ✅ |
| 6 | ProxyAPI: Claude `anthropic/claude-sonnet-4-5` с `thinking.budget_tokens=1500` | ✅ |
| 7 | Прямые адаптеры Anthropic, OpenAI, OpenRouter | ✅ |
| 8 | `assistant.py`: цикл, `/mode`, `/normal`, `/thinking`, `/history`, `/clear`, `exit` | ✅ |
| 9 | `--once`, `--check`, `--demo`, `--no-history`, `--clear-history` | ✅ |
| 10 | `ui.py`: панели ответа, размышлений, токенов; `rich` | ✅ |
| 11 | Понятные ошибки `401/402/403/404/429/5xx/таймаут/сеть`, маскировка ключа | ✅ |
| 12 | Логи без ключей и промптов | ✅ |
| 13 | 79 тестов без сети: конфиг, история, адаптеры, ошибки, команды | ✅ |
| 14 | Документы: `README`, `CONSPECT`, `PLAN`, `SAMOPROVERKA`, `reference/` | ✅ |
| 15 | Ветки-пресеты `proxyapi`, `anthropic`, `openai`, `openrouter` | ✅ созданы локально |
| 16 | Публикация репозитория `ai-console-assistant` | ⏳ |
| 17 | Живая проверка ProxyAPI (ключ пользователя, баланс) | ⏳ |

## Предусловия

- Python 3.10+; проверено на 3.12.
- Аккаунт ProxyAPI, ключ `sk-...` и ненулевой баланс.
- Доступ в интернет к `api.proxyapi.ru`.

## Runbook

```powershell
git clone https://github.com/IgorL0SEV/ai-console-assistant.git
cd ai-console-assistant
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# заполнить PROXYAPI_KEY
python assistant.py
```

Проверка без ключа:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe assistant.py --demo
```

Проверка ключа:

```powershell
.\venv\Scripts\python.exe assistant.py --check
```

## Критерии приёмки и доказательства

| Критерий | Доказательство |
|---|---|
| Диалог с контекстом | `conversation.py`, тест `test_request_contains_history_and_user` |
| История сохраняется и загружается | тесты `test_save_and_load`, `test_load_missing_file` |
| Два режима | `/normal`, `/thinking`, `build_provider` для proxyapi |
| Reasoning Claude | запрос с `thinking.budget_tokens=1500`, блок `thinking` в ответе |
| Обычная модель через Chat Completions | адаптер `OpenAICompatibleProvider` |
| Конфигурация в `.env` | `config.py`, `.env.example` |
| Ошибки и таймауты | `errors.py`, 10 тестов маппинга |
| Ключ не утекает | `scrub`, `.gitignore`, логи без промптов |
| Тесты | 79 тестов, `OK` |
| Офлайн-демо | `python assistant.py --demo` |
| Живой ProxyAPI | ⏳ нужен ключ и баланс |

## Риски и заметки

- **ProxyAPI платный.** Без баланса `402`; это ожидаемое поведение, а не
  ошибка кода.
- **Модели меняются.** Имена моделей вынесены в `.env`; при `404` проверьте
  каталог провайдера.
- **Reasoning у OpenAI скрыт.** В OpenAI-режиме виден только итог; это
  ограничение провайдера.
- **Anthropic требует `max_tokens > budget_tokens`.** Проверяется в
  `config.py`.
- **Контекст стоит денег.** История обрезается до `MAX_HISTORY_MESSAGES`.
- **Ключ в git.** `.env` в `.gitignore`; перед публикацией — `git ls-files`.
- **Прямые ветки зависят от доступа к api.openai.com/api.anthropic.com.**
  Основная ветка ProxyAPI решает эту проблему.
- **Материалы курса не публикуются.** Теория — своими словами, код — свой.
