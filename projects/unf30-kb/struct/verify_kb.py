r"""
verify_kb.py — проверка скелета KB-карточек (этап 2, 2026-11-08).

Проверяет фронтматтер карточек kb/unf30/ согласно KB_SCHEMA v2:
  - id совпадает с именем файла (допускается префикс «unf30-»);
  - type из допустимого набора;
  - objects: каждое ПолноеИмя резолвится в struct.db (+ подсказки похожих);
  - links: файл целевой карточки существует (префикс «unf30-» опционален);
  - verified_against: предупреждение, если отсутствует (не ошибка);
  - карточки без фронтматтера — в отдельный список «легаси», не ошибка.

Скелет проверяет якоря, не прозу. Прозу по-прежнему линтует kb_lint.py.

Зависимости: только стандартная библиотека Python 3.10+.

Запуск (из корня workspace):
  .venv\Scripts\python.exe -X utf8 projects/unf30-kb/struct/verify_kb.py \
      --db projects/unf30-kb/struct/data/struct.db \
      --kb kb/unf30 \
      --md kb_verify_report.md --json kb_verify_report.json

Exit: 0 всегда; --strict → exit 2, если есть битые якоря (для будущего CI).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TYPES = ('doc', 'cat', 'mech', 'pb', 'pit', 'case')


def parse_frontmatter(text: str):
    """Подмножество YAML: 'ключ: значение' и плоские списки '- элемент'.
    Возвращает (meta, has_frontmatter)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return None, False
    meta = {}
    key = None
    for ln in lines[1:]:
        s = ln.strip()
        if s == '---':
            return meta, True
        if not s or s.startswith('#'):
            continue
        if s.startswith('- '):
            if key is not None:
                cur = meta.get(key)
                if not isinstance(cur, list):
                    cur = []
                    meta[key] = cur
                cur.append(s[2:].strip().strip('"').strip("'"))
            continue
        if ':' in ln:
            k, _, v = ln.partition(':')
            key = k.strip()
            v = v.strip()
            meta[key] = v.strip('"').strip("'") if v else ([] if v == '' else None)
    return meta, False  # не закрыт '---' — считаем отсутствующим


def check_objects(conn, objects):
    """Якоря против struct.db. Возвращает (ok[], broken[{name, suggestions}])."""
    ok, broken = [], []
    for name in objects:
        row = conn.execute(
            'SELECT 1 FROM objects WHERE full_name = ?', (name,)).fetchone()
        if row:
            ok.append(name)
        else:
            broken.append({'name': name})
    for b in broken:
        kind = b['name'].split('.')[0] if '.' in b['name'] else ''
        tail = b['name'].split('.')[-1]
        like = f'%{tail}%'
        rows = conn.execute(
            """SELECT full_name, kind, synonym, subsystem FROM objects
               WHERE kind = ? AND (name LIKE ? OR synonym LIKE ? OR full_name LIKE ?)
               ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, length(full_name)
               LIMIT 3""",
            (kind, like, like, like, tail)).fetchall()
        b['suggestions'] = [dict(r) for r in rows]
    return ok, broken


def verify(kb_dir: Path, db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        stems = {p.stem: p for p in kb_dir.rglob('*.md')}
        cards, legacy = [], []
        totals = {'files': 0, 'legacy': 0, 'anchored': 0, 'broken_anchors': 0,
                  'broken_links': 0, 'no_verified_against': 0, 'bad_id': 0,
                  'bad_type': 0}

        for p in sorted(kb_dir.rglob('*.md')):
            totals['files'] += 1
            rel = str(p)
            meta, has_fm = parse_frontmatter(p.read_text(encoding='utf-8'))
            if not has_fm:
                legacy.append(rel)
                totals['legacy'] += 1
                continue

            card = {'file': rel, 'id': meta.get('id'), 'type': meta.get('type'),
                    'objects_ok': [], 'objects_broken': [], 'links_broken': [],
                    'warnings': []}

            if card['id'] not in (p.stem, f'unf30-{p.stem}'):
                card['warnings'].append(f"id «{card['id']}» != имя файла «{p.stem}»")
                totals['bad_id'] += 1
            if card['type'] not in TYPES:
                card['warnings'].append(f"тип «{card['type']}» вне {TYPES}")
                totals['bad_type'] += 1

            objs = meta.get('objects') or []
            if objs:
                ok, broken = check_objects(conn, objs)
                card['objects_ok'] = ok
                card['objects_broken'] = broken
                totals['anchored'] += 1
                totals['broken_anchors'] += len(broken)

            for link in (meta.get('links') or []):
                if link.removeprefix('unf30-') not in stems:
                    card['links_broken'].append(link)
                    totals['broken_links'] += 1

            if not meta.get('verified_against'):
                card['warnings'].append('нет verified_against (штамп сверки)')
                totals['no_verified_against'] += 1

            cards.append(card)

        return {'totals': totals, 'cards': cards, 'legacy': legacy}
    finally:
        conn.close()


def report_md(data):
    t = data['totals']
    L = ['# verify_kb: скелет карточек против struct.db', '',
         f"- карточек: {t['files']} (со скелетом: {t['files'] - t['legacy']}, "
         f"легаси без скелета: {t['legacy']})",
         f"- карточек с якорями: {t['anchored']}; битых якорей: **{t['broken_anchors']}**; "
         f"битых ссылок: {t['broken_links']}",
         f"- предупреждений: id≠файл {t['bad_id']}, тип {t['bad_type']}, "
         f"нет штампа {t['no_verified_against']}", '',
         '_битый якорь = ПолноеИмя в objects[] карточки не найдено в текущей '
         'struct.db (объект убран релизом или опечатка). Триаж: подсказки ниже '
         'и diff_struct.py._', '']

    broken_cards = [c for c in data['cards'] if c['objects_broken'] or c['links_broken']]
    if broken_cards:
        L.append('## 🔴 битые якоря / ссылки')
        L.append('')
        for c in broken_cards:
            L.append(f"### `{c['file']}`")
            for b in c['objects_broken']:
                L.append(f"- `? {b['name']}` — нет в objects.full_name")
                for s in b.get('suggestions') or []:
                    L.append(f"  - похожее: `{s['full_name']}` "
                             f"({s.get('subsystem') or 'без подсистемы'})")
            for link in c['links_broken']:
                L.append(f"- `→ {link}` — карточка не найдена")
            L.append('')
    warned = [c for c in data['cards'] if c['warnings'] and c not in broken_cards]
    if warned:
        L.append('## 🟡 предупреждения (не ошибки)')
        L.append('')
        for c in warned:
            for w in c['warnings']:
                L.append(f"- `{c['file']}`: {w}")
        L.append('')
    if data['legacy']:
        L.append(f"## ⚪ легаси без скелета ({len(data['legacy'])})")
        L.append('')
        L += [f"- `{f}`" for f in data['legacy']]
        L.append('')
    anchored = [c for c in data['cards'] if c['objects_ok'] and not c['objects_broken']
                and not c['links_broken'] and not c['warnings']]
    if anchored:
        L.append('## ✅ чистые карточки со скелетом')
        L.append('')
        L += [f"- `{c['file']}` ({len(c['objects_ok'])} якорей)" for c in anchored]
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description='Проверка скелета KB-карточек')
    ap.add_argument('--db', required=True)
    ap.add_argument('--kb', required=True, help='Папка карточек (kb/unf30)')
    ap.add_argument('--md', help='Markdown-отчёт (по умолчанию stdout)')
    ap.add_argument('--json', dest='json_out', help='JSON-отчёт')
    ap.add_argument('--strict', action='store_true',
                    help='Exit 2, если есть битые якоря')
    args = ap.parse_args()

    kb_dir = Path(args.kb)
    if not kb_dir.is_dir():
        sys.stderr.write(f'Папка не найдена: {kb_dir}\n')
        return 1

    data = verify(kb_dir, Path(args.db))
    md = report_md(data)
    if args.md:
        Path(args.md).write_text(md + '\n', encoding='utf-8')
    else:
        sys.stdout.write(md + '\n')
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 2 if (args.strict and data['totals']['broken_anchors']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
