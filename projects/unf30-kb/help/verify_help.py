r"""
verify_help.py — контроль целостности HELP-слоя (data/help.db).

Запускать из каталога projects\\unf30-kb\\help:
    ..\..\..\.venv\Scripts\python.exe verify_help.py
(или с явным путём: python -X utf8 verify_help.py --db data\help.db)

Возвращает exit 0, если критичные проверки зелёные; 1 — если есть красное.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

OK, WARN, FAIL = 'OK ', 'WARN', 'FAIL'


def check(label, status, detail=''):
    print(f'[{status}] {label}' + (f' — {detail}' if detail else ''))
    return status != FAIL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=str(Path(__file__).parent / 'data' / 'help.db'))
    args = ap.parse_args()
    db = Path(args.db)
    if not db.is_file():
        print(f'[FAIL] нет файла БД: {db}')
        sys.exit(1)
    conn = sqlite3.connect(db)
    green = True

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')")}
    green &= check('таблица help_articles', OK if 'help_articles' in tables else FAIL)
    green &= check('таблица help_links', OK if 'help_links' in tables else FAIL)
    green &= check('FTS help_articles_fts', OK if 'help_articles_fts' in tables else FAIL,
                   'полнотекстовый поиск недоступен' if 'help_articles_fts' not in tables else '')
    if not green:
        sys.exit(1)

    total = conn.execute('SELECT COUNT(*) FROM help_articles').fetchone()[0]
    green &= check('статьи есть', OK if total > 0 else FAIL, f'всего {total}')

    empty = conn.execute("SELECT COUNT(*) FROM help_articles WHERE LENGTH(TRIM(text)) < 50").fetchone()[0]
    check('нет подозрительно коротких статей (<50 симв.)', OK if empty == 0 else WARN, f'{empty} шт.')

    no_title = conn.execute("SELECT COUNT(*) FROM help_articles WHERE title IS NULL OR title = ''").fetchone()[0]
    check('заголовки у всех статей', OK if no_title == 0 else WARN, f'без title: {no_title}')

    print()
    print('--- распределение по видам ---')
    for row in conn.execute("SELECT ref_kind, COUNT(*) FROM help_articles GROUP BY ref_kind ORDER BY 2 DESC"):
        print(f'  {row[0]:15s} {row[1]}')

    print()
    print('--- привязка к объектам метаданных ---')
    linked = conn.execute("SELECT COUNT(*) FROM help_articles WHERE object_full_name IS NOT NULL").fetchone()[0]
    print(f'  с object_full_name: {linked} / {total}')
    print('  топ-10 объектов с привязкой:')
    for row in conn.execute("""SELECT object_full_name, COUNT(*) c FROM help_articles
                               WHERE object_full_name IS NOT NULL
                               GROUP BY 1 ORDER BY c DESC, 1 LIMIT 10"""):
        print(f'    {row[0]}  ({row[1]} статей)')

    print()
    print('--- ссылки между статьями ---')
    for row in conn.execute("SELECT link_kind, COUNT(*) FROM help_links GROUP BY 1 ORDER BY 2 DESC"):
        print(f'  {row[0]:15s} {row[1]}')
    internal = conn.execute("SELECT COUNT(*) FROM help_links WHERE link_kind='object_help'").fetchone()[0]
    check('внутренние ссылки object_help найдены', OK if internal > 0 else WARN,
          'формат ссылок не распознан — пришли образец' if internal == 0 else f'{internal} шт.')

    print()
    print('--- FTS-самопроверка ---')
    fts_n = conn.execute('SELECT COUNT(*) FROM help_articles_fts').fetchone()[0]
    check('FTS заполнен', OK if fts_n == total else FAIL, f'fts={fts_n}, articles={total}')
    probe = conn.execute("""SELECT a.title FROM help_articles_fts f JOIN help_articles a ON a.id = f.rowid
                            WHERE help_articles_fts MATCH 'документ' LIMIT 3""").fetchall()
    check('пробный запрос "документ"', OK if probe else WARN, f'нашлось {len(probe)} (первые: {[r[0] for r in probe]})')

    print()
    print('ИТОГ: ' + ('зелёный' if green else 'есть FAIL — см. выше'))
    sys.exit(0 if green else 1)


if __name__ == '__main__':
    main()
