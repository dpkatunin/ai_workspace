"""
answer_guard.py — пост-процессор ответов LLM для проекта unf30-kb. v1.1

Задача: перед показом ответа вытащить кандидатов в полные имена 1С
(Документ.ЗаказПокупателя, Справочник.Номенклатура, Подсистема.Продажи...)
и проверить их по STRUCT SQLite.

v1.1 — иерархическая проверка глубоких путей (3+ сегмента):
  Объект.Реквизит            -> known (реквизит подтверждён по attributes)
  Перечисление.Х.Значение    -> known (значение подтверждено по enum_values)
  Объект.ТЧ.Реквизит         -> known (цепочка по tabular_sections + attributes)
  Объект.<нечто> без подтверждения -> warn (объект есть, хвост не проверен:
                                 формы и прочее, чего нет в STRUCT)
  Ничего не нашлось          -> unknown (кандидат на галлюцинацию)
--strict даёт exit 2 ТОЛЬКО при unknown; warn не блокирует.

Зависимости: только stdlib. MCP не требуется — читаем struct.db напрямую.

Примеры:
  python answer_guard.py --db data/struct.db --input draft.md --annotate
  type draft.md | python answer_guard.py --db data/struct.db --input - --strict
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

KINDS = (
    'Константа', 'Справочник', 'Документ', 'ЖурналДокументов',
    'Отчет', 'Обработка', 'РегистрСведений', 'РегистрНакопления',
    'РегистрБухгалтерии', 'РегистрРасчета', 'Перечисление', 'ОбщийМодуль',
    'ОбщаяКоманда', 'ОбщаяФорма', 'ОбщаяКартинка', 'Роль',
    'ФункциональнаяОпция', 'ОпределяемыйТип', 'ПодпискаНаСобытие',
    'РегламентноеЗадание', 'ПланСчетов', 'ПланВидовХарактеристик',
    'ПланВидовРасчета', 'БизнесПроцесс', 'Задача', 'Подсистема',
)
WORD = r'[A-Za-zА-Яа-яЁё0-9_]+'
CAND_RE = re.compile(
    r'(?<![\w.])(?:' + '|'.join(KINDS) + r')\.' + WORD + r'(?:\.' + WORD + r')*(?!\w)'
)
TRAILING = '.,);:]}>"»”\''


def norm_candidate(s: str) -> str:
    return s.strip().rstrip(TRAILING)


def extract_candidates(text: str):
    seen = set()
    out = []
    for m in CAND_RE.finditer(text):
        full = norm_candidate(m.group(0))
        if full and full not in seen:
            seen.add(full)
            out.append(full)
    return out


def load_objects(db_path: Path, full_names):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        found = {}
        batch = 500
        for i in range(0, len(full_names), batch):
            part = full_names[i:i + batch]
            marks = ','.join('?' for _ in part)
            rows = conn.execute(
                f"""SELECT full_name, kind, name, synonym, subsystem, subsystem_path
                    FROM objects WHERE full_name IN ({marks})""",
                part,
            ).fetchall()
            for r in rows:
                found[r['full_name']] = dict(r)
        return found, conn
    except Exception:
        conn.close()
        raise


def suggest(conn, full_name: str, limit: int = 3):
    tail = full_name.split('.')[-1]
    if not tail:
        return []
    like = f'%{tail}%'
    kind = full_name.split('.')[0]

    # Подсказки только того же вида: Справочник → Справочник, Документ → Документ.
    # Широкий fallback по всем kind даёт шум вида Роль.*Товары* для Справочник.Товары.
    rows = conn.execute(
        """SELECT full_name, kind, synonym, subsystem
           FROM objects
           WHERE kind = ? AND (name LIKE ? OR synonym LIKE ? OR full_name LIKE ?)
           ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, length(full_name)
           LIMIT ?""",
        (kind, like, like, like, tail, limit),
    ).fetchall()
    return [dict(r) for r in rows]

# --- v1.1: иерархическая проверка глубоких путей -------------------------

def _fk_col(conn, table: str, *options: str):
    """Первое существующее имя FK-колонки таблицы (как _col в struct_mcp)."""
    try:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
    except sqlite3.Error:
        return None
    for opt in options:
        if opt in cols:
            return opt
    return None


def _object_row(conn, full_name: str):
    return conn.execute('SELECT * FROM objects WHERE full_name = ?', (full_name,)).fetchone()


def _enum_value_ok(conn, enum_row, value: str) -> bool:
    fk = _fk_col(conn, 'enum_values', 'enum_id', 'object_id', 'owner_id')
    if not fk:
        return False
    return conn.execute(
        f'SELECT 1 FROM enum_values WHERE {fk} = ? AND name = ? LIMIT 1',
        (enum_row['id'], value)).fetchone() is not None


def _attr_ok(conn, object_id, name: str) -> bool:
    fk = _fk_col(conn, 'attributes', 'object_id', 'obj_id', 'owner_id')
    if not fk:
        return False
    return conn.execute(
        f'SELECT 1 FROM attributes WHERE {fk} = ? AND name = ? LIMIT 1',
        (object_id, name)).fetchone() is not None


def _ts_ok(conn, object_id, name: str) -> bool:
    fk = _fk_col(conn, 'tabular_sections', 'object_id', 'obj_id', 'owner_id')
    if not fk:
        return False
    return conn.execute(
        f'SELECT 1 FROM tabular_sections WHERE {fk} = ? AND name = ? LIMIT 1',
        (object_id, name)).fetchone() is not None


def resolve_deep(conn, cand: str):
    """Глубокий путь Вид.Имя.<хвост>: ищем самый длинный префикс-объект и
    проверяем хвост (значение перечисления / реквизит / ТЧ.Реквизит).

    Возвращает (status, object_dict|None, tail):
      'enum-value' | 'attribute' | 'tail-miss' | 'unknown'."""
    segs = [p for p in cand.split('.') if p]
    for cut in range(len(segs) - 1, 1, -1):
        prefix = '.'.join(segs[:cut])
        row = _object_row(conn, prefix)
        if not row:
            continue
        obj = dict(row)
        tail = segs[cut:]
        if obj.get('kind') == 'Перечисление' and len(tail) == 1:
            ok = _enum_value_ok(conn, row, tail[0])
            return ('enum-value' if ok else 'tail-miss'), obj, '.'.join(tail)
        owner = row['id']
        for i, seg in enumerate(tail):
            if _attr_ok(conn, owner, seg):
                continue  # реквизит объекта/ТЧ
            if i < len(tail) - 1 and _ts_ok(conn, owner, seg):
                continue  # промежуточная табличная часть
            return 'tail-miss', obj, '.'.join(tail)
        return 'attribute', obj, '.'.join(tail)
    return 'unknown', None, '.'.join(segs[2:])


def guard(text: str, db_path: Path, do_suggest: bool = True):
    candidates = extract_candidates(text)
    if not candidates:
        return {'candidates': [], 'known': [], 'warn': [], 'unknown': []}, None

    found, conn = load_objects(db_path, candidates)
    try:
        known, warn, unknown = [], [], []
        for name in candidates:
            row = found.get(name)
            if row:
                row = dict(row)
                row['matched_as'] = name
                known.append(row)
                continue
            status, obj, tail = resolve_deep(conn, name)
            if status in ('enum-value', 'attribute'):
                obj = dict(obj)
                obj['matched_as'] = name
                obj['via'] = status
                obj['tail'] = tail
                known.append(obj)
            elif status == 'tail-miss':
                warn.append({'full_name': name,
                             'object': obj['full_name'],
                             'tail': tail})
            else:
                item = {'full_name': name}
                if do_suggest:
                    item['suggestions'] = suggest(conn, name)
                unknown.append(item)
        return {'candidates': candidates, 'known': known,
                'warn': warn, 'unknown': unknown}, conn
    finally:
        conn.close()


def annotation_md(report) -> str:
    lines = ['', '---', '### validate_names (STRUCT)']
    unk = report['unknown']
    warn = report.get('warn') or []
    if not unk and not warn:
        lines.append(f"Проверено имён: {len(report['candidates'])}; неизвестных нет.")
        return '\n'.join(lines)
    lines.append(
        f"Проверено имён: {len(report['candidates'])}; "
        f"**неизвестных: {len(unk)}**; с оговорками: {len(warn)}."
    )
    for item in warn:
        lines.append(
            f"- `~ {item['full_name']}` — объект `{item['object']}` существует, "
            f"хвост «{item['tail']}» не подтверждён (нет в STRUCT или опечатка)"
        )
    for item in unk:
        lines.append(f"- `? {item['full_name']}` — в objects.full_name не найдено")
        for s in item.get('suggestions') or []:
            lines.append(
                f"  - похожее: `{s['full_name']}` ({s.get('kind')}, {s.get('subsystem') or 'без подсистемы'})"
            )
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description='Проверка ПолноеИмя в ответе LLM по struct.db')
    ap.add_argument('--db', required=True, help='Путь к struct.db')
    ap.add_argument('--input', required=True, help='Файл с черновиком ответа или - для stdin')
    ap.add_argument('--output', help='Куда писать JSON-отчёт; по умолчанию stdout')
    ap.add_argument('--annotate', action='store_true', help='Вывести Markdown = черновик + блок validate_names')
    ap.add_argument('--strict', action='store_true', help='Exit code 2, если есть unknown')
    ap.add_argument('--no-suggest', action='store_true', help='Не искать похожие имена для unknown')
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == '-' else Path(args.input).read_text(encoding='utf-8')
    report, _ = guard(raw, Path(args.db), do_suggest=not args.no_suggest)

    if args.annotate:
        sys.stdout.write(raw.rstrip() + annotation_md(report) + '\n')
    else:
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(payload + '\n', encoding='utf-8')
        else:
            sys.stdout.write(payload + '\n')

    return 2 if (args.strict and report['unknown']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
