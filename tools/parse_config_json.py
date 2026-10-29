#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_config_json.py — читает config_export.json (выгрузка из 1С),
строит компактный _meta/config_metadata.json для валидации карточек.

Использование:
    py tools\\parse_config_json.py
    py tools\\parse_config_json.py --src _raw/unf30_xml/config_export.json
    py tools\\parse_config_json.py --dst _meta/config_metadata.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def build_compact_index(data: dict) -> dict:
    """Из плоского JSON от 1С → индексированный по имени."""
    result = {
        "meta": data.get("meta", {}),
        "documents": {o["name"]: o for o in data.get("documents", [])},
        "catalogs": {o["name"]: o for o in data.get("catalogs", [])},
        "accumulation_registers": {
            o["name"]: o for o in data.get("accumulation_registers", [])
        },
        "information_registers": {
            o["name"]: o for o in data.get("information_registers", [])
        },
        "enumerations": {o["name"]: o for o in data.get("enumerations", [])},
    }

    # Обратный индекс: регистр → какие документы в него пишут
    by_register: dict[str, list[str]] = {}
    for doc_name, doc in result["documents"].items():
        for mov in doc.get("movements", []):
            by_register.setdefault(mov, []).append(doc_name)
    result["_by_register"] = by_register

    return result

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        type=Path,
        default=Path("_raw/unf30_xml/config_export.json"),
        help="входной JSON от 1С (по умолчанию _raw/unf30_xml/config_export.json)",
    )
    ap.add_argument(
        "--dst",
        type=Path,
        default=Path("_meta/config_metadata.json"),
        help="куда сохранить компактный индекс (по умолчанию _meta/config_metadata.json)",
    )
    args = ap.parse_args()

    if not args.src.exists():
        print(f"ERROR: файл не найден: {args.src}", file=sys.stderr)
        print(
            "  Сначала запустите обработку 1С и сохраните config_export.json.",
            file=sys.stderr,
        )
        return 1

    try:
        with open(args.src, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: невалидный JSON: {e}", file=sys.stderr)
        return 1

    index = build_compact_index(data)

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    with open(args.dst, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    meta = index["meta"]
    print(f"Config: {meta.get('config_synonym', '?')} {meta.get('config_version', '?')}")
    print(f"  Exported at: {meta.get('exported_at', '?')}")
    print(f"  Documents:               {len(index['documents'])}")
    print(f"  Catalogs:                {len(index['catalogs'])}")
    print(f"  Accumulation registers:  {len(index['accumulation_registers'])}")
    print(f"  Information registers:   {len(index['information_registers'])}")
    print(f"  Enumerations:            {len(index['enumerations'])}")
    print(f"  Registers with writers:  {len(index['_by_register'])}")
    print(f"  → {args.dst}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
