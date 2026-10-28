#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизатор статусов в _meta/_expected/references.json с реальными карточками.
Исправлена кодировка для Windows и добавлен гибкий поиск файлов.
"""
import json
import sys
from pathlib import Path

# Принудительно переводим вывод в UTF-8 для Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def find_card_file(card_id: str) -> Path:
    """Ищет файл карточки, учитывая возможные префиксы в ID."""
    kb_dir = Path("kb/unf30")
    
    # Вариант 1: как есть
    p = kb_dir / f"{card_id}.md"
    if p.exists(): return p
    
    # Вариант 2: добавляем unf30- (если в JSON без префикса)
    if not card_id.startswith("unf30-"):
        p = kb_dir / f"unf30-{card_id}.md"
        if p.exists(): return p
        
    # Вариант 3: убираем unf30- (если в JSON с префиксом, а файл без)
    if card_id.startswith("unf30-"):
        p = kb_dir / f"{card_id[6:]}.md"
        if p.exists(): return p
        
    return None

def main():
    ref_file = Path("_meta/_expected/references.json")
    if not ref_file.exists():
        print(f"Файл {ref_file} не найден.")
        return

    data = json.loads(ref_file.read_text(encoding="utf-8"))
    changed = False

    print(f"Загружено {len(data)} записей из эталона.")
    print("Ключи в эталоне:", list(data.keys())[:5], "..." if len(data) > 5 else "")
    print("-" * 50)

    # Проходим по всем эталонам
    for card_id, info in data.items():
        card_path = find_card_file(card_id)
        
        if not card_path:
            print(f"[!] Файл для '{card_id}' не найден ни в одном из вариантов. Пропускаем.")
            continue

        text = card_path.read_text(encoding="utf-8-sig")
        actual_status = "draft"
        for line in text.splitlines():
            if line.startswith("status:"):
                actual_status = line.split(":")[1].strip()
                break

        # Если статус в эталоне не совпадает
        if info.get("status") != actual_status:
            print(f"[FIX] {card_path.name}: эталон={info.get('status')} -> реальность={actual_status}")
            info["status"] = actual_status
            changed = True

    if changed:
        ref_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("-" * 50)
        print("OK: references.json обновлен.")
    else:
        print("-" * 50)
        print("OK: Все статусы уже синхронизированы (или не найдено совпадений).")

if __name__ == "__main__":
    main()
