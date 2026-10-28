# tools/ — генерация индексов базы знаний УНФ 3.0

Две утилиты, реализующие **ADR-003** (генерация индексов скриптом):

| Скрипт | Что делает |
|---|---|
| `migrate_synonyms.py` | одноразовая миграция: переносит синонимы из `_meta/by-synonym.md` в YAML-фронтматтер карточек |
| `build_indexes.py` | сборка `_meta/by-synonym.md`, `_meta/by-movement.md`, `kb/unf30/_index.md` из карточек |

## Принципы (ADR-003)

1. **Одна копия знания.** Синонимы живут только в YAML-фронтматтере. Движения — только в H2-секциях `## Движения` / `## Участие в регистрах`. Индексы — производные, генерируются.
2. **Идемпотентность.** Повторный запуск `--apply` даёт побайтово тот же результат; git не шумит.
3. **Валидатор на трёх эталонах.** `_meta/_expected/references.json` — ручной снимок для `doc-realizaciya`, `pit-ceny`, `cat-kontragent`. Скрипт сверяет с текущими карточками и падает при расхождении. Так контракт парсера защищён от дрейфа.
4. **Безопасные режимы.** По умолчанию — `--dry-run`. Запись только по `--apply`. Проверка на CI — `--check`.

## Установка

Требуется Python 3.10+ и PyYAML.

```bash
pip install -r tools/requirements.txt
```

## Процедура миграции (один раз)

```
# 0. Зафиксировать текущее состояние — точка отката
git commit -am "before synonyms migration"

# 1. Что нашлось в _meta/by-synonym.md
python tools/migrate_synonyms.py --inspect

# 2. Посмотреть diff по каждой карточке
python tools/migrate_synonyms.py --dry-run

# 3. Записать
python tools/migrate_synonyms.py --apply

# 4. Сверить: сгенерированный by-synonym.md должен совпасть с ручным
python tools/build_indexes.py --dry-run

# 5. Если diffs пустые или только whitespace/сортировка — применить
python tools/build_indexes.py --apply

# 6. Закоммитить
git commit -am "migrate synonyms to frontmatter; regenerate indexes"
```

Если на шаге 4 diff показывает **потерю синонимов** — значит `migrate_synonyms.py` не всё разобрал в `by-synonym.md`. Посмотрите `--inspect`, поправьте формат в `by-synonym.md` или дайте знать — допилю парсер.

## Регулярная работа

```
# После правки карточек — что изменится
python tools/build_indexes.py --dry-run

# Применить
python tools/build_indexes.py --apply

# Быстрая сводка
python tools/build_indexes.py --inspect

# Подробно по каждой карточке
python tools/build_indexes.py --inspect --verbose

# CI / pre-commit хук
python tools/build_indexes.py --check     # exit 1, если индексы устарели
```

## Эталоны ADR-003

`_meta/_expected/references.json` — ручной снимок для трёх эталонных карточек.

- `registers` — **пишется руками по замыслу ADR-003**, не копируется из текущих карточек. Смысл валидатора — проверить, что парсер собирает именно задуманное, а не «что случайно получилось».
- Пустой массив `[]` = ожидается отсутствие движений (например, `pit-ceny`).
- `"TODO"` в списке = ещё не заполнено; валидатор пропустит карточку с предупреждением.

Пример заполненного:

```
{
  "_comment": "...",
  "doc-realizaciya": {
    "type": "object",
    "status": "verified",
    "registers": ["РегистрНакопления.ТоварыНаСкладах", "РегистрНакопления.Продажи"]
  }
}
```

## Форматы, которые понимает парсер

### Frontmatter карточки

```
---
id: doc-realizaciya
type: object        # object | catalog | mechanism | pitfall
status: verified    # verified | draft
config: unf30
synonyms:           # опционально
  - реализация
  - отгрузка
---
```

### Секции движений

Bullet-список:

```
## Движения
- `РегистрНакопления.ТоварыНаСкладах`
- `РегистрНакопления.Продажи`
```

Или таблица (первая колонка — имя регистра):

```
## Движения
| Регистр | Направление |
|---|---|
| `РегистрНакопления.ТоварыНаСкладах` | Расход |
```

Пустые маркеры (`нет`, `—`, `n/a`, `не движется`, `не участвует`) пропускаются. Markdown-ссылки `[X](url)` → `X`. Бэктики и `**bold**` срезаются.

## Диагностика

- `WARN: duplicate synonym 'X' in cards: [...]` — один синоним у нескольких карточек. Для RAG-навигатора это неоднозначность. Разведите (уточните формулировку) или решите осознанно.
- `REF-ERROR: ...` — расхождение с эталоном ADR-003. Либо карточка испорчена, либо парсер сломан. Смотреть diff выше.
- `WARN: orphan card ids in by-synonym.md` — id в ручном файле, которого нет среди карточек. Удалить или создать карточку.

## Откат

Всё под git. Если `--apply` испортил — `git checkout -- kb/unf30 _meta`. Мигратор пишет только в YAML-фронтматтер и только поле `synonyms`; тело карточки не трогается.

</BDS:create_file>

<BDS:create_file fileName="_meta/_expected/references.json">

```json
{
  "_comment": "Ручные эталоны для валидатора ADR-003. Заполни registers по ЗАМЫСЛУ (не копируй из текущих карточек!). Пустой [] = движений нет. TODO = ещё не заполнено, валидатор пропустит с предупреждением.",
  "doc-realizaciya": {
    "type": "object",
    "status": "verified",
    "registers": ["TODO"]
  },
  "pit-ceny": {
    "type": "pitfall",
    "status": "draft",
    "registers": []
  },
  "cat-kontragent": {
    "type": "catalog",
    "status": "draft",
    "registers": ["TODO"]
  }
}

