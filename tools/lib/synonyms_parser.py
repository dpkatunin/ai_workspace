"""
Парсер _meta/by-synonym.md → список (синоним, card_id).

Рассчитан на «толерантное» чтение ручного файла. Ожидаемые формы:

    | Синоним | id | Статус |
    |---|---|---|
    | реализация | doc-realizaciya | verified |

или:

    - **реализация** → `doc-realizaciya`
    - отгрузка — doc-realizaciya

Идентификатор карточки узнаётся по префиксу: doc-*, cat-*, mech-*, pit-*.
Всё, что в строке стоит перед id (после срезания маркеров списка/таблицы),
считается синонимом.
"""
from __future__ import annotations

import re

CARD_ID_RE = re.compile(r"\b(doc|cat|mech|pit)-[a-z][a-z0-9-]*\b")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|?$")

_HEADER_WORDS = {
    "синоним", "синонимы", "слово", "термин", "id", "карточка",
    "статус", "название", "псевдоним", "псевдонимы",
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
        # Удаляем markdown-форматирование (жирный шрифт, код)
        prefix = prefix.replace("**", "").replace("__", "").replace("`", "")
        
        # Удаляем с краев пробелы и разделители (палки таблиц, стрелки, тире)
        # Добавлены символы: >, —, –, →, ⇒, :
        prefix = re.sub(r"^[\s\|=\-]+", "", prefix)
        prefix = re.sub(r"[\s\|=\>\-—–→⇒:]+$", "", prefix)
        
        prefix = prefix.strip()

        if not prefix:
            continue
        if prefix.lower() in _HEADER_WORDS:
            continue

        key = (prefix, card_id)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)

    return pairs
