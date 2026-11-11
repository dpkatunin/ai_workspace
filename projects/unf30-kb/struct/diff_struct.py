r"""
diff_struct.py — механический дифф двух struct.db: старый релиз vs новый. v1.0

Зачем: при выходе нового релиза УНФ конфигурацию выгружают заново и пересобирают
struct.db полной заменой. Этот скрипт сравнивает архивную БД старого релиза
с новой и отвечает на вопрос «ЧТО изменилось механически»:
  - какие объекты добавлены / удалены;
  - какие, похоже, переименованы (совпадение вида + похожего имени/синонима);
  - у каких изменились поля (kind, синоним, подсистема);
  - изменения реквизитов у существующих объектов;
  - изменения движений документов и значений перечислений.

Семантику («зачем и что это значит») этот скрипт НЕ даёт — её несёт описание
изменений релиза (будущий слой REL). Вместе: diff_struct = ЧТО, REL = ЗАЧЕМ.

Зависимости: только stdlib. Схему читает адаптивно (PRAGMA), как answer_guard:
если таблицы/колонки нет — секция отчёта пропускается с пометкой, не падает.

Запуск (из корня workspace):
  .venv\Scripts\python.exe -X utf8 projects/unf30-kb/struct/diff_struct.py \
      --old projects/unf30-kb/struct/data/struct_3.0.OLD.db \
      --new projects/unf30-kb/struct/data/struct.db \
      --md report_diff.md --json report_diff.json

Exit code: всегда 0 (это аналитический инструмент, а не валидатор).
"""
import argparse
import json
import sqlite3
import sys
from difflib import SequenceMatcher
from pathlib import Path

# Поля objects, которые участвуют в сравнении (id/config_id — технические, пропускаем)
COMPARE_FIELDS = ('kind', 'name', 'synonym', 'subsystem', 'subsystem_path')


def _cols(conn, table):
    try:
        return [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]
    except sqlite3.Error:
        return []


def _has(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def load_objects(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('SELECT * FROM objects').fetchall()
        return {r['full_name']: dict(r) for r in rows}
    finally:
        conn.close()


def diff_objects(old, new):
    old_names, new_names = set(old), set(new)
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)
    common = old_names & new_names

    field_changes = []
    for name in sorted(common):
        diffs = {}
        for f in COMPARE_FIELDS:
            if f not in old[name] or f not in new[name]:
                continue
            if (old[name].get(f) or '') != (new[name].get(f) or ''):
                diffs[f] = {'old': old[name].get(f), 'new': new[name].get(f)}
        if diffs:
            field_changes.append({'full_name': name, 'changes': diffs})

    return added, removed, field_changes


def rename_candidates(old, new, added, removed, limit=5):
    """Удалённые × добавленные того же вида с похожим именем или равным синонимом."""
    by_kind_added = {}
    for n in added:
        by_kind_added.setdefault(new[n].get('kind'), []).append(n)
    pairs = []
    for r in removed:
        ro = old[r]
        kind = ro.get('kind')
        cands = []
        for a in by_kind_added.get(kind, []):
            na = new[a]
            score = SequenceMatcher(None, ro.get('name') or '', na.get('name') or '').ratio()
            syn_eq = (ro.get('synonym') or '') == (na.get('synonym') or '') != ''
            if score >= 0.7 or (syn_eq and score >= 0.3):
                cands.append((score, a))
        cands.sort(reverse=True)
        if cands:
            pairs.append({'removed': r, 'candidates': [
                {'full_name': a, 'score': round(s, 2)} for s, a in cands[:limit]]})
    return pairs


def _fk_col(conn, table, *options):
    cols = set(_cols(conn, table))
    for opt in options:
        if opt in cols:
            return opt
    return None


def diff_children(conn_old, conn_new, table, child_name_col='name',
                  parent_fk_options=('object_id', 'obj_id', 'owner_id'),
                  cap=40):
    """Сравнение состава дочерних строк (attributes/enum_values) по общим объектам.

    Возвращает список {full_name, added[], removed[], counts:{old,new}}."""
    if not (_has(conn_old, table) and _has(conn_new, table)):
        return None
    fk_old = _fk_col(conn_old, table, *parent_fk_options)
    fk_new = _fk_col(conn_new, table, *parent_fk_options)
    if not fk_old or not fk_new or child_name_col not in _cols(conn_old, table):
        return None

    def index(conn, fk):
        idx = {}
        for oid, name in conn.execute(f'SELECT {fk}, {child_name_col} FROM {table}'):
            idx.setdefault(oid, set()).add(name)
        return idx

    def name_of(conn, oid):
        row = conn.execute('SELECT full_name FROM objects WHERE id = ?', (oid,)).fetchone()
        return row[0] if row else f'id:{oid}'

    io_, in_ = index(conn_old, fk_old), index(conn_new, fk_new)
    rows = []
    for oid in sorted(set(io_) & set(in_)):
        added = sorted(in_[oid] - io_[oid])
        removed = sorted(io_[oid] - in_[oid])
        if added or removed:
            rows.append({
                'full_name': name_of(conn_new, oid),
                'added': added[:cap], 'removed': removed[:cap],
                'added_total': len(added), 'removed_total': len(removed),
                'counts': {'old': len(io_[oid]), 'new': len(in_[oid])},
            })
    return rows


def load_moves(db_path):
    """Движения документов: {document_full_name: set(register_full_name)}.
    Адаптивно: ищем FK на objects и текстовую колонку с именем регистра."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _has(conn, 'movements'):
            return None
        fk = _fk_col(conn, 'movements', 'object_id', 'obj_id', 'owner_id', 'from_object_id')
        cols = _cols(conn, 'movements')
        reg_col = next((c for c in cols if c in
                        ('to_full_name', 'register_full_name', 'register', 'target_full_name')), None)
        if not fk or not reg_col:
            return None
        idx = {}
        for r in conn.execute(f'SELECT {fk} AS oid, {reg_col} AS reg FROM movements'):
            idx.setdefault(r['oid'], set()).add(r['reg'])
        out = {}
        for oid, regs in idx.items():
            row = conn.execute('SELECT full_name FROM objects WHERE id = ?', (oid,)).fetchone()
            if row:
                out[row['full_name']] = regs
        return out
    finally:
        conn.close()


def diff_moves(old_path, new_path):
    mo, mn = load_moves(old_path), load_moves(new_path)
    if mo is None or mn is None:
        return None
    rows = []
    for doc in sorted(set(mo) | set(mn)):
        added = sorted(mn.get(doc, set()) - mo.get(doc, set()))
        removed = sorted(mo.get(doc, set()) - mn.get(doc, set()))
        if added or removed:
            rows.append({'document': doc, 'added_registers': added,
                         'removed_registers': removed})
    return rows


def build_report(old_path, new_path):
    old, new = load_objects(old_path), load_objects(new_path)
    added, removed, field_changes = diff_objects(old, new)
    renames = rename_candidates(old, new, added, removed)

    conn_old = sqlite3.connect(old_path)
    conn_new = sqlite3.connect(new_path)
    try:
        attrs = diff_children(conn_old, conn_new, 'attributes')
        enums = diff_children(conn_old, conn_new, 'enum_values',
                            parent_fk_options=('enum_id', 'object_id', 'obj_id', 'owner_id'))
    finally:
        conn_old.close()
        conn_new.close()
    moves = diff_moves(old_path, new_path)

    def by_subsystem(names):
        idx = {}
        for n in names:
            idx.setdefault(new.get(n, old.get(n, {})).get('subsystem') or 'без подсистемы', []).append(n)
        return {k: sorted(v) for k, v in sorted(idx.items())}

    return {
        'meta': {
            'old_db': str(old_path), 'new_db': str(new_path),
            'objects': {'old': len(old), 'new': len(new),
                        'added': len(added), 'removed': len(removed),
                        'field_changed': len(field_changes)},
        },
        'added_by_subsystem': by_subsystem(added),
        'removed_by_subsystem': by_subsystem(removed),
        'renamed_candidates': renames,
        'field_changes': field_changes,
        'attribute_changes': attrs,
        'enum_changes': enums,
        'movement_changes': moves,
    }


def _fmt_section(title, lines):
    return ['', f'## {title}', ''] + (lines or ['(нет данных)'])


def report_md(rep):
    m = rep['meta']['objects']
    L = ['# Дифф STRUCT: механические изменения конфигурации', '',
         f"- объектов: было {m['old']} → стало {m['new']}",
         f"- добавлено: **{m['added']}**, удалено: **{m['removed']}**, "
         f"с изменёнными полями: {m['field_changed']}", '',
         '_Семантика («зачем») — в описании изменений релиза (слой REL). '
         'Этот отчёт — только «что»._', '']

    for title, key in (('Новые объекты (по подсистемам)', 'added_by_subsystem'),
                     ('Удалённые объекты (по подсистемам)', 'removed_by_subsystem')):
        lines = []
        for sub, names in rep[key].items():
            lines.append(f'**{sub}** — {len(names)}:')
            lines += [f'- `{n}`' for n in names]
        L += _fmt_section(title, lines)

    lines = []
    for p in rep['renamed_candidates']:
        c = '; '.join(f"`{c['full_name']}` ({c['score']})" for c in p['candidates'])
        lines.append(f"- `{p['removed']}` → {c}")
    L += _fmt_section('Кандидаты на переименование (проверить глазами)', lines)

    lines = []
    for ch in rep['field_changes']:
        parts = [f"{f}: «{v['old']}» → «{v['new']}»" for f, v in ch['changes'].items()]
        lines.append(f"- `{ch['full_name']}` — {'; '.join(parts)}")
    L += _fmt_section('Изменённые поля объектов', lines)

    if rep['attribute_changes'] is None:
        L += _fmt_section('Реквизиты', ['(таблица attributes не найдена или схема не распознана)'])
    else:
        lines = []
        for r in rep['attribute_changes'][:200]:
            a = f"+{r['added_total']} ({', '.join(r['added'][:5])})" if r['added'] else ''
            rm = f"-{r['removed_total']} ({', '.join(r['removed'][:5])})" if r['removed'] else ''
            lines.append(f"- `{r['full_name']}`: {a} {rm}".replace('  ', ' '))
        L += _fmt_section(f'Изменения реквизитов ({len(rep["attribute_changes"])} объектов)', lines)

    if rep['enum_changes'] is not None:
        lines = [f"- `{r['full_name']}`: +{r['added_total']}, -{r['removed_total']}"
                 for r in rep['enum_changes'][:100]]
        L += _fmt_section(f'Изменения значений перечислений ({len(rep["enum_changes"])})', lines)

    if rep['movement_changes'] is None:
        L += _fmt_section('Движения документов', ['(таблица movements не найдена или схема не распознана)'])
    else:
        lines = []
        for r in rep['movement_changes'][:200]:
            a = ', '.join(f'`{x}`' for x in r['added_registers'][:5])
            rm = ', '.join(f'`{x}`' for x in r['removed_registers'][:5])
            lines.append(f"- `{r['document']}`: + [{a}] − [{rm}]")
        L += _fmt_section(f'Изменения движений ({len(rep["movement_changes"])} документов)', lines)
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description='Дифф двух struct.db')
    ap.add_argument('--old', required=True, help='БД старого релиза (архив)')
    ap.add_argument('--new', required=True, help='БД нового релиза (текущая)')
    ap.add_argument('--md', help='Markdown-отчёт (по умолчанию stdout)')
    ap.add_argument('--json', dest='json_out', help='JSON-отчёт')
    args = ap.parse_args()

    rep = build_report(Path(args.old), Path(args.new))
    md = report_md(rep)
    if args.md:
        Path(args.md).write_text(md + '\n', encoding='utf-8')
    else:
        sys.stdout.write(md + '\n')
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(rep, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
