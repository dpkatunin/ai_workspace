r"""
kb_lint.py — линт KB-карточек по struct.db. Этап 0 «скелета KB» (2026-11-07).

Зачем: KB — это 43 эссе-карточки (kb/unf30/*.md). Пока скелет (frontmatter
с якорями, verify_kb) не построен, этот скрипт даёт программную проверку
«как есть»: прогоняет answer_guard по КАЖДОЙ карточке и показывает, какие
ПолныеИмена в тексте НЕ резолвятся в текущую конфигурацию.

Это одновременно:
  1. аудит гнили (мёртвые имена в карточках после смены релиза);
  2. выборка для миграции: карточки с unknown — первые кандидаты
     на простановку structured-якорей на этапе 2.

Скелет НЕ нужен для работы скрипта — он читает прозу как текст.

Зависимости: stdlib + answer_guard.py (должен лежать рядом, в той же папке).

Запуск (из корня workspace):
  .venv\Scripts\python.exe -X utf8 projects/unf30-kb/struct/kb_lint.py \
      --db projects/unf30-kb/struct/data/struct.db \
      --kb kb/unf30 \
      --md kb_lint_report.md --json kb_lint_report.json

Exit code: 0 — отчёт построен (даже если unknown есть; это отчёт, а не валидатор).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer_guard as ag  # noqa: E402


def iter_cards(kb_dir: Path):
    for p in sorted(kb_dir.rglob('*.md')):
        try:
            yield p, p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                yield p, p.read_text(encoding='utf-8-sig')
            except UnicodeDecodeError:
                yield p, p.read_text(encoding='cp1251')


def lint(kb_dir: Path, db_path: Path, suggest: bool = True):
    files = []
    totals = {'files': 0, 'clean': 0, 'with_warn': 0, 'with_unknown': 0,
              'candidates': 0, 'known': 0, 'warn': 0, 'unknown': 0}
    for path, text in iter_cards(kb_dir):
        report, _ = ag.guard(text, db_path, do_suggest=suggest)
        rel = str(path)
        entry = {
            'file': rel,
            'candidates': len(report['candidates']),
            'known': len(report['known']),
            'warn': report['warn'],
            'unknown': report['unknown'],
        }
        files.append(entry)
        totals['files'] += 1
        totals['candidates'] += entry['candidates']
        totals['known'] += entry['known']
        totals['warn'] += len(report['warn'])
        totals['unknown'] += len(report['unknown'])
        if report['unknown']:
            totals['with_unknown'] += 1
        elif report['warn']:
            totals['with_warn'] += 1
        else:
            totals['clean'] += 1
    return {'totals': totals, 'files': files}


def report_md(data):
    t = data['totals']
    L = ['# KB-линт: карточки против struct.db', '',
         f"- карточек: {t['files']} (чистых: {t['clean']}, "
         f"с warn: {t['with_warn']}, с unknown: {t['with_unknown']})",
         f"- имён проверено: {t['candidates']} "
         f"(known {t['known']}, warn {t['warn']}, **unknown {t['unknown']}**)", '',
         '_unknown = ПолноеИмя из карточки не найдено в текущей конфигурации. '
         'Это гниль (устаревшее/выдуманное имя) или имя из другой конфигурации '
         '(УТ/ERP). Точку решает человек; похожие имена подсказаны._', '']

    def _file_block(e, title):
        L.append(f"### `{e['file']}`")
        L.append(f"_{title}: {len(e['unknown']) if title == 'unknown' else len(e['warn'])}_")
        for item in (e['unknown'] if title == 'unknown' else e['warn']):
            if title == 'unknown':
                L.append(f"- `? {item['full_name']}` — не найдено в objects.full_name")
                for s in item.get('suggestions') or []:
                    L.append(f"  - похожее: `{s['full_name']}` "
                             f"({s.get('kind')}, {s.get('subsystem') or 'без подсистемы'})")
            else:
                L.append(f"- `~ {item['full_name']}` — объект `{item['object']}` есть, "
                         f"хвост «{item['tail']}» не подтверждён")
        L.append('')

    unk_files = [e for e in data['files'] if e['unknown']]
    if unk_files:
        L += ['## 🔴 unknown (гнить — проверить первой)', '']
        for e in unk_files:
            _file_block(e, 'unknown')
    wrn_files = [e for e in data['files'] if e['warn'] and not e['unknown']]
    if wrn_files:
        L += ['## 🟡 warn (объект есть, хвост не подтверждён)', '']
        for e in wrn_files:
            _file_block(e, 'warn')
    L += ['## ✅ чистые карточки', '']
    L += [f"- `{e['file']}`" for e in data['files']
          if not e['unknown'] and not e['warn']]
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description='Линт KB-карточек по struct.db')
    ap.add_argument('--db', required=True, help='Путь к struct.db')
    ap.add_argument('--kb', required=True, help='Папка с карточками KB (kb/unf30)')
    ap.add_argument('--md', help='Markdown-отчёт (по умолчанию stdout)')
    ap.add_argument('--json', dest='json_out', help='JSON-отчёт')
    ap.add_argument('--no-suggest', action='store_true',
                    help='Не искать похожие имена (быстрее)')
    args = ap.parse_args()

    kb_dir = Path(args.kb)
    if not kb_dir.is_dir():
        sys.stderr.write(f'Папка не найдена: {kb_dir}\n')
        return 1

    data = lint(kb_dir, Path(args.db), suggest=not args.no_suggest)
    md = report_md(data)
    if args.md:
        Path(args.md).write_text(md + '\n', encoding='utf-8')
    else:
        sys.stdout.write(md + '\n')
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
