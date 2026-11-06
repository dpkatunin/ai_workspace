"""
answer_guard.py — пост-процессор ответов LLM для проекта unf30-kb.

Задача: перед показом ответа вытащить кандидатов в полные имена 1С
(Документ.ЗаказПокупателя, Справочник.Номенклатура, Подсистема.Продажи...)
и проверить их по STRUCT SQLite objects.full_name.

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

def guard(text: str, db_path: Path, do_suggest: bool = True):
    candidates = extract_candidates(text)
    if not candidates:
        return {'candidates': [], 'known': [], 'unknown': []}, None

    found, conn = load_objects(db_path, candidates)
    try:
        known, unknown = [], []
        for name in candidates:
            row = found.get(name)
            if row:
                known.append(row)
            else:
                item = {'full_name': name}
                if do_suggest:
                    item['suggestions'] = suggest(conn, name)
                unknown.append(item)
        return {'candidates': candidates, 'known': known, 'unknown': unknown}, conn
    finally:
        conn.close()


def annotation_md(report) -> str:
    lines = ['', '---', '### validate_names (STRUCT)']
    unk = report['unknown']
    if not unk:
        lines.append(f"Проверено имён: {len(report['candidates'])}; неизвестных нет.")
        return '\n'.join(lines)
    lines.append(f"Проверено имён: {len(report['candidates'])}; **неизвестных: {len(unk)}**.")
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
