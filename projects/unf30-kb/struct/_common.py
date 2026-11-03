"""
Общие утилиты для работы с JSON-выгрузкой 1С метаданных.
Потоковое чтение через ijson, чтобы не грузить в память файлы в десятки-сотни МБ.
"""
import json
from pathlib import Path

import ijson

def iter_objects(file_path: Path):
    """
    Потоково итерирует объекты из JSON-файла выгрузки.

    Поддерживает два формата (по контракту 1c-metadata-json-exporter):
    - Общий файл (ОтдельныеФайлы=Ложь): верхний ключ "Объекты" — массив.
    - Одиночный файл (ОтдельныеФайлы=Истина): верхний ключ "Объект" — один объект.

    Не читает файл целиком — только нужный массив потоком.
    """
    file_path = Path(file_path)
    with open(file_path, 'rb') as f:
        # Попытка 1: общий файл (массив Объекты)
        found_any = False
        try:
            for obj in ijson.items(f, 'Объекты.item'):
                found_any = True
                yield obj
        except Exception:
            pass
        if found_any:
            return

        # Попытка 2: одиночный файл (один Объект)
        f.seek(0)
        try:
            for obj in ijson.items(f, 'Объект'):
                yield obj
                return
        except Exception as e:
            raise RuntimeError(f'Не удалось распарсить {file_path}: {e}') from e

        # Попытка 3 (fallback): прочитать целиком (для маленьких файлов)
        f.seek(0)
        try:
            data = json.load(f)
        except Exception as e:
            raise RuntimeError(f'Файл не является JSON: {file_path}: {e}') from e
        if 'Объекты' in data:
            yield from data['Объекты']
        elif 'Объект' in data:
            yield data['Объект']

def iter_header(file_path: Path):
    """
    Читает заголовок файла (Конфигурация, Версия, ДатаВыгрузки).
    Возвращает dict с ключами config_name, config_version, dump_date.
    Для одиночных файлов без заголовка вернёт None в каждом поле.
    """
    result = {'config_name': None, 'config_version': None, 'dump_date': None}
    with open(file_path, 'rb') as f:
        try:
            for prefix, event, value in ijson.parse(f):
                if event != 'string':
                    continue
                if prefix == 'Конфигурация':
                    result['config_name'] = value
                elif prefix == 'Версия':
                    result['config_version'] = value
                elif prefix == 'ДатаВыгрузки':
                    result['dump_date'] = value
                elif prefix == 'Объекты':
                    # дошли до массива объектов — заголовок закончился
                    break
        except Exception:
            pass
    return result

def iter_json_files(input_path: Path):
    """Возвращает список .json-файлов (один файл или все в папке)."""
    input_path = Path(input_path)
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(input_path.glob('*.json'))
    raise FileNotFoundError(f'Не найдено: {input_path}')
