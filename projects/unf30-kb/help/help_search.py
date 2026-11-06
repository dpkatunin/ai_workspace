"""
help_search.py — CLI-поиск по HELP-слою (FTS5 поверх data/help.db).

    python -X utf8 help_search.py "заказ наряд"
    python -X utf8 help_search.py "резервирование" --limit 10
    python -X utf8 help_search.py "заказ-наряд" --kind Документ
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

WORD = re.compile(r'[A-Za-zА-Яа-яЁё0-9_]+')


def to_fts_query(q: str) -> str:
    """Свободный текст → безопасный FTS5 AND-запрос: 'заказ-наряд' → '"заказ" "наряд"'.
    Внимание: unicode61-токенизатор не знает морфологии ('зарезервировать' ≠ 'резервировать')."""
    words = WORD.findall(q)
    return ' '.join(f'"{w}"' for w in words)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('query')
    ap.add_argument('--db', default=str(Path(__file__).parent / 'data' / 'help.db'))
    ap.add_argument('--limit', type=int, default=5)
    ap.add_argument('--kind', help='фильтр по виду объекта, напр. Документ')
    args = ap.parse_args()
    if not Path(args.db).is_file():
        print(f'нет БД: {args.db} (сначала ingest_help.py)', file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(args.db)
    where, params = '', []
    if args.kind:
        where = "AND a.object_full_name LIKE ?"
        params.append(args.kind + '.%')
    q = to_fts_query(args.query)
    if not q:
        print('нет слов для поиска', file=sys.stderr)
        sys.exit(2)
    try:
        rows = conn.execute(f"""
            SELECT a.title, a.path, a.object_full_name,
                   snippet(help_articles_fts, 1, '>>>', '<<<', ' … ', 12) AS snip
            FROM help_articles_fts f
            JOIN help_articles a ON a.id = f.rowid
            WHERE help_articles_fts MATCH ? {where}
            ORDER BY bm25(help_articles_fts)
            LIMIT ?""", [q, *params, args.limit]).fetchall()
    except sqlite3.OperationalError as e:
        print(f'FTS-запрос не прошёл: {e}\nПопробуй другие слова (спецсимволы FTS не поддерживаются).', file=sys.stderr)
        sys.exit(2)
    if not rows:
        print('нет данных')
        return
    for i, (title, path, obj, snip) in enumerate(rows, 1):
        print(f'{i}. {title}')
        print(f'   путь:   {path}')
        if obj:
            print(f'   объект: {obj}')
        print(f'   {snip}')
        print()


if __name__ == '__main__':
    main()
