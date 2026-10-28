#!/usr/bin/env python3
"""
migrate_synonyms.py — миграция синонимов из _meta/by-synonym.md в YAML-фронтматтер карточек.

По умолчанию работает в режиме инспекции: ничего не пишет, только показывает план.
Запись — только по --apply.

Режимы:
  --inspect   показать, что найдено в by-synonym.md и что будет вставлено
  --dry-run   показать diff для каждой карточки (по умолчанию)
  --apply     записать изменения в файлы

Дополнительно:
  --force     перезаписать synonyms, если поле уже есть и отличается
  --repo PATH путь к корню репозитория (по умолчанию — поиск вверх от cwd)

Процедура безопасной миграции:
  1. git commit -am "before synonyms migration"
  2. python tools/migrate_synonyms.py --inspect
  3. python tools/migrate_synonyms.py --dry-run | less
  4. python tools/migrate_synonyms.py --apply
  5. python tools/build_indexes.py --dry-run   # сверить с ручным by-synonym.md
  6. git commit -am "migrate synonyms to frontmatter"
"""
from __future__ import annotations

import argparse
import difflib
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.frontmatter import (  # noqa: E402
    insert_block_after_key,
    parse,
    rebuild,
    render_list_block,
    split,
)
from lib.synonyms_parser import parse_by_synonym  # noqa: E402

def find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for _ in range(10):
        if (p / "_meta").is_dir() and (p / "kb").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    raise RuntimeError(f"could not find repo root (with _meta/ and kb/) from {start}")

def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def warn(msg: str) -> None:
    print(f"WARN:  {msg}", file=sys.stderr)

def info(msg: str) -> None:
    print(msg)

def load_cards(kb_dir: Path) -> dict[str, dict]:
    cards: dict[str, dict] = {}
    for path in sorted(kb_dir.glob("*.md")):
        if path.name == "_index.md":
            continue
        text = path.read_text(encoding="utf-8")
        try:
            fm_text, _body = split(text)
            meta = parse(fm_text)
        except Exception as e:  # noqa: BLE001
            warn(f"{path.name}: cannot parse frontmatter ({e}); skipped")
            continue
        card_id = meta.get("id") or path.stem
        cards[card_id] = {"id": card_id, "path": path, "text": text, "meta": meta}
    return cards

def plan(cards: dict[str, dict], by_synonym_md: Path, force: bool) -> list[dict]:
    """Вернуть список планов: [{id, path, synonyms, action, old_text, new_text}]."""
    text = by_synonym_md.read_text(encoding="utf-8")
    pairs = parse_by_synonym(text)
    if not pairs:
        die(f"no (synonym, card_id) pairs parsed from {by_synonym_md}")

    by_card: dict[str, list[str]] = defaultdict(list)
    for syn, card_id in pairs:
        by_card[card_id].append(syn)

    orphan_ids = sorted(set(by_card) - set(cards))
    if orphan_ids:
        warn(f"{len(orphan_ids)} orphan card ids in by-synonym.md: {orphan_ids}")

    plans: list[dict] = []
    for card_id, syns in sorted(by_card.items()):
        if card_id not in cards:
            continue
        card = cards[card_id]
        existing = card["meta"].get("synonyms")
        existing_list = list(existing) if isinstance(existing, list) else ([] if existing is None else [existing])

        if existing_list and not force:
            if set(existing_list) != set(syns):
                warn(
                    f"{card_id}: frontmatter synonyms {existing_list} differ from "
                    f"by-synonym.md {syns}; use --force to overwrite"
                )
                plans.append({"id": card_id, "action": "skip-conflict",
                              "path": card["path"], "synonyms": syns,
                              "old_text": card["text"], "new_text": card["text"]})
            else:
                plans.append({"id": card_id, "action": "noop",
                              "path": card["path"], "synonyms": syns,
                              "old_text": card["text"], "new_text": card["text"]})
            continue

        fm_text, _ = split(card["text"])
        new_block = render_list_block("synonyms", syns)
        new_fm = insert_block_after_key(fm_text, "status", new_block)
        new_text = rebuild(card["text"], new_fm)
        plans.append({"id": card_id, "action": "insert",
                      "path": card["path"], "synonyms": syns,
                      "old_text": card["text"], "new_text": new_text})

    return plans

def write_text_preserving_newlines(path: Path, text: str) -> None:
    raw = path.read_bytes()
    crlf = b"\r\n" in raw[:5000]
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))

def show_diff(plan_item: dict) -> None:
    if plan_item["old_text"] == plan_item["new_text"]:
        return
    diff = difflib.unified_diff(
        plan_item["old_text"].splitlines(keepends=True),
        plan_item["new_text"].splitlines(keepends=True),
        fromfile=f"a/{plan_item['path'].name}",
        tofile=f"b/{plan_item['path'].name}",
    )
    sys.stdout.writelines(diff)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=None, help="repo root (auto-detected)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--inspect", action="store_true", help="show what will be inserted (no diff)")
    mode.add_argument("--dry-run", action="store_true", help="show diff for each card (default)")
    mode.add_argument("--apply", action="store_true", help="write changes to files")
    ap.add_argument("--force", action="store_true", help="overwrite conflicting synonyms")
    args = ap.parse_args()

    repo = args.repo or find_repo_root(Path.cwd())
    kb_dir = repo / "kb" / "unf30"
    by_synonym_md = repo / "_meta" / "by-synonym.md"

    if not by_synonym_md.exists():
        die(f"not found: {by_synonym_md}")
    if not kb_dir.is_dir():
        die(f"not found: {kb_dir}")

    cards = load_cards(kb_dir)
    info(f"Loaded {len(cards)} cards from {kb_dir}")

    plans = plan(cards, by_synonym_md, args.force)

    n_insert = sum(1 for p in plans if p["action"] == "insert")
    n_noop = sum(1 for p in plans if p["action"] == "noop")
    n_conflict = sum(1 for p in plans if p["action"] == "skip-conflict")
    info(f"Plan: insert={n_insert}, noop={n_noop}, conflict={n_conflict}")

    if args.inspect:
        for p in plans:
            tag = {"insert": "+", "noop": "=", "skip-conflict": "!"}[p["action"]]
            info(f"  {tag} {p['id']}: {p['synonyms']}")
        return 0

    if args.apply:
        if n_conflict and not args.force:
            info("Refusing to --apply while conflicts exist (use --force or resolve manually).")
            return 1
        written = 0
        for p in plans:
            if p["action"] != "insert":
                continue
            write_text_preserving_newlines(p["path"], p["new_text"])
            written += 1
        info(f"✓ wrote {written} card(s)")
        return 0

    # dry-run (default)
    for p in plans:
        if p["action"] == "insert":
            show_diff(p)
    info(f"Dry-run: {n_insert} card(s) would change. Use --apply to write.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
