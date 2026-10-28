#!/usr/bin/env python3
"""
verify_catalog_cards.py — перевод карточек cat-kontragent и cat-kassy в статус verified.
Скрипт сам находит файлы в подпапках, обновляет YAML и эталон references.json.
"""
from pathlib import Path
import re
import json

def verify_card(kb_dir: Path, stem: str):
    # Ищем файл по всему дереву kb/unf30
    matches = list(kb_dir.rglob(f"{stem}.md"))
    if not matches:
        print(f"✗ Файл {stem}.md не найден.")
        return
        
    path = matches[0]
    text = path.read_text(encoding="utf-8")
    
    if "status: draft" not in text:
        print(f"⚠ В {path.name} статус уже не 'draft'. Возможно, скрипт уже запускался.")
        return
        
    # Меняем статус и добавляем поля верификации
    text = text.replace("status: draft", "status: verified")
    
    if "verified_by:" not in text:
        text = re.sub(r"(status: verified)", r"\1\nverified_by: admin\nverified_at: 2026-10-29", text, count=1)
        
    path.write_text(text, encoding="utf-8")
    print(f"✓ Карточка {path.name} переведена в verified")

def update_references(meta_dir: Path):
    refs_path = meta_dir / "_expected" / "references.json"
    if not refs_path.exists():
        print("✗ references.json не найден.")
        return
        
    try:
        refs = json.loads(refs_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"✗ Ошибка чтения references.json: {e}")
        return

    updated = False
    for card_id in ("cat-kontragent", "cat-kassy"):
        if card_id in refs and refs[card_id].get("status") == "draft":
            refs[card_id]["status"] = "verified"
            updated = True
            print(f"✓ Эталон для {card_id} обновлен на verified")

    if updated:
        refs_path.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print("⚠ Эталоны уже были в статусе verified (или их нет в references.json).")

def main():
    kb_dir = Path("kb/unf30")
    meta_dir = Path("_meta")
    
    verify_card(kb_dir, "cat-kontragent")
    verify_card(kb_dir, "cat-kassy")
    
    update_references(meta_dir)

if __name__ == "__main__":
    main()
