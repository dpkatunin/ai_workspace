#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика парсинга карточек.
Показывает, какие файлы видит скрипт, их кодировку и первые символы.
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def check_dir(kb_dir: Path):
    if not kb_dir.exists():
        print(f"❌ Папка {kb_dir} НЕ СУЩЕСТВУЕТ по этому пути!")
        return

    print(f"📂 Сканируем {kb_dir.absolute()}...")
    files = list(kb_dir.glob("*.md"))
    print(f"Найдено .md файлов: {len(files)}\n")

    for p in sorted(files)[:5]:  # показываем первые 5 для примера
        if p.name.startswith("_"):
            print(f"  - {p.name} (пропускаем, служебный)")
            continue
            
        raw_bytes = p.read_bytes()
        print(f"  📄 Файл: {p.name} ({len(raw_bytes)} байт)")
        
        # Пробуем прочитать как utf-8-sig
        try:
            text = raw_bytes.decode("utf-8-sig")
            first_chars = repr(text[:15]) # показываем первые 15 символов с экранированием
            print(f"     Первые символы (utf-8-sig): {first_chars}")
            
            if text.lstrip().startswith("---"):
                print("     ✅ Начинается с '---'")
            else:
                print("     ❌ НЕ начинается с '---' (возможно, пробелы или невидимые символы до '---')")
                
        except UnicodeDecodeError:
            print("     ⚠️ Ошибка декодирования UTF-8 (файл в другой кодировке, например cp1251)")
            try:
                text = raw_bytes.decode("cp1251")
                print(f"     Первые символы (cp1251): {repr(text[:15])}")
            except Exception as e:
                print(f"     ❌ Не удалось прочитать и как cp1251: {e}")

if __name__ == "__main__":
    check_dir(Path("kb/unf30"))
