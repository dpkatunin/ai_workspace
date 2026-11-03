"""
Структурный отчёт по папке с JSON-выгрузкой 1С метаданных.

Назначение: дать компактный (5–15 КБ) обзор того, что лежит в выгрузке —
без самих данных. Используется при отладке ingest и при передаче контекста
в новый чат.

Не читает файлы целиком: ijson-поток через _common.iter_objects.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from _common import iter_json_files, iter_objects

def survey_file(file_path: Path) -> dict:
    """Собирает статистику по одному JSON-файлу."""
    stats = {
        'file': file_path.name,
        'size_mb': round(file_path.stat().st_size / (1024 * 1024), 2),
        'objects': 0,
        'max_attributes': 0,
        'max_types_per_attribute': 0,
        'max_tabular_sections': 0,
    }

    for obj in iter_objects(file_path):
        stats['objects'] += 1

        # Сумма атрибутов: реквизиты + измерения + ресурсы
        total_attrs = (
            len(obj.get('Реквизиты', []))
            + len(obj.get('Измерения', []))
            + len(obj.get('Ресурсы', []))
        )
        if total_attrs > stats['max_attributes']:
            stats['max_attributes'] = total_attrs

        # Максимум типов в одном реквизите — критичный параметр для лимитов
        for role in ('Реквизиты', 'Измерения', 'Ресурсы', 'СтандартныеРеквизиты'):
            for attr in obj.get(role, []):
                tc = len(attr.get('Типы', []))
                if tc > stats['max_types_per_attribute']:
                    stats['max_types_per_attribute'] = tc

        # ТЧ
        tch_count = len(obj.get('ТабличныеЧасти', []))
        if tch_count > stats['max_tabular_sections']:
            stats['max_tabular_sections'] = tch_count

    return stats

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Структурный отчёт по JSON-выгрузке 1С метаданных'
    )
    parser.add_argument('--input', required=True, help='Файл или папка с JSON')
    parser.add_argument('--output', help='Путь к файлу отчёта (по умолчанию stdout)')
    parser.add_argument(
        '--types-threshold',
        type=int,
        default=50,
        help='Порог по числу типов в одном реквизите для аномалий (по умолчанию 50)',
    )
    parser.add_argument(
        '--attrs-threshold',
        type=int,
        default=100,
        help='Порог по числу реквизитов в объекте для аномалий (по умолчанию 100)',
    )
    args = parser.parse_args()

    try:
        files = iter_json_files(Path(args.input))
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not files:
        print(f'Нет .json файлов в {args.input}', file=sys.stderr)
        sys.exit(1)

    report = {
        'input': str(args.input),
        'file_count': len(files),
        'total_size_mb': 0,
        'files': [],
        'kinds': Counter(),
        'anomalies': [],
    }

    print(f'Обрабатываю {len(files)} файл(ов)...', file=sys.stderr)
    for fp in files:
        print(f'  {fp.name} ({fp.stat().st_size / 1024 / 1024:.1f} МБ)...', file=sys.stderr)
        file_stats = survey_file(fp)
        report['files'].append(file_stats)
        report['total_size_mb'] += file_stats['size_mb']

        # Второй проход по файлу — для kinds и аномалий.
        # На файле 13 МБ это займёт секунды; для очень больших папок оптимизируем позже.
        for obj in iter_objects(fp):
            report['kinds'][obj.get('ВидОбъекта', '?')] += 1

            full_name = obj.get('ПолноеИмя', '?')

            # Аномалия: реквизит с большим числом типов
            for role in ('Реквизиты', 'Измерения', 'Ресурсы'):
                for attr in obj.get(role, []):
                    tc = len(attr.get('Типы', []))
                    if tc >= args.types_threshold:
                        report['anomalies'].append({
                            'type': 'many_types_in_attribute',
                            'object': full_name,
                            'attribute': attr.get('Имя', '?'),
                            'role': role,
                            'types_count': tc,
                        })

            # Аномалия: объект с большим числом реквизитов
            total = (
                len(obj.get('Реквизиты', []))
                + len(obj.get('Измерения', []))
                + len(obj.get('Ресурсы', []))
            )
            if total >= args.attrs_threshold:
                report['anomalies'].append({
                    'type': 'many_attributes_in_object',
                    'object': full_name,
                    'attributes_count': total,
                })

    report['kinds'] = dict(report['kinds'])
    report['total_size_mb'] = round(report['total_size_mb'], 2)
    # Сортировка по убыванию числа объектов — так виднее «толстые» виды
    report['kinds'] = dict(
        sorted(report['kinds'].items(), key=lambda kv: -kv[1])
    )

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        size_kb = len(output.encode('utf-8')) / 1024
        print(f'OK: {args.output} ({size_kb:.1f} КБ)', file=sys.stderr)
    else:
        print(output)

if __name__ == '__main__':
    main()
