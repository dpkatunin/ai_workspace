# ai_workspace

База знаний 1С + RAG-агент для внедренца-аналитика.

**Репозиторий:** `github.com/dpkatunin/ai_workspace`

---

## Что это

Агент, который:

- **«достаёт»** — отвечает на вопросы по внедрению (консультации, стратегия, чек-листы, кросс-вопросы);
- **«кладит»** — принимает новые материалы (PDF, TXT, папки), оценивает, классифицирует, встраивает в базу.

**Пользователь:** внедренец 1С с 25-летним стажем, новичок в ИИ/данных.

---

## Текущий статус

| Аспект | Состояние |
|:---|:---|
| Архитектура | ✅ 26 ADR, 17 спецификаций (M1–M17) |
| Universal-слой | ✅ 34 шаблона, методология, стандарты |
| Код | 🟡 MVP: `tools/gen_mapping.py` (116 строк) |
| Пилот | 🟡 1 проект (`01_projects/duiko/`) — первый прогон |

Проектирование остановлено. Цикл «пилот → проблемы → исправление → пилот» не сходился. Переход к MVP.

---

## Быстрый старт

См. **`MVP_QUICKSTART.md`** — 6 шагов + 9 критериев проверки.

```bash
pip install -r tools/requirements.txt
export DEEPSEEK_API_KEY=sk-...
python tools/gen_mapping.py duiko --dry-run   # проверка
python tools/gen_mapping.py duiko             # реальный прогон
```

Результат: `01_projects/duiko/01_design/mapping.md`

---

## Структура

```
ai_workspace/
├── _meta/                    # таксономия, реестр конфигураций, спецификации
│   ├── config_registry.yaml  # 6 конфигураций 1С с merge_name
│   ├── taxonomy.yaml         # 3 оси: config / type / concept
│   └── specs/                # M1–M17, ROLES, DECISIONS, OPEN_ISSUES
│
├── _universal/               # универсальный слой
│   ├── templates/            # 34 шаблона (mapping, gap, roadmap и т.д.)
│   ├── stages/ roles/ artifacts/
│   ├── standards/ questions/ competencies/
│   └── registries/
│
├── 00_knowledge_base/        # KB — переиспользуемые знания (48 файлов УНФ)
│
├── 01_projects/              # проекты внедрений
│   └── duiko/                # пилот
│       ├── meta.yaml
│       ├── 00_input.md
│       └── 01_design/        # сюда пишется mapping.md
│
└── tools/                    # MVP-скрипты
    ├── gen_mapping.py
    ├── requirements.txt
    └── README.md
```

---

## Архитектура (кратко)

### Три оси

| Ось ↕▾ | Значения ↕▾ | Зачем ↕▾ |
|---|---|---|
| −**config** | `unf`, `erp`, `zup`, `bp`, `ka`, `universal` | Отделить УНФ от ERP |
| −**type** | `methodology`, `reference`, `objects`, `practical`, `case`, `artifact` | Отделить теорию от практики |
| −**level** | `kb`, `project` | Отделить общее от клиентского |
⚙

**Плюс `concept`** — семантический тег для кросс-поиска (`warehouse`, `production`, `taxes`).

### Два индекса

- **KB** (`00_knowledge_base/`) — переиспользуемые знания.
- **Projects** (`01_projects/{project_id}/`) — артефакты внедрений.

### Три класса задач

| Класс ↕▾ | Механизм ↕▾ | Что делает ↕▾ |
|---|---|---|
| −Поиск | M7-full | Найти существующее |
| −Загрузка | M11 | Положить новое |
| −Генерация | M13 | Создать новое |
⚙

---

## MVP — что входит и что нет

**Входит:**

- `tools/gen_mapping.py` — 116 строк Python.
- `meta.yaml` + `00_input.md` + шаблон → LLM → `mapping.md`.
- Один проект (`duiko`), один артефакт (`mapping.md`).

**Не входит (осознанно):**

- RAG (сначала — проверка: справится ли LLM без KB).
- `gap.md`, `roadmap.md`.
- Валидация результата (уровни 1–3).
- Retry, fallback, streaming.
- Тесты (проверка руками, на реальном клиенте).

---

## Что почитать

| Файл ↕▾ | Что внутри ↕▾ |
|---|---|
| −`MVP_QUICKSTART.md` | Как запустить MVP за 6 шагов |
| −`_meta/specs/HANDOFF.md` | Контекст проекта для нового чата |
| −`_meta/specs/MVP_PLAN.md` | План из 4 шагов (1–3 закрыты, 4 в работе) |
| −`_meta/specs/OPEN_ISSUES.md` | 32 проблемы (13 критичных) |
| −`_meta/specs/DECISIONS.md` | 26 ADR |
| −`_meta/specs/_PATCHES_STEPS_1_4.md` | Патчи к M7-full, M9, M13 |
⚙

---

## Принципы (после пилотов)

1. **«Достаточно хорошо» + реальная проверка** лучше, чем «идеально» + пилоты на бумаге.
2. **Не итерировать промпт в MVP.** Один прогон — один вывод. Плохо — в `OPEN_ISSUES.md`, не в код.
3. **Не добавлять механизмы.** Только M1, M7-full, M13.
4. **Один реальный клиент** — не синтетика.

</BDS:create_file>

<BDS:create_file fileName="INSTALL_IN_EXISTING_REPO.md">

```markdown
# Как наложить выгрузку на существующий репозиторий

> **Важно:** этот архив содержит **только новые файлы** (шаг 1–4 плана MVP).
> Существующие файлы (M1–M17, 34 шаблона, 48 KB-файлов) — **не входят**.
> Их у вас уже есть в локальном репозитории. Этот документ — как их совместить.

---

## Что в архиве (NEW)

.env.example                              [NEW]
.gitignore                                [NEW]
README.md                                 [NEW]
MVP_QUICKSTART.md                         [NEW]
INSTALL_IN_EXISTING_REPO.md               [NEW] ← этот файл
_meta/config_registry.yaml                [NEW, обновление]
_meta/specs/_PATCHES_STEPS_1_4.md         [NEW]
_universal/templates/mapping.example.md   [NEW]
01_projects/duiko/meta.yaml               [NEW]
01_projects/duiko/00_input.md             [NEW]
01_projects/duiko/01_design/.gitkeep      [NEW]
tools/gen_mapping.py                      [NEW]
tools/requirements.txt                    [NEW]
tools/README.md                           [NEW]

```

## Чего в архиве НЕТ (у вас уже есть)

```

_meta/taxonomy.yaml                       [EXISTS]
_meta/CONTENT_INVENTORY.md                [EXISTS]
_meta/PROJECT_SUMMARY.md                  [EXISTS]
_meta/specs/M1_addressing.md              [EXISTS]
_meta/specs/M2_links.md                   [EXISTS]
_meta/specs/M2_addendum.md                [EXISTS]
_meta/specs/M3_versions.md                [EXISTS]
_meta/specs/M4-M6_ingestion.md            [EXISTS]
_meta/specs/M4-M6_addendum.md             [EXISTS]
_meta/specs/M7_partial_contradictions.md  [EXISTS]
_meta/specs/M7_full_routing.md            [EXISTS] ← применить патч v3
_meta/specs/M9_project_structure.md       [EXISTS] ← применить патч v2
_meta/specs/M10_project_kb_links.md       [EXISTS]
_meta/specs/M11_incoming_flow.md          [EXISTS]
_meta/specs/M12_release_notes.md          [EXISTS]
_meta/specs/M13_generation.md             [EXISTS] ← применить патч v4.1
_meta/specs/M14_quality_assurance.md      [EXISTS]
_meta/specs/M15_quick_capture.md          [EXISTS]
_meta/specs/M16_cross_project.md          [EXISTS]
_meta/specs/M17_portfolio.md              [EXISTS]
_meta/specs/ROLES.md                      [EXISTS]
_meta/specs/DECISIONS.md                  [EXISTS]
_meta/specs/OPEN_ISSUES.md                [EXISTS]
_meta/specs/MVP_PLAN.md                   [EXISTS]
_meta/specs/00_README.md                  [EXISTS]
_universal/templates/mapping.md           [EXISTS] ← рабочий шаблон, НЕ перезаписывать
_universal/templates/gap.md               [EXISTS]
_universal/templates/roadmap.md           [EXISTS]
_universal/templates/... (ещё 31)         [EXISTS]
_universal/stages/ roles/ artifacts/ ...  [EXISTS]
00_knowledge_base/ (48 файлов УНФ)        [EXISTS]
HANDOFF.md                                [EXISTS]

```

---

## Порядок наложения

### Шаг 1. Скопировать новые файлы

Из распакованного архива скопировать всё в корень `ai_workspace/`, **кроме** этого файла (`INSTALL_IN_EXISTING_REPO.md` — можно тоже скопировать, для истории).

**Конфликты:** только один — `_meta/config_registry.yaml`. Он перезапишется. Старый файл — сохраните в `config_registry.yaml.bak` на всякий случай.

### Шаг 2. Применить патчи к спецификациям

Открыть `_meta/specs/_PATCHES_STEPS_1_4.md`. Применить три патча вручную:

#### 2.1. `M7_full_routing.md` → v3

- **Раздел 2.1:** заменить/добавить описание 8-го типа.
- **Раздел 4:** добавить строку в таблицу выбора индекса + текст после таблицы.
- **Раздел 5:** добавить блок «Фильтр `config`».

#### 2.2. `M9_project_structure.md` → v2

- **Новый раздел «Несколько конфигураций»:** вставить после раздела про `meta.yaml`, перед разделом про этапы.

#### 2.3. `M13_generation.md` → v4.1

- **Раздел 3.11:** добавить абзац про несколько конфигураций.

**Проверка после патчей:**
```bash
grep -n "фильтр по .config" _meta/specs/M7_full_routing.md
grep -n "Несколько конфигураций" _meta/specs/M9_project_structure.md
grep -n "Несколько конфигураций" _meta/specs/M13_generation.md
```

Все три — должны найти совпадения.

### Шаг 3. Проверить, что `mapping.md` не перезаписан

```
ls -la _universal/templates/mapping.md
# → файл должен существовать и быть НЕ пустым
```

Если случайно перезаписан — восстановите из git:

```
git checkout HEAD -- _universal/templates/mapping.md
```

### Шаг 4. Проверить структуру

```
tree -L 2 -a ai_workspace/
```

Должно быть:

```
ai_workspace/
├── .env.example
├── .gitignore
├── HANDOFF.md
├── INSTALL_IN_EXISTING_REPO.md
├── MVP_QUICKSTART.md
├── README.md
├── _meta/
│   ├── config_registry.yaml
│   ├── taxonomy.yaml
│   ├── ...
│   └── specs/
│       ├── _PATCHES_STEPS_1_4.md
│       ├── M1_addressing.md
│       ├── ...
├── _universal/
│   ├── templates/
│   │   ├── mapping.md
│   │   ├── mapping.example.md
│   │   └── ...
│   └── ...
├── 00_knowledge_base/
│   └── ...
├── 01_projects/
│   └── duiko/
│       ├── meta.yaml
│       ├── 00_input.md
│       └── 01_design/
│           └── .gitkeep
└── tools/
    ├── gen_mapping.py
    ├── requirements.txt
    └── README.md
```

### Шаг 5. Проверить, что MVP запускается

```
pip install -r tools/requirements.txt
python tools/gen_mapping.py duiko --dry-run
```

Должно вывести:

```
DRY-RUN: промпт сохранён в .../01_projects/duiko/01_design/_prompt.txt
Длина промпта: N символов
```

Если что-то не так — проверьте:

- `DEEPSEEK_API_KEY` не нужен для `--dry-run`.
- `pyyaml` установлен (`pip show pyyaml`).
- `_universal/templates/mapping.md` существует.

### Шаг 6. Реальный прогон

```
export DEEPSEEK_API_KEY=sk-...
python tools/gen_mapping.py duiko
```

Результат: `01_projects/duiko/01_design/mapping.md`

### Шаг 7. Коммит

```
git add .
git commit -m "MVP: шаги 1-4 (M7-full v3, M9 v2, config_registry, gen_mapping.py)"
git push
```

---

## Откат (если что-то пошло не так)

```
git checkout HEAD -- _meta/config_registry.yaml
git checkout HEAD -- _meta/specs/M7_full_routing.md
git checkout HEAD -- _meta/specs/M9_project_structure.md
git checkout HEAD -- _meta/specs/M13_generation.md
rm -rf 01_projects/duiko/ tools/ MVP_QUICKSTART.md
```

Затем — заново по шагам.

---

## Что проверить после наложения (сводка)

| № ↕▾ | Что ↕▾ | Где ↕▾ |
|---|---|---|
| −1 | `config_registry.yaml` — 6 конфигураций, все 5 полей | `cat _meta/config_registry.yaml` |
| −2 | Патчи применены к M7-full, M9, M13 | `grep` по трём файлам |
| −3 | `mapping.md` — не перезаписан | `git status` |
| −4 | `mapping.example.md` — новый файл | `ls _universal/templates/` |
| −5 | `duiko` — meta.yaml + 00_input.md | `ls 01_projects/duiko/` |
| −6 | `gen_mapping.py` — 116 строк | `wc -l tools/gen_mapping.py` |
| −7 | `--dry-run` работает без API-ключа | `python tools/gen_mapping.py duiko --dry-run` |
⚙

---

## Принцип: один источник истины

**Спецификации (M1–M17)** остаются в `_meta/specs/`. Патчи — не «вторая версия спеки», а «список правок». Если патч применён — спеку можно коммитить как v3/v2/v4.1. Файл `_PATCHES_STEPS_1_4.md` можно оставить как историю (в `_meta/specs/_archive/`), или удалить после применения.

Я бы оставил в `_archive/` — через полгода будет видно, что менялось и почему.

</BDS:create_file>

<BDS:create_file fileName=".env.example">

```bash
# API-ключ DeepSeek. Скопируйте в .env и заполните.
# Не коммитить .env в git.
DEEPSEEK_API_KEY=sk-your-key-here

