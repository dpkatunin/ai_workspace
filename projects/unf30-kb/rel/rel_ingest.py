r"""rel_ingest.py — REL-слой: загрузка «Новое в версии» с ITS в rel.db (этап 3).

Источник — публичная страница ITS вида
    https://its.1c.ru/db/content/updinfo/src/smallbusiness/<версия>/index.htm
Вход: сохранённый локально HTML (--html) или прямой URL (--url). PDF-распечатки
НЕ подходят: кириллица в них необратимо портится кодировкой шрифтов.

Структура ITS-страницы: заголовок H1 с версией, оглавление (ul до первого H2),
разделы H2 с подразделами H3, абзацы P и списки UL/LI. Скрипт собирает
иерархию разделов, извлекает текст и линкует его к struct.db через индекс
синонимов/имён (тот же механизм, что kb_anchors_propose.py — reuse по принципу
kb_lint→answer_guard).

rel.db — накопительный журнал релизов (НЕ снимок, в отличие от struct/help):
повторная загрузка той же версии заменяет её записи. При расхождении
REL и STRUCT истина — STRUCT (зафиксировано в REL.md).

Зависимости: stdlib + kb_anchors_propose.py (папка ../struct).

Запуск (из projects/unf30-kb/rel):
  python rel_ingest.py --html "3.0.14.159.htm" --md ingest_report.md
  python rel_ingest.py --url "https://its.1c.ru/db/content/updinfo/src/smallbusiness/3.0.14.159/index.htm"

Exit: 0 всегда (это инжест, не валидация).
"""
import argparse
import json
import re
import sqlite3
import sys
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / 'struct'))
import kb_anchors_propose as kap  # load_phrase_index, find_mentions

VERSION_RE = re.compile(r'Новое\s+в\s+версии?\s+([\d.]+)', re.I)
URL_VERSION_RE = re.compile(r'/(\d+\.\d+\.\d+\.\d+)/')
BLOCK_TAGS = ('h1', 'h2', 'h3', 'h4', 'p', 'li')
HEADING_LVLS = {'h1': 1, 'h2': 2, 'h3': 3, 'h4': 4}


SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    title TEXT,
    source_url TEXT,
    ingested_at TEXT
);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    release_id INTEGER NOT NULL REFERENCES releases(id),
    path TEXT NOT NULL,
    title TEXT,
    body TEXT
);
CREATE TABLE IF NOT EXISTS entry_objects (
    entry_id INTEGER NOT NULL REFERENCES entries(id),
    full_name TEXT NOT NULL,
    by TEXT,
    n_words INTEGER,
    context TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_rel ON entries(release_id);
CREATE INDEX IF NOT EXISTS idx_eo_entry ON entry_objects(entry_id);
CREATE INDEX IF NOT EXISTS idx_eo_obj ON entry_objects(full_name);
"""


def fetch_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    for enc in ('utf-8', 'utf-8-sig', 'cp1251'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def parse_blocks(html_text):
    """HTML -> упорядоченные блоки (tag, текст). stdlib-only."""
    blocks = []

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.skip = 0
            self.cur = None
            self.buf = []

        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'):
                self.skip += 1
            elif tag in BLOCK_TAGS and not self.skip and self.cur is None:
                self.cur = tag
                self.buf = []

        def handle_endtag(self, tag):
            if tag in ('script', 'style'):
                self.skip = max(0, self.skip - 1)
            elif tag == self.cur:
                t = ' '.join(''.join(self.buf).split())
                if t:
                    blocks.append((tag, t))
                self.cur = None
                self.buf = []

        def handle_data(self, data):
            if self.cur and not self.skip:
                self.buf.append(data)

    p = P()
    p.feed(html_text)
    p.close()
    return blocks


def assemble(blocks):
    """Блоки -> (title, lead_lines, sections[{level,path,title,lines}])."""
    title = ''
    lead = []
    sections = []
    stack = []           # [(level, title)] — текущая цепочка заголовков
    cur_lines = lead

    for tag, t in blocks:
        lvl = HEADING_LVLS.get(tag)
        if tag == 'h1' and not title:
            title = t
            continue
        if lvl:
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            stack.append((lvl, t))
            sec = {'level': lvl, 'path': '/'.join(x[1] for x in stack),
                   'title': t, 'lines': []}
            sections.append(sec)
            cur_lines = sec['lines']
        else:
            cur_lines.append(('- ' if tag == 'li' else '') + t)
    return title, lead, sections


def extract_version(title, source_ref):
    m = VERSION_RE.search(title or '')
    if m:
        return m.group(1)
    m = URL_VERSION_RE.search(source_ref or '')
    if m:
        return m.group(1)
    return None


def ensure_schema(conn):
    conn.executescript(SCHEMA)


def ingest(html_text, rel_db, struct_db, source_ref, forced_version=None):
    title, lead, sections = assemble(parse_blocks(html_text))
    version = forced_version or extract_version(title, source_ref)
    if not version:
        raise SystemExit('Не удалось определить версию релиза: укажите --version.')

    idx = kap.load_phrase_index(struct_db, kinds=kap.KINDS)
    for sec in sections:
        text = sec['title'] + '\n' + '\n'.join(sec['lines'])
        sec['mentions'] = kap.find_mentions(text, idx)
    if lead:
        sections.insert(0, {'level': 0, 'path': '_оглавление', 'title': '_оглавление',
                            'lines': lead, 'mentions': {}})

    conn = sqlite3.connect(rel_db)
    ensure_schema(conn)
    with conn:
        old = conn.execute('SELECT id FROM releases WHERE version=?',
                           (version,)).fetchone()
        if old:
            conn.execute('DELETE FROM entry_objects WHERE entry_id IN '
                         '(SELECT id FROM entries WHERE release_id=?)', (old[0],))
            conn.execute('DELETE FROM entries WHERE release_id=?', (old[0],))
            conn.execute('DELETE FROM releases WHERE id=?', (old[0],))
        cur = conn.execute(
            'INSERT INTO releases (version, title, source_url, ingested_at) '
            'VALUES (?,?,?,?)',
            (version, title, source_ref, date.today().isoformat()))
        rid = cur.lastrowid
        for sec in sections:
            cur = conn.execute(
                'INSERT INTO entries (release_id, path, title, body) VALUES (?,?,?,?)',
                (rid, sec['path'], sec['title'],
                 '\n'.join(sec['lines'])[:20000]))
            eid = cur.lastrowid
            for full_name, info in sorted(sec['mentions'].items()):
                conn.execute(
                    'INSERT INTO entry_objects VALUES (?,?,?,?,?)',
                    (eid, full_name, info['by'], info['n_words'],
                     (info['contexts'][0] if info['contexts'] else '')[:200]))
    conn.close()
    return {'version': version, 'title': title, 'source': source_ref,
            'sections': sections,
            'total_links': sum(len(s['mentions']) for s in sections)}


def report_md(data):
    L = []
    L.append('# rel_ingest: журнал релиза ' + data['version'])
    L.append(f"- источник: {data['source']}")
    L.append(f"- разделов: {len(data['sections'])}; "
             f"привязок к объектам: **{data['total_links']}**")
    L.append('')
    L.append('⚪ = раздел без привязок к struct.db — кандидат на ручной триаж.')
    L.append('')
    for sec in data['sections']:
        n = len(sec['mentions'])
        mark = '' if n else '⚪ '
        L.append(f"## {mark}{sec['path']}" + (f" — {n} привязок" if n else ''))
        for full_name, info in sorted(sec['mentions'].items()):
            ctx = (info['contexts'][0] if info['contexts'] else '')[:70]
            L.append(f"- `{full_name}` ({info['by']}) — …{ctx}…")
        L.append('')
    return '\n'.join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--html', help='локальный HTML-файл со страницы ITS')
    src.add_argument('--url', help='URL страницы ITS (скачивается автоматически)')
    ap.add_argument('--db', default=str(_HERE / 'data' / 'rel.db'),
                    help='rel.db (по умолчанию data/rel.db рядом со скриптом)')
    ap.add_argument('--struct-db',
                    default=str(_HERE.parent / 'struct' / 'data' / 'struct.db'),
                    help='struct.db для линковки (по умолчанию ../struct/data/struct.db)')
    ap.add_argument('--version', help='принудительно указать версию (если авто не сработала)')
    ap.add_argument('--md', help='отчёт в markdown')
    ap.add_argument('--json', help='результат в json')
    args = ap.parse_args(argv)

    if args.url:
        html_text = fetch_url(args.url)
        source_ref = args.url
    else:
        source_ref = str(Path(args.html).resolve())
        raw = Path(args.html).read_bytes()
        html_text = None
        for enc in ('utf-8', 'utf-8-sig', 'cp1251'):
            try:
                html_text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if html_text is None:
            html_text = raw.decode('utf-8', errors='replace')

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    data = ingest(html_text, args.db, args.struct_db, source_ref,
                  forced_version=args.version)
    md = report_md(data)
    if args.md:
        Path(args.md).write_text(md, encoding='utf-8')
    if args.json:
        slim = {k: v for k, v in data.items() if k != 'sections'}
        slim['sections'] = [
            {'path': s['path'], 'title': s['title'], 'n_links': len(s['mentions'])}
            for s in data['sections']]
        Path(args.json).write_text(json.dumps(slim, ensure_ascii=False, indent=2),
                                   encoding='utf-8')
    print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
