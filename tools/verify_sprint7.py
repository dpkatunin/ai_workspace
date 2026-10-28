#!/usr/bin/env python3
"""
verify_sprint7.py — перевод карточек pit-ceny и doc-ustanovka-cen в статус verified.
"""
from pathlib import Path
import re

def verify_card(path: Path):
    if not path.exists():
        print(f"✗ Файл не найден: {path}")
        return
        
    text = path.read_text(encoding="utf-8")
    
    if "status: draft" not in text:
        print(f"⚠ В {path.name} статус уже не 'draft'. Возможно, скрипт уже запускался.")
        return
        
    text = text.replace("status: draft", "status: verified")
    
    if "verified_by:" not in text:
        text = re.sub(r"(status: verified)", r"\1\nverified_by: admin\nverified_at: 2026-10-28", text, count=1)
        
    path.write_text(text, encoding="utf-8")
    print(f"✓ Карточка {path.name} переведена в verified")

def main():
    pit_ceny = Path("kb/unf30/pitfalls/pit-ceny.md")
    doc_ceny = Path("kb/unf30/objects/doc-ustanovka-cen.md")
    
    verify_card(pit_ceny)
    verify_card(doc_ceny)

if __name__ == "__main__":
    main()
