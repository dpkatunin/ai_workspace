# CHAT_HANDOFF — для передачи контекста в новый чат

Скопируй этот файл целиком в начало нового чата с DeepSeek (или другим
ассистентом), чтобы он быстро понял, где мы и что делать дальше.

Обновлён: 2026-11-06 (вечер). Заменяет предыдущую версию.

---

## Что за проект

ИИ-база знаний (RAG) по конфигурации 1С **УНФ 3.0**. Пользователь —
внедренец с 25-летним опытом. Цель: давать проверяемые ответы, не галлюцинировать.

**Главный вывод:** поведение нельзя гарантировать промптом. Правильность
обеспечивается **кодом и структурой данных**.

## Три источника правды (не путать)

| Слой | Что это | MCP-инструменты | Статус |
|---|---|---|---|
| **KB** (`kb/unf30/`) | 43 ручные карточки (`pit-`, `mech-`, `pb-`, `case-`, `cat-`, `doc-`) | `search_kb`, `get_card`, `kb_stats`, `verify_card_facts` | Работает (порт 8000) |
| **STRUCT** (`projects/unf30-kb/struct/data/struct.db`) | SQLite из JSON-выгрузки метаданных | `search_objects`, `get_object`, ... (9 штук) | **Работает (порт 8001)**, 16 909 объектов, ВСЯ конфигурация (56 подсистем) |
| **HELP** (`projects/unf30-kb/help/data/help.db`) | SQLite из справки конфигурации (`Help/ru.html`) | `help_search`, `help_get_article`, `help_get_object_articles`, `help_get_links`, `help_stats` | **Работает (порт 8002)**, 1487 статей |
| **XML-конфигурация** | Выгрузка конфигурации 1С в XML | `search_config`, `read_config_file` | Работает (по контракту /1c) |

## Где что лежит

```

ai_workspace/
├── .kimi-code/mcp.json          # MCP для Kimi Code (struct/help — stdio автозапуск, kb — http:8000)
├── AGENTS.md                    # правила ответов агента по УНФ
├── kb/unf30/                    # KB слой (43 карточки)
├── projects/unf30-kb/
│   ├── PROJECT_STATE.md         # ← актуален, обновлён 2026-11-06
│   ├── CHAT_HANDOFF.md          # ← ты читаешь его
│   ├── KIMI_CODE_ИНСТРУКЦИЯ.md    # ← как задавать вопросы в Kimi Code + 5 тестовых задач
│   ├── struct/                  # STRUCT слой (порт 8001)
│   │   ├── struct_mcp.py        # ✅ MCP-сервер (v2 SDK), 9 инструментов
│   │   ├── tools.md             # описание инструментов
│   │   ├── schema.sql           # схема SQLite
│   │   ├── ingest.py            # заливка JSON → SQLite (пропускает существующие full_name!)
│   │   ├── verify.py            # проверка целостности
│   │   ├── answer_guard.py      # CLI-постпроцессор validate_names (вариант А)
│   │   ├── _common.py           # утилиты
│   │   └── data/struct.db       # ✅ 16 909 объектов, ВСЯ конфигурация (56 подсистем)
│   └── help/                    # HELP слой (порт 8002)
│       ├── ingest_help.py       # заливка Help/ru.html → SQLite
│       ├── verify_help.py       # контроль целостности
│       ├── help_search.py       # CLI-поиск (FTS5)
│       ├── help_mcp.py          # ✅ MCP-сервер, 5 инструментов (каркас = struct_mcp.py)
│       ├── schema.sql
│       └── data/help.db         # ✅ 1487 статей, привязка к объектам 1486/1487
├── tools/mcp_server.py          # KB-сервер (порт 8000)
└── _meta/                       # conventions, design

```

## Ключевые решения (не пересматривать без причины)

1. **STRUCT → SQLite**, не векторную БД. Точный поиск по именам надёжнее семантики.
2. **`Раскрытие` из выгрузки не храним** — граф из `Типы` + `СвойстваОбъекта`.
3. **`СвойстваОбъекта` — в колонки + JSON.** Без `register_kind` модель путает регистры.
4. **ID фактов стабильные:** `obj:Документ.ЗаказПокупателя`, `attr:…`, `move:…`, `link:…`.
5. **Лимит 10–15 КБ на ответ MCP-инструмента.** Большие массивы обрезаются с `truncated`.
6. **Валидатор имён — код.** Все `ПолноеИмя` проверяются по `objects.full_name` через `validate_names`.
7. **`ijson`, не `json.load`.** Файлы полной выгрузки 10–50 МБ.
8. **Подсистема — измерение в `objects`** (`subsystem`, `subsystem_path`). Читается из JSON. При заливке «Закупок» проставится сама.
9. **`config_id` из `СвойстваКонфигурации.Синоним`.** Версия парсится regex, дата — из имени файла.
10. **MCP SDK v2 (mcp 2.3.0):** `transport_security` передаётся в `run()`, а **не** в `MCPServer(...)`. Если передать в конструктор — BDS получит 403 при подключении.

## Состояние STRUCT-базы (2026-11-06, verify.py — полная заливка)

| Метрика | Значение |
|---|---|
| objects | **16 909** (56 подсистем — вся конфигурация УНФ 3.0) |
| attributes | 54 673 |
| attribute_types | 195 710 |
| object_links | 3 627 (незакрытых стало меньше: регистры теперь в базе) |
| movements | 1 602 |
| enum_values | 9 216 |
| tabular_sections | 2 115 |
| config | 1 строка: УНФ 3.0 |

ingest.py пропускает существующие full_name → изменение маппинга полей = чистая
пересборка; дозаливка новых объектов = обычный запуск (rglob обходит вложенные
папки сам). `resolve_links` докрывает ссылки после каждой заливки.

## Состояние HELP-базы (2026-11-06, verify_help.py)

| Метрика | Значение |
|---|---|
| help_articles | **1487** (object 848, form 599, subsystem 39, configuration 1, other 1) |
| привязка к объектам | 1486/1487 |
| help_links | 4166 (object_help 2406 — мост к STRUCT) |
| FTS | в синхроне (1487/1487) |

Ограничение FTS: unicode61 без морфологии — ищем точные формы слов.

**Проверка MCP-серверов пройдена:**
- STRUCT: `get_config_info` → УНФ 3.0; `validate_names` ловит галлюцинации.
- HELP: `initialize` + `tools/list` прошли, все 5 инструментов видны.
- Smoke-тесты verify.py/check_zakupki.py зелёные из-под Kimi Code Desktop.

## Что делать (следующий шаг)

1. **Приёмка контура в Kimi Code:** 5 тестовых задачек из
   `projects/unf30-kb/KIMI_CODE_ИНСТРУКЦИЯ.md`. Настройка: открыть папку
   `ai_workspace` в Kimi Code Desktop → Trust this folder → НОВАЯ сессия →
   `/mcp` (struct-unf30 и help-unf30 должны быть connected — они stdio,
   запускаются сами; unf30-kb — только если запущено его окно на 8000).
2. **Связка STRUCT↔HELP:** 2406 ссылок `help_links.to_object_full_name`
   разобраны; решить — отдельный инструмент или связка `get_object` +
   `help_get_object_articles`.
3. **Мелочи:** опционально: подписать метрику object_links в check_zakupki.py
   как «resolved»; нормализация окончаний для FTS HELP (морфология).

## Окружение

- Windows, PowerShell 5.1
- Python 3.14, `mcp 2.3.0` (SDK v2), `ijson 3.6.0`, `jsonschema`, `pytest`
- MCP-сервер KB: `.venv\Scripts\python.exe tools/mcp_server.py --no-dns-protection` (порт 8000)
- MCP-сервер STRUCT: `.venv\Scripts\python.exe projects/unf30-kb/struct/struct_mcp.py --db projects/unf30-kb/struct/data/struct.db --port 8001`
- MCP-сервер HELP: `.venv\Scripts\python.exe projects/unf30-kb/help/help_mcp.py --db projects/unf30-kb/help/data/help.db --port 8002`
- В BDS подключены: `unf30-kb` (8000), `struct-unf30` (8001)
- Kimi Code Desktop: `.kimi-code/mcp.json` + `AGENTS.md` в корне ai_workspace;
  struct-unf30/help-unf30 — stdio (автозапуск), unf30-kb — http://127.0.0.1:8000/mcp (ручной запуск)
- UTF-8 дисциплина: `chcp 65001` + `python -X utf8`; вместо `python -c` — here-string `$code = @'...'@ | python -X utf8 -`

**Важно про PowerShell:** красный текст в консоли от `py` (например, `CategoryInfo: NotSpecified`, `RemoteException`) — это **не ошибка**. PowerShell так показывает вывод Python в stderr. Смотри на последнюю строку (`INFO: Application startup complete.`) — она и есть результат.

## Правила общения

- Не использовать старые BDS-инструменты для записи файлов без просьбы.
- Не выдумывать имена объектов 1С. Если чего-то нет в фактах — писать «нет данных».
- Объяснять сложные ИИ-термины через аналогии из 1С, базовые понятия 1С — не объяснять.
- Отвечать по-русски.
- Не пересматривать ключевые решения без причины (пункты 1–10 выше).
- При своих вопросах сразу предлагать варианты ответа.
- Инструкции давать подробно, шаг за шагом (опыт пользователя в текущих инструментах небольшой) — чтобы не переспрашивать и не переделывать скрипты.
- Критически обдумывать свои предложения до выдачи: сначала проверить радикально-простое решение (пример: «снести БД и перезалить» вместо долгой инкрементальной диагностики).
- Не закапываться в незначительные вопросы.
- Доставка файлов: только ZIP через `C:\dsh-out` (unzip-watcher.ps1), entry-пути обязаны начинаться с `ai_workspace/`. Коммиты — пользователь через GitHub Desktop.

## Если нужен полный контекст

- **`projects/unf30-kb/PROJECT_STATE.md`** — актуален, обновлён 2026-11-04 (вечер). Приоритет — этот CHAT_HANDOFF.md.
- **`_meta/conventions.md`** — префиксы карточек, критерии верификации
- **`_meta/design/00-START-HERE.md`** — общий дизайн
