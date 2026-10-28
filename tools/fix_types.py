#!/usr/bin/env python3
"""
fix_types.py — исправляет поле type: object на type: catalog 
для всех файлов, начинающихся с cat-*.
"""
from pathlib import Path

def main():
    kb_dir = Path("kb/unf30")
    fixed_count = 0

    # Ищем все файлы во всех подпапках
    for path in kb_dir.rglob("*.md"):
        if path.name == "_index.md":
            continue
            
        # Нас интересуют только справочники (префикс cat-)
        if not path.stem.startswith("cat-"):
            continue
            
        text = path.read_text(encoding="utf-8")
        
        # Если в справочнике ошибочно стоит type: object
        if "type: object" in text:
            text = text.replace("type: object", "type: catalog")
            path.write_text(text, encoding="utf-8")
            print(f"✓ Исправлен {path.name}: object -> catalog")
            fixed_count += 1

    if fixed_count == 0:
        print("Все справочники уже имеют правильный тип.")
    else:
        print(f"Готово! Исправлено файлов: {fixed_count}")

if __name__ == "__main__":
    main()