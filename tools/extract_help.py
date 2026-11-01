#!/usr/bin/env python3
"""
extract_help.py — извлекает файлы справки (ru.html) из выгрузки 1С.

Ищет все ru.html в структуре Ext/Help/ и копирует их в папку назначения,
переименовывая в <ИмяОбъекта>.html и раскладывая по категориям
(Documents/, Catalogs/, DataProcessors/ и т.д.).

Использование:
    py tools/extract_help.py --src "C:\unf30_xml_dump" --dst "_source\01_unf\official_help"
"""

import os
import shutil
import argparse
from pathlib import Path

def extract_help(src_path, dst_path):
    src = Path(src_path).resolve()
    dst = Path(dst_path).resolve()

    if not src.exists():
        print(f"Ошибка: папка {src} не найдена.")
        return

    print(f"Ищем справку в: {src}")
    print(f"Сохраняем в: {dst}\n")

    count = 0

    for root, dirs, files in os.walk(src):
        if "ru.html" in files:
            file_path = Path(root) / "ru.html"

            # Проверяем, что это справка: путь должен заканчиваться на Ext/Help/ru.html
            if file_path.parent.name == "Help" and file_path.parent.parent.name == "Ext":
                # Определяем имя объекта и категорию
                obj_dir = file_path.parent.parent.parent
                obj_name = obj_dir.name
                category = obj_dir.parent.name

                # Если категория совпадает с корнем (например, CommonHelp),
                # то она неинформативна — кладём в _root
                if category == src.name:
                    category = "_root"

                # Создаём папку категории
                target_dir = dst / category
                target_dir.mkdir(parents=True, exist_ok=True)

                # Копируем файл как <ИмяОбъекта>.html
                target_file = target_dir / f"{obj_name}.html"
                shutil.copy2(file_path, target_file)

                count += 1
                print(f"[OK] {category}/{obj_name}.html")

    print(f"\nГотово. Скопировано файлов: {count}")
    if count == 0:
        print("Файлы справки не найдены. Проверьте, что выгрузка сделана")
        print("с флагом -Help или содержит папки Ext/Help.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Извлечение справки из выгрузки 1С")
    parser.add_argument("--src", required=True, help="Путь к выгрузке конфигурации")
    parser.add_argument("--dst", required=True, help="Куда сохранить извлечённую справку")
    args = parser.parse_args()

    extract_help(args.src, args.dst)
