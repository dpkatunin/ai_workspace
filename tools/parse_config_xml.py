#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_config_xml.py — читает XML-выгрузку конфигурации 1С и собирает
компактный _meta/config_metadata.json для валидации карточек.

v2: починен парсер движений документов. В XML-выгрузке 8.5 имя регистра
хранится в имени тега (<xr:AccumulationRecord_ИмяРегистра>) или в
атрибуте xsi:type, а не в тексте элемента. Добавлена диагностика.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def strip_ns(tag: str) -> str:
    """Убрать namespace из имени тега: '{...}Name' -> 'Name'."""
    return tag.split("}")[-1] if "}" in tag else tag

def find_text(el: ET.Element, target_tag: str) -> str:
    """Найти первый вложенный тег target_tag и вернуть его текст."""
    for child in el.iter():
        if strip_ns(child.tag) == target_tag and child.text:
            return child.text.strip()
    return ""

def find_synonym(el: ET.Element) -> str:
    """В XML 1С синоним хранится как <Synonym><v8:content>Текст</v8:content></Synonym>."""
    for child in el.iter():
        if strip_ns(child.tag) == "Synonym":
            for sub in child.iter():
                if strip_ns(sub.tag) == "content" and sub.text:
                    return sub.text.strip()
            if child.text:
                return child.text.strip()
    return ""

def parse_attributes(parent: ET.Element) -> list[dict]:
    attrs = []
    for child in parent:
        if strip_ns(child.tag) == "ChildObjects":
            for attr in child:
                if strip_ns(attr.tag) == "Attribute":
                    attrs.append(parse_attribute(attr))
    return attrs

def parse_attribute(el: ET.Element) -> dict:
    return {
        "name": find_text(el, "Name"),
        "synonym": find_synonym(el),
        "type": find_text(el, "Type"),
        "required": find_text(el, "FillChecking") == "ShowError",
    }

def parse_tabular_sections(parent: ET.Element) -> list[dict]:
    tss = []
    for child in parent:
        if strip_ns(child.tag) == "ChildObjects":
            for ts in child:
                if strip_ns(ts.tag) == "TabularSection":
                    tss.append({
                        "name": find_text(ts, "Name"),
                        "synonym": find_synonym(ts),
                        "attributes": parse_attributes(ts),
                    })
    return tss

def parse_movements(root: ET.Element, debug: bool = False) -> list[str]:
    """
    Извлечь движения документа из <RegisterRecords>.

    В XML-выгрузке 8.5 имя регистра хранится в имени тега
    (<xr:AccumulationRecord_ЗапасыНаСкладах>) или в атрибуте
    xsi:type="xr:AccumulationRecord_ЗапасыНаСкладах".
    В тексте элемента имени регистра нет.
    """
    moves: list[str] = []
    found_any_container = False

    for rec in root.iter():
        if strip_ns(rec.tag) != "RegisterRecords":
            continue
        found_any_container = True

        for item in rec:
            # Источник имени: атрибут xsi:type или имя тега
            type_attr = ""
            for key, val in item.attrib.items():
                if strip_ns(key) == "type":
                    type_attr = val
                    break

            # Если это обёртка <xr:Item xsi:type="xr:AccumulationRecord_...">,
            # имя регистра в атрибуте; если прямой тег <xr:AccumulationRecord_...>,
            # имя в теге.
            source = type_attr if type_attr else strip_ns(item.tag)

            # Убираем префикс xr: (или любой другой)
            if ":" in source:
                source = source.split(":", 1)[1]

            # Определяем тип регистра
            if source.startswith("AccumulationRecord_"):
                reg_name = source[len("AccumulationRecord_"):]
                moves.append(f"РегистрНакопления.{reg_name}")
            elif source.startswith("InformationRecord_"):
                reg_name = source[len("InformationRecord_"):]
                moves.append(f"РегистрСведений.{reg_name}")
            elif debug:
                # Не регистр — покажем для диагностики
                print(f"    DEBUG: пропущен тег '{strip_ns(item.tag)}' "
                      f"(type='{type_attr}')", file=sys.stderr)

    if debug and not moves:
        if found_any_container:
            print("    DEBUG: <RegisterRecords> найден, но движений не извлечено.",
                  file=sys.stderr)
        else:
            print("    DEBUG: <RegisterRecords> не найден в этом файле.",
                  file=sys.stderr)

    return moves

def parse_object_file(xml_path: Path, obj_type: str,
                      debug: bool = False) -> dict | None:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"WARN: не удалось прочитать {xml_path.name}: {e}", file=sys.stderr)
        return None

    main_el = None
    for child in root:
        if strip_ns(child.tag) in ("Document", "Catalog", "AccumulationRegister",
                                   "InformationRegister", "Enum"):
            main_el = child
            break

    if main_el is None:
        return None

    result = {
        "name": find_text(main_el, "Name"),
        "synonym": find_synonym(main_el),
        "type": obj_type,
        "comment": find_text(main_el, "Comment"),
        "attributes": parse_attributes(main_el),
        "tabular_sections": parse_tabular_sections(main_el),
    }

    if obj_type == "Document":
        result["movements"] = parse_movements(main_el, debug=debug)

    if obj_type == "AccumulationRegister":
        result["kind"] = find_text(main_el, "RegisterKind")

    if obj_type == "InformationRegister":
        result["periodicity"] = find_text(main_el, "InformationRegisterPeriodicity")
        result["write_mode"] = find_text(main_el, "WriteMode")

    return result

def process_dir(base_dir: Path, sub_dir: str, obj_type: str,
                debug: bool = False) -> list[dict]:
    folder = base_dir / sub_dir
    if not folder.is_dir():
        print(f"WARN: папка {sub_dir} не найдена", file=sys.stderr)
        return []

    result = []
    for xml_file in folder.glob("*.xml"):
        if xml_file.name == "ConfigDumpInfo.xml":
            continue
        obj = parse_object_file(xml_file, obj_type, debug=debug)
        if obj:
            result.append(obj)
    return result

def build_compact_index(data: dict) -> dict:
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
    by_register: dict[str, list[str]] = {}
    for doc_name, doc in result["documents"].items():
        for mov in doc.get("movements", []):
            by_register.setdefault(mov, []).append(doc_name)
    result["_by_register"] = by_register
    return result

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=Path("_raw/unf30_xml"))
    ap.add_argument("--dst", type=Path, default=Path("_meta/config_metadata.json"))
    ap.add_argument("--debug", action="store_true",
                    help="показать диагностику по первому документу с движениями")
    args = ap.parse_args()

    if not args.src.is_dir():
        print(f"ERROR: папка не найдена: {args.src}", file=sys.stderr)
        return 1

    config_version = "?"
    info_file = args.src / "ConfigDumpInfo.xml"
    if info_file.exists():
        try:
            tree = ET.parse(info_file)
            for el in tree.getroot().iter():
                if strip_ns(el.tag) == "version":
                    config_version = el.text
                    break
        except ET.ParseError:
            pass

    print(f"Читаю XML-выгрузку: {args.src}")

    # Для отладки берём только первый документ, чтобы не засорять вывод
    documents = process_dir(args.src, "Documents", "Document", debug=args.debug)

    data = {
        "meta": {
            "config_name": "1С:УНФ",
            "config_synonym": "Управление нашей фирмой",
            "config_version": config_version,
            "exported_at": "XML-выгрузка",
        },
        "documents": documents,
        "catalogs": process_dir(args.src, "Catalogs", "Catalog"),
        "accumulation_registers": process_dir(
            args.src, "AccumulationRegisters", "AccumulationRegister"
        ),
        "information_registers": process_dir(
            args.src, "InformationRegisters", "InformationRegister"
        ),
        "enumerations": process_dir(args.src, "Enums", "Enum"),
    }

    index = build_compact_index(data)

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    with open(args.dst, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

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
