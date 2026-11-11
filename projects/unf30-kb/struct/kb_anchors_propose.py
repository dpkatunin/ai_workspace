r"""kb_anchors_propose.py — предлагает объекты УНФ (якоря) для скелета карточек KB.

Идея: текст карточек уже содержит русские синонимы объектов («заказ покупателя»,
«номенклатура»). Скрипт строит индекс ПолноеИмя -> синоним/имя из struct.db,
ищет упоминания в теле карточек и предлагает, что внести в objects[] фронтматтера.

Статусы:
  ➕ — предлагается (в тексте есть, в скелете нет)
  ✅ — уже есть в скелете
  —  — предложение пропущено (отсеклись лимитами/стоп-словами)

Человек просматривает предложения и вручную вписывает принятые якоря в
frontmatter карточки. Автозапись НЕ делается намеренно: предложение — не факт.

Зависимости: только стандартная библиотека Python 3.10+. БД — struct.db
(таблица objects с колонками full_name, name, kind, synonym).

Запуск:
    python kb_anchors_propose.py --db data/struct.db --kb ../../kb/unf30 --md proposals.md
    python kb_anchors_propose.py --db data/struct.db --kb ../../kb/unf30 --json proposals.json
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

MIN_PHRASE = 4          # минимальная длина фразы-индекса (символы)
MAX_NGRAM = 4           # максимальный размер n-граммы (слова)
CAP_PER_CARD = 12       # предложений на карточку (по убыванию веса)
GENERIC = {'отчет', 'обработка', 'документ', 'справочник', 'регистр', 'константа'}
# стоп-слова-виды: упоминание «документ» само по себе не якорь

TOKEN_RE = re.compile(r'[a-zа-яё0-9]+')

# суффиксы русских падежных форм: «номенклатуру»->«номенклатур», «заказа»->«заказ».
# Стемминг применяем к КАЖДОМУ слову фразы — и при индексации, и при поиске,
# поэтому ложных рассогласований нет. Грубо, но для предложений (не фактов) —
# достаточно: человек всё равно просматривает результат.
_ENDINGS = ('иями', 'иям', 'иях', 'ия', 'ами', 'ями', 'ах', 'ях', 'ам', 'ям',
            'ого', 'его', 'ому', 'ему', 'ой', 'ый', 'ий', 'ая', 'ое', 'ые',
            'ов', 'ев', 'ей', 'ью', 'ия', 'ие', 'ии', 'ь', 'ю', 'у', 'а',
            'ы', 'е', 'и', 'о')


def stem(word):
    w = word.lower().replace('ё', 'е')
    if len(w) <= 4:
        return w
    for suf in _ENDINGS:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def norm(s):
    return (s or '').lower().replace('ё', 'е').strip()


def norm_stemmed(s):
    """Фраза нормализованная, каждое слово пропущено через stem()."""
    return ' '.join(stem(t) for t in TOKEN_RE.findall(norm(s)))


def load_phrase_index(db_path):
    """Синоним/имя -> [{full_name, kind, by}] только для фраз достаточной длины."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT full_name, name, kind, synonym FROM objects"
    ).fetchall()
    conn.close()
    idx = {}
    for full_name, name, kind, synonym in rows:
        for phrase, by in ((synonym, 'synonym'), (name, 'name')):
            p = norm_stemmed(phrase)
            if len(p) < MIN_PHRASE or p in GENERIC:
                continue
            idx.setdefault(p, []).append(
                {'full_name': full_name, 'kind': kind, 'by': by})
    return idx


def frontmatter_objects(raw):
    """Вытащить objects[] из фронтматтера (простой парсер, без yaml)."""
    m = re.match(r'^---\n(.*?)\n---\n', raw, re.S)
    if not m:
        return set()
    meta = m.group(1)
    in_objects = False
    out = set()
    for line in meta.splitlines():
        if re.match(r'^objects\s*:', line):
            in_objects = True
            tail = line.split(':', 1)[1].strip()
            if tail.startswith('[') and tail.endswith(']'):
                inner = tail[1:-1].strip().strip('"\'')
                if inner:
                    out.add(inner)
                in_objects = False
            continue
        if in_objects:
            if re.match(r'^\s*-\s+', line):
                out.add(line.split('-', 1)[1].strip().strip('"\''))
            else:
                in_objects = False
    return out


def body_text(raw):
    """Тело карточки без фронтматтера."""
    m = re.match(r'^---\n.*?\n---\n', raw, re.S)
    return raw[m.end():] if m else raw


def find_mentions(text, idx):
    """Токенизировать текст, найти n-граммы (MAX_NGRAM->1), совпадающие с индексом.

    Возвращает {full_name: {by, n_words, contexts[]}}. Берётся самое длинное
    совпадение: после совпадения на i..e указатель прыгает на e (longest-match).
    """
    raw_tokens = TOKEN_RE.findall(norm(text))
    stems = [stem(t) for t in raw_tokens]
    found = {}
    i = 0
    while i < len(stems):
        hit = None
        hit_span = None
        for n in range(min(MAX_NGRAM, len(stems) - i), 0, -1):
            gram = ' '.join(stems[i:i + n])
            if gram in idx:
                hit = idx[gram]
                hit_span = (i, i + n)
                break
        if hit:
            s, e = hit_span
            ctx = ' '.join(raw_tokens[max(0, s - 4):e + 4])
            for rec in hit:
                cur = found.setdefault(rec['full_name'], {
                    'by': rec['by'], 'n_words': e - s, 'contexts': []})
                # приоритет synonym (вес 2) над name (вес 1)
                if rec['by'] == 'synonym':
                    cur['by'] = 'synonym'
                if ctx not in cur['contexts']:
                    cur['contexts'].append(ctx)
            i = e                                  # longest-match: не пересекаемся
        else:
            i += 1
    return found


def propose(kb_dir, db_path):
    idx = load_phrase_index(db_path)
    cards = []
    for path in sorted(Path(kb_dir).rglob('*.md')):
        raw = path.read_text(encoding='utf-8', errors='replace')
        existing = frontmatter_objects(raw)
        found = find_mentions(body_text(raw), idx)
        props = []
        for full_name, info in found.items():
            status = 'ok' if full_name in existing else 'new'
            props.append({
                'full_name': full_name,
                'status': status,
                'by': info['by'],
                'n_words': info['n_words'],
                'context': (info['contexts'][0] + ' …') if info['contexts'] else '',
            })
        # новые сначала, затем по длине фразы (синоним раньше имени)
        props.sort(key=lambda p: (
            p['status'] != 'new', -p['n_words'], p['by'] != 'synonym'))
        cards.append({'file': str(path), 'existing': sorted(existing),
                      'proposals': props[:CAP_PER_CARD],
                      'total_found': len(props)})
    return cards


def report_md(cards):
    L = []
    L.append('# kb_anchors_propose: предложения якорей для карточек KB')
    total_new = sum(1 for c in cards for p in c['proposals'] if p['status'] == 'new')
    L.append(f'- карточек просмотрено: {len(cards)}; предложений (➕ новых): **{total_new}**')
    L.append('')
    L.append('Легенда: ➕ = предлагается в objects[]; ✅ = уже в скелете;')
    L.append('by: synonym = совпало по синониму, name = по имени объекта.')
    L.append('')
    for c in cards:
        if not c['proposals']:
            continue
        L.append(f"## `{Path(c['file']).name}`")
        if c['existing']:
            L.append(f"уже в скелете: {', '.join(f'`{o}`' for o in c['existing'])}")
        L.append('')
        L.append('| ПолноеИмя (by) | статус | контекст |')
        L.append('|---|---|---|')
        for p in c['proposals']:
            mark = '✅' if p['status'] == 'ok' else '➕'
            L.append(f"| `{p['full_name']}` ({p['by']}) | {mark} | {p['context'][:80]} |")
        L.append('')
    return '\n'.join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True, help='путь к struct.db')
    ap.add_argument('--kb', required=True, help='папка с карточками KB')
    ap.add_argument('--md', help='выгрузить отчёт в markdown')
    ap.add_argument('--json', help='выгрузить результат в json')
    args = ap.parse_args(argv)

    cards = propose(args.kb, args.db)
    md = report_md(cards)
    if args.md:
        Path(args.md).write_text(md, encoding='utf-8')
    if args.json:
        Path(args.json).write_text(
            json.dumps(cards, ensure_ascii=False, indent=2), encoding='utf-8')
    print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
