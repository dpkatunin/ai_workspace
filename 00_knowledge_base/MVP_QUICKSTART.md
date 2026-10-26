# MVP Quickstart

> **Что это:** минимальный сценарий проверки «справится ли LLM с заполнением шаблона по описанию бизнеса». 116 строк Python, без RAG, без проверок.
>
> **Что НЕ входит:** RAG, gap.md, roadmap.md, валидация результата, UX. Осознанно.

---

## Что должно быть на месте

| Файл | Что это |
|:---|:---|
| `_meta/config_registry.yaml` | Реестр конфигураций (unf, erp, zup, bp, ka, universal) |
| `_meta/specs/_PATCHES_STEPS_1_4.md` | Патчи к M7-full, M9, M13 |
| `_universal/templates/mapping.md` | Ваш шаблон (34 шаблона уже есть в репо) |
| `_universal/templates/mapping.example.md` | Пример-скелет (только для сверки) |
| `01_projects/duiko/meta.yaml` | Проект: client, project_name, config |
| `01_projects/duiko/00_input.md` | Описание бизнеса |
| `tools/gen_mapping.py` | Скрипт |
| `tools/requirements.txt` | Зависимости |

---

## Шаги

### 1. Установка

```bash
pip install -r tools/requirements.txt
export DEEPSEEK_API_KEY=sk-...     # или из .env
```

### 2. Dry-run

```
python tools/gen_mapping.py duiko --dry-run
```

**Проверьте `01_projects/duiko/01_design/_prompt.txt`:**

- `{{CONFIG_NAME}}` заменён на «УНФ 3.0 + ЗУП 3.1»
- Остальные `{{X}}` — на месте (это сигнал LLM)
- Шаблон и input.md — в промпте целиком

### 3. Реальный прогон

```
python tools/gen_mapping.py duiko
```

**Создаётся:** `01_projects/duiko/01_design/mapping.md`

### 4. Проверка (9 критериев)

См. `tools/README.md`, раздел «Что проверить после прогона».

**Критерий приёмки:** ≥ 8 из 9.

### 5. Сравнение с ручным результатом

Ручной `mapping.md` — от вас. Оценка совпадения — оценочно, > 80% по смыслу.

### 6. Вердикт

- **Приемлемо** — зафиксировать как baseline, двигаться к расширению KB.
- **Не приемлемо** — записать в `_meta/specs/OPEN_ISSUES.md`, не итерировать промпт в MVP.

---

## Что НЕ делать

| Не делать ↕▾ | Почему ↕▾ |
|---|---|
| −Не итерировать промпт в MVP | Один прогон — один вывод. Иначе — возврат в цикл «пилот → проблемы → исправление» |
| −Не добавлять RAG | Сначала — проверка, справится ли LLM без KB |
| −Не добавлять gap.md / roadmap.md | Один артефакт. Проверяем принцип, а не объём |
| −Не добавлять retry / fallback LLM | Один вызов. Упал — видим ошибку |
| −Не добавлять тесты | MVP проверяется руками, на реальном клиенте |
| −Не нормализовать дубликаты в config | Ошибка лучше, чем тихое исправление |
⚙

---

## Структура репозитория (что добавлено MVP)

```
ai_workspace/
├── .env.example                         [NEW]
├── .gitignore                           [NEW]
├── MVP_QUICKSTART.md                    [NEW] ← этот файл
├── README.md                            [NEW]
├── INSTALL_IN_EXISTING_REPO.md          [NEW]
├── _meta/
│   ├── config_registry.yaml             [NEW, обновление]
│   └── specs/
│       └── _PATCHES_STEPS_1_4.md        [NEW]
├── _universal/
│   └── templates/
│       └── mapping.example.md           [NEW] ← скелет; ваш mapping.md — отдельно
├── 01_projects/
│   └── duiko/
│       ├── meta.yaml                    [NEW]
│       ├── 00_input.md                  [NEW]
│       └── 01_design/
│           └── .gitkeep                 [NEW]
└── tools/
    ├── gen_mapping.py                   [NEW]
    ├── requirements.txt                 [NEW]
    └── README.md                        [NEW]
```

---

## Что осталось из плана 4 шагов

| Шаг ↕▾ | Статус ↕▾ |
|---|---|
| −1. M7-full v3 — фильтр `config` в 8-м типе | ✅ патч в `_PATCHES_STEPS_1_4.md` |
| −2. M9 v2 — «Несколько конфигураций» | ✅ патч в `_PATCHES_STEPS_1_4.md` |
| −3. `config_registry.yaml` — `merge_name` | ✅ полный файл |
| −4. MVP — 116 строк Python, 1 артефакт, 1 клиент | ✅ скрипт + пример duiko |
⚙

**Проектирование закрыто. Дальше — реальный прогон.**

</BDS:create_file>

<BDS:create_file fileName="_meta/config_registry.yaml">

```yaml
# Реестр конфигураций 1С.
# Используется:
#   - M7-full v3 (фильтр по config в 8-м типе запроса)
#   - M9 v2 (резолв {{CONFIG_NAME}} для проектов с несколькими конфигурациями)
#   - M13 (генерация артефактов)
#
# Правила:
#   - id: уникальный идентификатор (латиница, нижний регистр); используется в meta.yaml и frontmatter
#   - short: компактное имя для UI (метки, фильтры)
#   - full: полное наименование (tooltips, справка)
#   - merge_name: имя для {{CONFIG_NAME}} в генерируемых документах (обязательно)
#   - version: версия конфигурации (входит в merge_name, отдельно — для справки)
#
# Валидация:
#   - Все пять полей обязательны (поле должно присутствовать).
#   - Поле version может быть пустой строкой "" (например, для universal).
#   - Отсутствие поля — ошибка валидации. Пустая строка — допустима.
#   - Отсутствие merge_name — ошибка (не fallback на short).
#   - Конфигурация, на которую ссылается meta.yaml, должна присутствовать здесь.
#     Иначе — ошибка: «Конфигурация {id} не найдена в config_registry.yaml».

configs:
  - id: unf
    short: "УНФ"
    full: "1С:Управление нашей фирмой"
    version: "3.0"
    merge_name: "УНФ 3.0"

  - id: erp
    short: "ERP"
    full: "1С:ERP Управление предприятием"
    version: "2.5"
    merge_name: "ERP 2.5"

  - id: zup
    short: "ЗУП"
    full: "1С:Зарплата и управление персоналом"
    version: "3.1"
    merge_name: "ЗУП 3.1"

  - id: bp
    short: "БП"
    full: "1С:Бухгалтерия предприятия"
    version: "3.0"
    merge_name: "БП 3.0"

  - id: ka
    short: "КА"
    full: "1С:Комплексная автоматизация"
    version: "2.5"
    merge_name: "КА 2.5"

  - id: universal
    short: "Универсал"
    full: "Универсальные материалы (не привязаны к конфигурации)"
    version: ""
    merge_name: "Универсал"

