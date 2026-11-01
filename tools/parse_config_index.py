#!/usr/bin/env python3
"""
parse_config_index.py — создает быстрый поисковый индекс (JSON) из XML-выгрузки 1С.

Вместо того чтобы заставлять агента читать тяжелые XML-файлы (по 1-10 МБ),
этот скрипт один раз проходит по выгрузке, вытаскивает имена, синонимы и типы
всех основных объектов и сохраняет их в компактный config_index.json.

Использование:
    py tools/parse_config_index.py --src "_raw/unf30_xml"
"""

import argparse
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

# Категории объектов, которые нас интересуют
CATEGORIES = {
    "Documents": "Document",
    "Catalogs": "Catalog",
    "Enums": "Enum",
    "AccumulationRegisters": "AccumulationRegister",
    "InformationRegisters": "InformationRegister",
    "Reports": "Report",
    "DataProcessors": "DataProcessor",
    "CommonModules": "CommonModule",
}

def get_text(node, path: str) -> str:
    """Безопасно извлекает текст по пути с учетом пространств имен 1С."""
    try:
        # Ищем по локальному имени тега (игнорируя namespace)
        elem = node.find(path)
        if elem is not None and elem.text:
            return elem.text.strip()
    except Exception:
        pass
    return ""

def extract_synonym(root) -> str:
    """Ищет синоним (обычно на русском) в структуре объекта."""
    # Ищем тег Synonym -> item -> content
    for item in root.findall(".//{*}Synonym/{*}item"):
        lang = get_text(item, "{*}lang")
        if lang == "ru":
            return get_text(item, "{*}content")
    
    # Если русского нет, берем первый попавшийся
    for item in root.findall(".//{*}Synonym/{*}item"):
        content = get_text(item, "{*}content")
        if content:
            return content
            
    return ""

def process_file(file_path: Path, kind: str) -> dict | None:
    """Парсит один XML-файл объекта и возвращает словарь с данными."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Имя объекта (например, "РеализацияТоваровУслуг")
        name = get_text(root, ".//{*}Name")
        if not name:
            return None
            
        # Синоним (например, "Реализация товаров и услуг")
        synonym = extract_synonym(root)
        
        return {
            "kind": kind,
            "name": name,
            "synonym": synonym,
            "path": file_path.name
        }
    except ET.ParseError:
        # Пропускаем битые файлы
        return None
    except Exception as e:
        print(f"Ошибка при чтении {file_path.name}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Генератор индекса конфигурации 1С")
    parser.add_argument("--src", default="_raw/unf30_xml", help="Путь к папке с XML-выгрузкой")
    args = parser.parse_args()

    src_dir = Path(args.src).resolve()
    if not src_dir.exists():
        print(f"Ошибка: каталог {src_dir} не найден.")
        return

    index_data = []
    total_objects = 0

    print(f"Сканируем конфигурацию в: {src_dir}")

    for folder_name, kind in CATEGORIES.items():
        folder_path = src_dir / folder_name
        if not folder_path.exists():
            continue

        print(f"  - Обработка {folder_name}...")
        
        for file_path in folder_path.glob("*.xml"):
            # Пропускаем служебные файлы, если они есть
            if file_path.name.startswith("."):
                continue
                
            obj_data = process_file(file_path, kind)
            if obj_data:
                index_data.append(obj_data)
                total_objects += 1

    # Сортируем для удобства
    index_data.sort(key=lambda x: (x["kind"], x["name"]))

    # Сохраняем
    out_file = src_dir / "config_index.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"\n[ГОТОВО] Успешно обработано объектов: {total_objects}")
    print(f"Индекс сохранен в: {out_file}")
    print("Теперь MCP-сервер сможет искать по конфигурации мгновенно.")

if __name__ == "__main__":
    main()
