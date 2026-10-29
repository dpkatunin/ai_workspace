#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_cards.py — сверка карточек базы знаний с реальной конфигурацией.

Проверяет:
  1. Каждый регистр в `## Движения` / `## Участие в регистрах` существует
     в конфигурации (по имени `РегистрНакопления.X` или `РегистрСведений.X`).
  2. Регистры без префикса (например, «Выпуск продукции» — свободное имя)
     пропускаются с предупреждением: проверить программно нельзя.
  3. Каждая карточка со статусом verified не имеет «подозрительных»
     регистров: если карточка verified и регистр не найден — это ошибка.

Использование:
    py tools\\validate_cards.py
    py tools\\validate_cards.py --config _meta/config_metadata.json
    py tools\\validate_cards.py --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.frontmatter import parse, split
from lib.sections import extract_h2, extract_items

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REGISTER_SECTIONS = ("Движения", "Участие в регистрах")

def build_all_registers(config: dict) -> set[str]:
    """Множество имён регистров в формате `РегистрНакопления.X`."""
    names: set[str] = set()
    for reg in config.get("accumulation_registers", {}):
        names.add(f"РегистрНакопления.{reg}")
    for reg in config.get("information_registers", {}):
        names.add(f"РегистрСведений.{reg}")
    return names

def is_technical_register(name: str) -> bool:
    """Техническое имя = с префиксом РегистрНакопления/РегистрСведений."""
    return name.startswith("РегистрНакопления.") or name.startswith(
        "РегистрСведений."
    )

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("_meta/config_metadata.json"),
        help="компактный индекс (по умолчанию _meta/config_metadata.json)",
    )
    ap.add_argument(
        "--kb",
        type=Path,
        default=Path("kb/unf30"),
        help="каталог карточек (по умолчанию kb/unf30)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="считать ошибкой любой нетехнический регистр",
    )
    args = ap.parse_args()

    if not args.config.exists():
        print(f"ERROR: {args.config} не найден.", file=sys.stderr)
        print("  Сначала: py tools\\parse_config_json.py", file=sys.stderr)
        return 1

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    all_registers = build_all_registers(config)

    errors: list[str] = []
    warnings: list[str] = []
    stats = {
        "cards": 0,
        "with_registers": 0,
        "registers_total": 0,
        "registers_ok": 0,
        "registers_unknown": 0,
        "registers_bad": 0,
    }

    for path in sorted(args.kb.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        stats["cards"] += 1

        text = path.read_text(encoding="utf-8")
        try:
            fm_text, body = split(text)
            meta = parse(fm_text)
        except Exception as e:
            warnings.append(f"{path.name}: не удалось разобрать frontmatter ({e})")
            continue

        card_id = meta.get("id", path.stem)
        card_status = meta.get("status", "?")

        sections = extract_h2(body)
        has_section = False

        for section_name in REGISTER_SECTIONS:
            if section_name not in sections:
                continue
            has_section = True
            items = extract_items(sections[section_name])
            for reg in items:
                stats["registers_total"] += 1

                if not is_technical_register(reg):
                    stats["registers_unknown"] += 1
                    msg = (
                        f"{card_id}: '{reg}' в '{section_name}' — "
                        f"не техническое имя, проверить программно нельзя"
                    )
                    if args.strict:
                        errors.append(msg)
                    else:
                        warnings.append(msg)
                    continue

                if reg in all_registers:
                    stats["registers_ok"] += 1
                else:
                    stats["registers_bad"] += 1
                    msg = (
                        f"{card_id} [{card_status}]: '{reg}' "
                        f"в '{section_name}' — НЕТ в конфигурации"
                    )
                    if card_status == "verified":
                        errors.append(msg)
                    else:
                        warnings.append(msg)

        if has_section:
            stats["with_registers"] += 1

    # Отчёт
    print(f"Config: {config['meta'].get('config_synonym', '?')} "
          f"{config['meta'].get('config_version', '?')}")
    print(f"Cards:  {stats['cards']} (из них с секцией регистров: {stats['with_registers']})")
    print(f"Registers: всего {stats['registers_total']}, "
          f"OK {stats['registers_ok']}, "
          f"не найдено {stats['registers_bad']}, "
          f"не технических {stats['registers_unknown']}")
    print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        return 1

    print("✓ Все технические регистры найдены в конфигурации.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
