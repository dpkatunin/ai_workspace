"""
Извлечение списков из H2-секций карточки.

Ожидаемый формат секции (`## Движения` / `## Участие в регистрах`):

    ## Движения
    - `РегистрНакопления.ТоварыНаСкладах`
    - `РегистрНакопления.Продажи`

или таблица:

    | Регистр | Направление |
    |---|---|
    | `РегистрНакопления.ТоварыНаСкладах` | Расход |

Парсер терпим к: bullet-спискам, таблицам, «сырым» строкам без маркера.
Заголовки таблицы, разделители, «нет/—/n/a/не движется» — пропускаются.
"""
from __future__ import annotations

import re

# --- H2 ---

_H2_RE = re.compile(r"^##\s+(.+?)\s*$")

def extract_h2(body: str) -> dict[str, str]:
    """Вернуть {имя_секции: текст_секции}. Имена без '##'."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in body.split("\n"):
        m = _H2_RE.match(line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1)
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections

# --- Списки внутри секции ---

_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|?$")
_BULLET_RE = re.compile(r"^[-*+]\s+(.+)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")

_EMPTY_TOKENS = {"нет", "—", "-", "n/a", "na", "не движется", "не участвует", "не используется"}

def extract_items(section_body: str) -> list[str]:
    """Извлечь упорядоченный список уникальных значений из тела H2-секции."""
    if not section_body:
        return []

    lines = section_body.split("\n")
    items: list[str] = []

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue

        # Разделитель markdown-таблицы
        if _TABLE_SEP_RE.match(line):
            continue

        # Bullet (но не строка таблицы, начинающаяся с '|')
        m = _BULLET_RE.match(line)
        if m and not line.startswith("|"):
            item = _clean(m.group(1))
            if item:
                items.append(item)
            continue

        # Строка таблицы
        if line.startswith("|"):
            # Заголовок таблицы — если следующая строка разделитель
            if i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1].strip()):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells:
                item = _clean(cells[0])
                if item:
                    items.append(item)
            continue

        # Сырая строка
        item = _clean(line)
        if item:
            items.append(item)

    return _dedupe(items)

def _clean(text: str) -> str | None:
    # [Текст](url) → Текст
    text = _LINK_RE.sub(r"\1", text)
    text = text.strip().strip("`*_").strip()
    if not text:
        return None
    if text.lower() in _EMPTY_TOKENS:
        return None
    return text

def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def classify_register(name: str) -> tuple[int, str]:
    """Ключ сортировки регистров: накопления → сведения → прочие."""
    if name.startswith("РегистрНакопления"):
        return (0, name)
    if name.startswith("РегистрСведений"):
        return (1, name)
    return (2, name)
