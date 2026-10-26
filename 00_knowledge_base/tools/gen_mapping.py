#!/usr/bin/env python3
"""MVP: генерация mapping.md из meta.yaml + input.md + шаблона.

ОГРАНИЧЕНИЯ MVP (осознанные отступления от M9):
  - input.md лежит в корне проекта, а не в 00_questionnaire/input.md (M9).
    Это упрощение для быстрой проверки. В полной версии — 00_questionnaire/.
  - Нет RAG: KB не подгружается, только шаблон + input.
  - Нет проверок результата, нет gap.md / roadmap.md.
  - Один LLM-вызов, один артефакт.

Запуск:
    export DEEPSEEK_API_KEY=sk-...
    python tools/gen_mapping.py duiko
    python tools/gen_mapping.py duiko --dry-run   # только сохранить промпт
"""
import os
import sys
import re
from pathlib import Path
import yaml
from openai import OpenAI  # DeepSeek совместим с OpenAI SDK

REPO = Path(__file__).resolve().parent.parent
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
MAX_TEMPLATE_CHARS = 100_000  # ~25K токенов, запас до 64K контекста

def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def build_config_name(config_ids: list, registry: dict) -> str:
    """config_registry.yaml → «УНФ 3.0 + ЗУП 3.1» по правилам M9."""
    by_id = {c["id"]: c for c in registry["configs"]}
    parts = []
    for cid in config_ids:
        if cid not in by_id:
            sys.exit(f"ERROR: конфигурация '{cid}' не найдена в config_registry.yaml")
        if not by_id[cid].get("merge_name"):
            sys.exit(f"ERROR: у '{cid}' нет merge_name в config_registry.yaml")
        parts.append(by_id[cid]["merge_name"])
    return " + ".join(parts)

def substitute(template: str, values: dict) -> str:
    """Заменяет {{KEY}} на values[KEY]. Остальные {{...}} остаются — это сигнал LLM."""
    for key, val in values.items():
        template = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", str(val), template)
    return template

def call_llm(prompt: str, api_key: str) -> str:
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE)
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "Ты — внедренец 1С с 25-летним стажем. Пишешь по-русски, конкретно, без воды."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content

def main(project_id: str = "duiko", dry_run: bool = False) -> None:
    project_dir = REPO / "01_projects" / project_id
    if not project_dir.is_dir():
        sys.exit(f"ERROR: проект '{project_id}' не найден: {project_dir}")

    # 1. meta.yaml — поле client (соответствует M9)
    meta = load_yaml(project_dir / "meta.yaml")
    if not meta.get("config"):
        sys.exit("ERROR: поле config обязательно в meta.yaml")

    # 2. input.md (MVP: в корне проекта, не в 00_questionnaire/ по M9)
    input_path = project_dir / "00_input.md"
    if not input_path.exists():
        sys.exit(f"ERROR: файл не найден: {input_path}")
    input_text = input_path.read_text(encoding="utf-8")

    # 3. шаблон
    template_path = REPO / "_universal" / "templates" / "mapping.md"
    if not template_path.exists():
        sys.exit(f"ERROR: шаблон не найден: {template_path}")
    template = template_path.read_text(encoding="utf-8")

    # 4. config_registry
    registry = load_yaml(REPO / "_meta" / "config_registry.yaml")
    config_name = build_config_name(meta["config"], registry)

    # 5. подстановка плейсхолдеров
    values = {
        "CONFIG_NAME": config_name,
        "CLIENT_NAME": meta.get("client", ""),
        "PROJECT_NAME": meta.get("project_name", ""),
        "PROJECT_ID": project_id,
    }
    filled_template = substitute(template, values)

    # 6. проверка размера (до вызова LLM)
    if len(filled_template) > MAX_TEMPLATE_CHARS:
        sys.exit(f"ERROR: шаблон слишком большой ({len(filled_template)} символов > {MAX_TEMPLATE_CHARS})")

    # 7. промпт — явно про плейсхолдеры
    prompt = f"""Заполни шаблон ниже по описанию проекта.

ШАБЛОН:
---
{filled_template}
---

ОПИСАНИЕ ПРОЕКТА (input.md):
---
{input_text}
---

Правила:
- Плейсхолдеры вида {{{{X}}}} — это места для заполнения. Замени каждый {{{{X}}}} на конкретное значение из описания.
- Если данных для плейсхолдера нет — оставь {{{{X}}}} как есть (это сигнал, что данных не хватает; не выдумывай).
- Заполняй только секции шаблона, не добавляй новых.
- Если для секции нет данных — пиши «Не применимо» одной строкой.
- Не выдумывай факты. Используй только то, что есть в описании.
- Сохраняй заголовки и структуру шаблона.
- Верни только итоговый mapping.md, без комментариев вокруг.
"""

    out_dir = project_dir / "01_design"
    out_dir.mkdir(exist_ok=True)

    # 8. сохранение промпта (для разбора результата)
    (out_dir / "_prompt.txt").write_text(prompt, encoding="utf-8")

    # 9. dry-run
    if dry_run:
        print(f"DRY-RUN: промпт сохранён в {out_dir / '_prompt.txt'}")
        print(f"Длина промпта: {len(prompt)} символов")
        return

    # 10. вызов
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        sys.exit("ERROR: установите DEEPSEEK_API_KEY")
    result = call_llm(prompt, api_key)

    # 11. сохранение
    out_path = out_dir / "mapping.md"
    out_path.write_text(result, encoding="utf-8")
    print(f"OK: {out_path}")

if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    main(args[0] if args else "duiko", dry_run=dry)

</BDS:create_file>

<BDS:create_file fileName="tools/requirements.txt">

```
openai>=1.0
pyyaml>=6.0
```

</BDS:create_file>

<BDS:create_file fileName="tools/README.md">

```
# tools/ — MVP-инструменты

## gen_mapping.py

Генерация `mapping.md` из `meta.yaml` + `00_input.md` + шаблона.

**Ограничения (осознанно):**
- Нет RAG.
- Нет проверок.
- Один LLM-вызов, один артефакт.
- `00_input.md` — в корне проекта (MVP-упрощение; по M9 должен быть в `00_questionnaire/`).

## Установка

```bash
pip install -r tools/requirements.txt
export DEEPSEEK_API_KEY=sk-...
```

## Запуск

**Dry-run (посмотреть, что отправляем LLM):**

```
python tools/gen_mapping.py duiko --dry-run
# → _prompt.txt сохранён, LLM не вызывается
```

**Реальный прогон:**

```
python tools/gen_mapping.py duiko
# → 01_projects/duiko/01_design/mapping.md
```

**Другой проект:**

```
python tools/gen_mapping.py other_project
```

## Что проверить после прогона (9 критериев)

| № ↕▾ | Критерий ↕▾ | Как проверить ↕▾ |
|---|---|---|
| −1 | Файл создан в `01_design/mapping.md` | `ls` |
| −2 | Структура шаблона сохранена (все заголовки) | Diff с шаблоном |
| −3 | `{{CONFIG_NAME}}` = «УНФ 3.0 + ЗУП 3.1» | `grep` |
| −4 | `{{CLIENT_NAME}}` = «Дуйко» | `grep` |
| −5 | Нет `{{...}}` или они осознанно оставлены | `grep -E '\{\{[A-Z_]+\}\}'` |
| −6 | Нет «воды» вокруг (нет «Вот ваш документ») | Прочитать первые/последние 3 строки |
| −7 | Секции без данных = «Не применимо» | Просмотреть 2–3 секции |
| −8 | Факты соответствуют `00_input.md` | Сверить с input |
| −9 | Время генерации < 60 сек | Замер |
⚙

**Критерий приёмки MVP:** ≥ 8 из 9 пунктов выполнены.

## Что делать, если результат плохой

**НЕ итерировать промпт в MVP.** Один прогон — один вывод.

Записать в `_meta/specs/OPEN_ISSUES.md` как «M13-XX» и переходить к следующему шагу (расширение KB, RAG). Иначе — возврат в тот же цикл «пилот → проблемы → исправление», от которого ушли.

## Файлы, которые создаются

- `01_projects/{id}/01_design/_prompt.txt` — отправленный промпт (всегда)
- `01_projects/{id}/01_design/mapping.md` — результат (только без `--dry-run`)

