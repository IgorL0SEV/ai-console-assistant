# ai-console-assistant — консольный AI-ассистент

Диалоговый помощник в терминале: помнит контекст, сохраняет историю,
переключается между обычной и «думающей» моделью. Один и тот же CLI работает
с несколькими LLM-клиентами, а в репозитории есть ветки-пресеты под каждого
провайдера.

- Основной вариант (сдача): **ProxyAPI**, обычная модель + Claude с reasoning.
- Дополнительно: прямые ветки **Anthropic**, **OpenAI** и **OpenRouter**.
- Python 3.10+ (проверено на 3.12).

## Ветки-пресеты

| Ветка | Провайдер | Ключ | Обычная модель | Думающая модель |
|---|---|---|---|---|
| `main`, `proxyapi` | ProxyAPI | `PROXYAPI_KEY` | `openai/gpt-5-mini` | `anthropic/claude-sonnet-4-5` |
| `anthropic` | Anthropic напрямую | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` | `claude-sonnet-4-5` |
| `openai` | OpenAI напрямую | `OPENAI_API_KEY` | `gpt-5-mini` | `gpt-5` |
| `openrouter` | OpenRouter | `OPENROUTER_API_KEY` | `openai/gpt-5-mini` | `anthropic/claude-sonnet-4-5` |

Каждая ветка — самостоятельное приложение со своим `.env.example`, README и
настройками по умолчанию. Код общий: провайдер выбирается адаптером.

```powershell
git clone https://github.com/IgorL0SEV/ai-console-assistant.git
cd ai-console-assistant
git branch -a
git switch proxyapi    # или anthropic, openai, openrouter
```

Можно остаться на `main` и переключить провайдера переменной
`LLM_PROVIDER` или аргументом `--provider`.

## Что умеет

- ведёт диалог в консоли до команды `exit`;
- передаёт контекст в каждом запросе и не теряет нить разговора;
- сохраняет историю в `data/history.json` и загружает её при следующем запуске;
- переключает режимы `/normal` и `/thinking` без перезапуска;
- в думающем режиме показывает размышления Claude и расход токенов;
- поддерживает ProxyAPI, Anthropic, OpenAI и OpenRouter;
- понятно объясняет ошибки `401`, `402`, `429`, таймауты и недоступность сети;
- пишет технический лог без ключей и полных промптов;
- умеет работать без ключа в режиме `--demo`.

## Быстрый старт

```powershell
git clone https://github.com/IgorL0SEV/ai-console-assistant.git
cd ai-console-assistant
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполните `.env`:

```ini
LLM_PROVIDER=proxyapi
PROXYAPI_KEY=sk-ваш_ключ
NORMAL_MODEL=openai/gpt-5-mini
THINKING_MODEL=anthropic/claude-sonnet-4-5
DEFAULT_MODE=thinking
REASONING_BUDGET=1500
MAX_TOKENS=4096
```

Запуск:

```powershell
python assistant.py
python assistant.py --mode normal
python assistant.py --once "Привет! Кто ты?"
python assistant.py --check
python assistant.py --demo
```

Или в один клик:

```powershell
.\run.cmd
.\run.cmd demo
.\run.cmd check
```

### ProxyAPI

1. Зарегистрируйтесь на `proxyapi.ru` и подтвердите почту.
2. Создайте ключ в разделе «Ключи API» — он начинается с `sk-`.
3. Пополните баланс: запросы списываются по токенам, баланс в рублях.
4. Вставьте ключ в `.env` как `PROXYAPI_KEY`.

Один ключ даёт доступ к моделям OpenAI, Anthropic, DeepSeek и других
вендоров. Базовые адреса уже прописаны в `.env.example`.

## Как задаётся модель

Модель выбирается в два слоя:

1. `LLM_PROVIDER` задаёт пресет провайдера и модели по умолчанию:

   | Провайдер | Обычная | Думающая |
   |---|---|---|
   | `proxyapi` | `openai/gpt-5-mini` | `anthropic/claude-sonnet-4-5` |
   | `anthropic` | `claude-haiku-4-5` | `claude-sonnet-4-5` |
   | `openai` | `gpt-5-mini` | `gpt-5` |
   | `openrouter` | `openai/gpt-5-mini` | `anthropic/claude-sonnet-4-5` |

2. `NORMAL_MODEL` и `THINKING_MODEL` в `.env` — явное переопределение.
   Пустое значение означает «взять из пресета». Это основной способ
   поставить конкретную модель, не меняя код.

Режим `/normal` или `/thinking` решает, какой слот использовать. Выбранное
имя уходит в запрос как `model=...`. Если провайдер отвечает `404`,
проверьте идентификатор в каталоге моделей.

Пример: оставить ProxyAPI, но заменить думающую модель:

```ini
LLM_PROVIDER=proxyapi
THINKING_MODEL=anthropic/claude-sonnet-5-5
```

Проверить, какие модели видит провайдер, можно командой `--check`.

Адреса API берутся из `.env` или пресета провайдера, а не из переменных
окружения: чужая `ANTHROPIC_BASE_URL` не должна уводить запрос на локальный
адрес вместо ProxyAPI.

## Команды

| Команда | Действие |
|---|---|
| `/help` | справка |
| `/mode` | выбрать обычный или думающий режим |
| `/normal` | переключить на обычную модель |
| `/thinking` | переключить на думающую модель |
| `/history` | показать историю диалога |
| `/clear` | очистить историю и файл |
| `/status` | провайдер, модели, бюджет, файлы |
| `exit`, `/exit`, `quit` | выйти и показать историю |

CLI-аргументы: `--provider`, `--mode`, `--once`, `--check`, `--demo`,
`--no-history`, `--clear-history`, `--version`.

## Два режима

**Обычный (`normal`).** Запрос в формате Chat Completions к
OpenAI-совместимому API. В ветке ProxyAPI это `openai/gpt-5-mini`; в прямых
ветках — модель соответствующего провайдера.

**Думающий (`thinking`).** Для ProxyAPI и Anthropic используется нативный
Anthropic Messages с `thinking.budget_tokens` (по умолчанию 1500). Модель
возвращает блок `thinking` и итоговый текст; программа показывает и то, и
другое. Для OpenAI и OpenRouter включается `reasoning_effort`, но ход
рассуждений эти сервисы могут не показывать — это их особенность, а не
ошибка приложения.

## Контекст и история

Модель не хранит диалог между запросами. Программа сама собирает список
сообщений `user` / `assistant`, обрезает его до `MAX_HISTORY_MESSAGES` и
передаёт в каждом запросе. После успешного ответа пара сохраняется в
`data/history.json`; при следующем запуске история загружается. Команда
`/clear` очищает и память, и файл.

## Структура

```text
ai-console-assistant/
├── assistant.py      # CLI: цикл, команды, режимы, --once/--check/--demo
├── providers.py      # адаптеры ProxyAPI, Anthropic, OpenAI, OpenRouter
├── conversation.py   # история, обрезка контекста, JSON
├── config.py         # .env, пресеты провайдеров
├── errors.py         # понятные ошибки SDK
├── ui.py             # вывод через rich
├── demo.py           # офлайн-демонстрация
├── TEST_SCENARIO.md  # сценарий проверки проекта
├── run.cmd           # запуск в один клик
├── tests/            # 80 тестов без сети
├── reference/        # справка по ProxyAPI
├── requirements.txt
├── .env.example
└── README.md
```

## Проверка

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe assistant.py --demo
.\venv\Scripts\python.exe assistant.py --check
```

Тесты не ходят в сеть: SDK-клиенты подменяются фейками, история пишется во
временную папку. `--check` проверяет ключ и список моделей без расхода
токенов.

Пример демо:

```text
┌──────────────────────────── Размышления модели ─────────────────────────────┐
│ Пользователь здоровается и спрашивает, кто я. ...                           │
└─────────────────────────────────────────────────────────────────────────────┘
┌────────────────── Ассистент · anthropic/claude-sonnet-4-5 ──────────────────┐
│ Я консольный ассистент. ...                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
токены: вход 48 · выход 96 · 1.1 с
```

### Живая проверка ProxyAPI

- `--check`: 827 моделей, `openai/gpt-5-mini` и `anthropic/claude-sonnet-4-5` найдены.
- Обычный режим: «Париж», 35 входных / 76 выходных токенов.
- Думающий режим: 17×23 = 391, размышления показаны, 79 / 114 токенов.

## Ошибки

| Ситуация | Сообщение |
|---|---|
| `401` | ключ не принят — проверьте `.env` |
| `402` | недостаточно средств — пополните баланс |
| `403` | доступ запрещён — проверьте ограничения ключа |
| `404` | модель не найдена — проверьте имя модели |
| `429` | слишком много запросов — подождите |
| `502/504` | сервис временно недоступен |
| таймаут | превышено время ожидания |
| сеть | нет связи с API |

Ключи и полные промпты в лог не попадают. В `data/assistant.log` пишутся
провайдер, модель, время ответа и токены.

## Ограничения

- ProxyAPI — платный сервис: без баланса запросы вернут `402`.
- Прямые API OpenAI и Anthropic могут быть недоступны из России без
  дополнительных средств; для этого и существует ветка ProxyAPI.
- Названия моделей меняются. Если модель не найдена, проверьте каталог
  провайдера и обновите `NORMAL_MODEL` / `THINKING_MODEL`.
- Reasoning показывают не все провайдеры; для OpenAI это внутренний процесс.
- История — локальный файл; при удалении `data/history.json` диалог начнётся
  заново.
- Стоимость зависит от модели и длины контекста; думающая модель дороже.

## Безопасность

- `.env` и `data/` исключены из git.
- В репозитории только `.env.example` с плейсхолдерами.
- Ключ не печатается в консоль, лог и сообщения об ошибках.
- Логи содержат модель, время и токены, но не текст запросов.

## Справка

- [Сценарий проверки проекта](TEST_SCENARIO.md)
- [ProxyAPI: адреса, модели, reasoning и ошибки](reference/proxyapi-reference.md)
- [Конспект по AI API](CONSPECT.md)
- [План проекта](PLAN.md)
- [Самопроверка](SAMOPROVERKA.md)
