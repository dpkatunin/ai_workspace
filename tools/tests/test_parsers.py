"""Минимальные тесты парсеров. Запуск: py -m pytest tools/tests/test_parsers.py -v"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.frontmatter import parse, rebuild, split, replace_or_insert_block  # noqa: E402
from lib.sections import classify_register, extract_h2, extract_items  # noqa: E402
from lib.synonyms_parser import parse_by_synonym  # noqa: E402

SAMPLE_CARD = """---
id: doc-realizaciya
type: object
status: verified
config: unf30
---

# Реализация товаров и услуг

## Движения

- `РегистрНакопления.ТоварыНаСкладах`
- `РегистрНакопления.Продажи`

## Примечания

Текст.
"""

def test_split_frontmatter():
    fm, body = split(SAMPLE_CARD)
    assert "id: doc-realizaciya" in fm
    assert body.startswith("\n# Реализация")

def test_parse_frontmatter():
    fm, _ = split(SAMPLE_CARD)
    meta = parse(fm)
    assert meta["id"] == "doc-realizaciya"
    assert meta["type"] == "object"
    assert meta["status"] == "verified"

def test_extract_h2():
    _, body = split(SAMPLE_CARD)
    sections = extract_h2(body)
    assert "Движения" in sections
    assert "Примечания" in sections

def test_extract_items_bullets():
    _, body = split(SAMPLE_CARD)
    sections = extract_h2(body)
    regs = extract_items(sections["Движения"])
    assert regs == ["РегистрНакопления.ТоварыНаСкладах", "РегистрНакопления.Продажи"]

def test_extract_items_table():
    body = """
| Регистр | Направление |
|---|---|
| `РегистрНакопления.ТоварыНаСкладах` | Расход |
| `РегистрСведений.ЦеныНоменклатуры` | — |
"""
    items = extract_items(body)
    assert items == ["РегистрНакопления.ТоварыНаСкладах", "РегистрСведений.ЦеныНоменклатуры"]

def test_extract_items_empty():
    assert extract_items("") == []
    assert extract_items("- нет") == []
    assert extract_items("- —") == []

def test_classify_register():
    assert classify_register("РегистрНакопления.ТоварыНаСкладах")[0] == 0
    assert classify_register("РегистрСведений.ЦеныНоменклатуры")[0] == 1
    assert classify_register("Справочник.Номенклатура")[0] == 2

def test_parse_by_synonym_table():
    text = """
| Синоним | id | Статус |
|---|---|---|
| реализация | doc-realizaciya | verified |
| отгрузка | doc-realizaciya | verified |
| контрагент | cat-kontragent | draft |
"""
    pairs = parse_by_synonym(text)
    assert ("реализация", "doc-realizaciya") in pairs
    assert ("отгрузка", "doc-realizaciya") in pairs
    assert ("контрагент", "cat-kontragent") in pairs

def test_parse_by_synonym_bullets():
    text = """
- **реализация** → `doc-realizaciya`
- отгрузка — doc-realizaciya
"""
    pairs = parse_by_synonym(text)
    assert ("реализация", "doc-realizaciya") in pairs
    assert ("отгрузка", "doc-realizaciya") in pairs

def test_parse_by_synonym_skips_headers():
    text = """
| Синоним | id |
|---|---|
| реализация | doc-realizaciya |
"""
    pairs = parse_by_synonym(text)
    # "Синоним" не должен попасть как синоним
    assert all(syn.lower() != "синоним" for syn, _ in pairs)
    assert len(pairs) == 1

def test_rebuild_roundtrip():
    fm, body = split(SAMPLE_CARD)
    rebuilt = rebuild(SAMPLE_CARD, fm)
    fm2, body2 = split(rebuilt)
    assert fm2 == fm
    assert body2 == body

def test_replace_block():
    text = """---
id: test
status: verified
synonyms: [касса, | unf30]
other: 1
---
Body here.
"""
    fm, _ = split(text)
    new_block = "synonyms:\n  - касса\n  - подотчёт"
    new_fm = replace_or_insert_block(fm, "status", "synonyms", new_block)
    
    assert "synonyms:\n  - касса\n  - подотчёт" in new_fm
    assert "unf30" not in new_fm
    assert "other: 1" in new_fm
