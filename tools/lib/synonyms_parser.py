"""
Парсер _meta/by-synonym.md → список (синоним, card_id).

Рассчитан на «толерантное» чтение ручного файла. Ожидаемые формы:

    | Синоним | Конфиг | id |
    |---|---|---|
    | касса, кассовые документы | unf30 | cat-kassy |

или:

    - **реализация** → `doc-realizaciya`
    - отгрузка — doc-realizaciya

Идентификатор карточки узнаётся по префиксу: doc-*, cat-*, mech-*, pit-*.
Всё, что в строке стоит перед id, разбивается по запятым и очищается от мусора.
"""
from __future__ import annotations

import re

CARD_ID_RE = re.compile(r"\b(doc|cat|mech|pit)-[a-z][a-z0-9-]*\b")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|?$")

_HEADER_WORDS = {
    "синоним", "синонимы", "слово", "термин", "id", "карточка",
    "статус", "название", "псевдоним", "псевдонимы", "unf30",
}

def parse_by_synonym(text: str) -> list[tuple[str, str]]:
    """Вернуть [(synonym, card_id), ...] в порядке появления. Дубли отбрасываются."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        if _TABLE_SEP_RE.match(line):
            continue

        m = CARD_ID_RE.search(line)
        if not m:
            continue

        card_id = m.group(0)
        prefix = line[: m.start()]

        # Извлекаем текст с синонимами, обрабатывая колонки таблицы
        if "|" in prefix:
            # Разбиваем по пайпу, убираем пустые ячейки
            cells = [c.strip() for c in prefix.split("|") if c.strip()]
            # Синонимы обычно в первой непустой ячейке (до колонки с id)
            syns_text = cells[0] if cells else ""
        else:
            syns_text = prefix

        # Разделяем по запятым
        for sr in syns_text.split(","):
            s = sr.strip()
            
            # Удаляем markdown-форматирование и лишние символы
            s = s.replace("**", "").replace("__", "").replace("`", "")
            s = s.strip("«»\"' -—–→|").strip()
            
            if not s:
                continue
            if s.lower() in _HEADER_WORDS:
                continue

            key = (s, card_id)
            if key not in seen:
                seen.add(key)
                pairs.append(key)

    return pairs
