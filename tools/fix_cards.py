#!/usr/bin/env python3
"""
fix_cards.py — одноразовый патчер для приведения карточек doc-realizaciya
и cat-kontragent к строгому формату ADR-003 (технические имена регистров).
"""
import re
import json
from pathlib import Path

def fix_md_section(path: Path, section_name: str, new_content: str):
    """Найти секцию ## Имя и заменить всё до следующего ##."""
    text = path.read_text(encoding="utf-8")
    # Ищем заголовок и всё до следующего заголовка H2
    pattern = re.compile(rf"^(##\s+{section_name}.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
    replacement = f"## {section_name}\n\n{new_content}\n\n"
    
    new_text, count = pattern.subn(replacement, text)
    if count > 0:
        path.write_text(new_text, encoding="utf-8")
        print(f"✓ Обновлена секция '{section_name}' в {path.name}")
    else:
        print(f"✗ Секция '{section_name}' не найдена в {path.name}")

def main():
    # 1. Исправляем doc-realizaciya.md (Движения)
    doc_moves = """- `РегистрНакопления.ТоварыНаСкладах`
- `РегистрНакопления.Продажи`
- `РегистрНакопления.РасчетыСПокупателями`
- `РегистрНакопления.РасчетыСПоставщиками`
- `РегистрНакопления.ПредоставленныеСкидки`"""
    doc_path = Path("kb/unf30/objects/doc-realizaciya.md")
    if doc_path.exists():
        fix_md_section(doc_path, "Движения", doc_moves)

    # 2. Исправляем cat-kontragent.md (Тип и Участие в регистрах)
    cat_path = Path("kb/unf30/objects/cat-kontragent.md")
    if cat_path.exists():
        cat_text = cat_path.read_text(encoding="utf-8")
        if "type: object" in cat_text:
            cat_text = cat_text.replace("type: object", "type: catalog")
            cat_path.write_text(cat_text, encoding="utf-8")
            print("✓ Исправлен тип на 'catalog' в cat-kontragent.md")
        
        cat_usage = """- `РегистрНакопления.ВзаиморасчетыСКонтрагентами`
- `РегистрНакопления.РасчетыСПокупателями`
- `РегистрНакопления.РасчетыСПоставщиками`
- `РегистрНакопления.ЗаказыПокупателей`"""
        fix_md_section(cat_path, "Участие в регистрах", cat_usage)

    # 3. Обновляем эталоны references.json
    refs = {
        "_comment": "Ручные эталоны (исправленные под технические имена ADR-003)",
        "doc-realizaciya": {
            "type": "object",
            "status": "verified",
            "registers": [
                "РегистрНакопления.ТоварыНаСкладах",
                "РегистрНакопления.Продажи",
                "РегистрНакопления.РасчетыСПокупателями",
                "РегистрНакопления.РасчетыСПоставщиками",
                "РегистрНакопления.ПредоставленныеСкидки"
            ]
        },
        "pit-ceny": {
            "type": "pitfall",
            "status": "draft",
            "registers": []
        },
        "cat-kontragent": {
            "type": "catalog",
            "status": "draft",
            "registers": [
                "РегистрНакопления.ВзаиморасчетыСКонтрагентами",
                "РегистрНакопления.РасчетыСПокупателями",
                "РегистрНакопления.РасчетыСПоставщиками",
                "РегистрНакопления.ЗаказыПокупателей"
            ]
        }
    }
    
    refs_path = Path("_meta/_expected/references.json")
    refs_path.parent.mkdir(parents=True, exist_ok=True)
    refs_path.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✓ Обновлен эталон references.json")

if __name__ == "__main__":
    main()
