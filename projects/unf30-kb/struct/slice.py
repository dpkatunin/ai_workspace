"""
Вырезает один объект метаданных по ПолноеИмя из большого JSON-файла выгрузки.

Зачем: полная выгрузка УНФ/УТ в одном файле может быть 10–50 МБ.
Чтобы посмотреть один объект без загрузки всего файла в чат — режем срез.

Пишет результат как одиночный файл того же формата (`{"Объект": {...}}`),
чтобы дальше его можно было бы прогнать через survey.py или ingest.py.
"""
import argparse
import json
import sys
from pathlib import Path

from _common import iter_objects

def main() -> None:
    parser = argparse.ArgumentParser(description='Вырезать объект из JSON-выгрузки 1С')
    parser.add_argument('--input', required=True, help='Файл JSON-выгрузки')
    parser.add_argument(
        '--full-name',
        required=True,
        help='ПолноеИмя объекта, например Документ.ЗаказКлиента',
    )
    parser.add_argument('--output', required=True, help='Путь к файлу среза')
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Компактный JSON без отступов (меньше по размеру)',
    )
    parser.add_argument(
        '--wrap',
        action='store_true',
        default=True,
        help='Обернуть в {"Объект": ...} (по умолчанию; отключается флагом --no-wrap)',
    )
    parser.add_argument('--no-wrap', dest='wrap', action='store_false')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f'Файл не найден: {input_path}', file=sys.stderr)
        sys.exit(1)

    found = None
    for obj in iter_objects(input_path):
        if obj.get('ПолноеИмя') == args.full_name:
            found = obj
            break

    if not found:
        print(f'Объект не найден: {args.full_name}', file=sys.stderr)
        sys.exit(2)

    payload = {'Объект': found} if args.wrap else found
    indent = None if args.compact else 2
    output = json.dumps(payload, ensure_ascii=False, indent=indent)

    Path(args.output).write_text(output, encoding='utf-8')
    size_kb = len(output.encode('utf-8')) / 1024
    print(
        f'OK: {args.full_name} → {args.output} ({size_kb:.1f} КБ)',
        file=sys.stderr,
    )

if __name__ == '__main__':
    main()
