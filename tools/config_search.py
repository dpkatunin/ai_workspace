#!/usr/bin/env python3
"""Поиск объектов в XML-выгрузке конфигурации 1С (без 1С, без зависимостей).

Зачем этот файл
---------------
MCP-инструмент read_config_file умеет читать только файл по точному пути.
Чтобы узнать точное имя («есть ли документ, фиксирующий выполнение этапа
производства?»), нужен поиск по реестру выгрузки — ConfigDumpInfo.xml.
Он отсортирован по алфавиту и весит мегабайты, поэтому читать его подряд
бессмысленно: нужен индекс.

Что делает
----------
Стримит ConfigDumpInfo.xml, разбирает имена метаданных вида
    Document.РеализацияТоваровУслуг.Attribute.Организация
на три части: kind (Document), объект (РеализацияТоваровУслуг),
под-объект (Attribute.Организация). Дальше — поиск по подстроке или регексу.

CLI
---
    py tools/config_search.py этап
    py tools/config_search.py этап --kind Document
    py tools/config_search.py спецификац --kind Catalog --limit 100
    py tools/config_search.py --kinds
    py tools/config_search.py --objects --kind Document

Библиотека
----------
    from tools.config_search import ConfigIndex
    idx = ConfigIndex()
    for e in idx.search("этап", kind="Document"):
        print(e.obj)

Путь к выгрузке
---------------
По умолчанию _raw/unf30_xml рядом с репозиторием; переопределяется
аргументом --dump или переменной окружения UNF30_XML_DIR.

Как подключить к MCP (tools/mcp_server.py)
-----------------------------------------
Добавить рядом с read_config_file:

    @mcp.tool()
    def search_config(query: str, kind: str | None = None,
                      objects_only: bool = True, limit: int = 50) -> str:
        \"\"\"Найти объекты конфигурации по подстроке в имени.

        Args:
            query: подстрока имени, например «этап» или «Спецификац».
            kind: фильтр по типу: Document, Catalog, Enum, Register...
            objects_only: только сами объекты, без реквизитов и модулей.
            limit: максимум строк в ответе.
        \"\"\"
        from tools.config_search import ConfigIndex
        idx = ConfigIndex()
        rows = idx.search(query, kind=kind,
                          objects_only=objects_only, limit=limit)
        if not rows:
            return f"Ничего не найдено по запросу «{query}»."
        lines = [f"Найдено {len(rows)} (лимит {limit}):", ""]
        for e in rows:
            mark = "" if e.sub is None else f"  [{e.sub}]"
            lines.append(f"- {e.obj}{mark}  ({e.kind})")
        return "\\n".join(lines)

После перезапуска сервера инструмент появится в списке MCP.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Имя метаданных в ConfigDumpInfo.xml: <Metadata name="..." id="..."/>
_NAME_RE = re.compile(r'<Metadata\s+name="([^"]+)"')

DEFAULT_DUMP_DIR = Path(os.environ.get("UNF30_XML_DIR", "_raw/unf30_xml"))
DUMP_FILE_NAME = "ConfigDumpInfo.xml"

@dataclass(frozen=True)
class Entry:
    """Одна запись реестра выгрузки."""

    full: str          # Document.РеализацияТоваровУслуг.Attribute.Организация
    kind: str          # Document
    obj: str           # РеализацияТоваровУслуг
    sub: str | None    # Attribute.Организация  (None для самого объекта)

    @property
    def is_object(self) -> bool:
        return self.sub is None

def _parse_name(full: str) -> Entry:
    parts = full.split(".")
    kind = parts[0] if parts else ""
    obj = parts[1] if len(parts) > 1 else ""
    sub = ".".join(parts[2:]) or None
    return Entry(full=full, kind=kind, obj=obj, sub=sub)

class ConfigIndex:
    """Ленивый индекс объектов XML-выгрузки конфигурации."""

    def __init__(self, dump_path: str | Path | None = None) -> None:
        if dump_path is None:
            dump_path = DEFAULT_DUMP_DIR / DUMP_FILE_NAME
        self.dump_path = Path(dump_path)
        self._entries: list[Entry] | None = None

    # --- загрузка ---------------------------------------------------------

    def load(self) -> list[Entry]:
        """Прочитать реестр один раз и закешировать в памяти."""
        if self._entries is not None:
            return self._entries

        if not self.dump_path.exists():
            raise FileNotFoundError(
                f"Не найден реестр выгрузки: {self.dump_path}\n"
                f"Укажите путь через --dump или переменную UNF30_XML_DIR."
            )

        seen: set[str] = set()
        entries: list[Entry] = []
        with self.dump_path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = _NAME_RE.search(line)
                if not match:
                    continue
                full = match.group(1)
                if full in seen:
                    continue
                seen.add(full)
                entries.append(_parse_name(full))

        self._entries = entries
        return entries

    # --- поиск ------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        kind: str | None = None,
        objects_only: bool = True,
        limit: int = 50,
        regex: bool = False,
    ) -> list[Entry]:
        """Найти записи, в имени которых встречается query."""
        entries = self.load()

        if regex:
            pattern = re.compile(query, re.IGNORECASE)
            def match(e: Entry) -> bool:
                return bool(pattern.search(e.full))
        else:
            needle = query.casefold()
            def match(e: Entry) -> bool:
                return needle in e.full.casefold()

        kind_cf = kind.casefold() if kind else None
        result: list[Entry] = []
        for entry in entries:
            if objects_only and not entry.is_object:
                continue
            if kind_cf and entry.kind.casefold() != kind_cf:
                continue
            if not match(entry):
                continue
            result.append(entry)
            if len(result) >= limit:
                break
        return result

    # --- статистика -------------------------------------------------------

    def kinds(self) -> Counter[str]:
        """Сколько объектов каждого типа в конфигурации."""
        counter: Counter[str] = Counter()
        for entry in self.load():
            if entry.is_object:
                counter[entry.kind] += 1
        return counter

# --- CLI ------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Поиск объектов в XML-выгрузке конфигурации 1С",
    )
    parser.add_argument("query", nargs="?", help="подстрока имени (или регекс)")
    parser.add_argument("--kind", help="фильтр по типу: Document, Catalog, Enum...")
    parser.add_argument("--dump", help="путь к ConfigDumpInfo.xml")
    parser.add_argument("--limit", type=int, default=50, help="максимум строк")
    parser.add_argument("--all", action="store_true",
                        help="показывать реквизиты и модули, а не только объекты")
    parser.add_argument("--regex", action="store_true", help="query — регулярное выражение")
    parser.add_argument("--kinds", action="store_true", help="показать состав конфигурации")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    index = ConfigIndex(args.dump)

    try:
        if args.kinds:
            for kind, count in index.kinds().most_common():
                print(f"{kind:28} {count}")
            return 0

        if not args.query:
            print("Укажите запрос или --kinds", file=sys.stderr)
            return 2

        rows = index.search(
            args.query,
            kind=args.kind,
            objects_only=not args.all,
            limit=args.limit,
            regex=args.regex,
        )
        if not rows:
            print(f"Ничего не найдено по запросу «{args.query}».")
            return 1

        print(f"Найдено {len(rows)} (лимит {args.limit}):\n")
        for entry in rows:
            suffix = "" if entry.sub is None else f"  [{entry.sub}]"
            print(f"- {entry.obj}{suffix}  ({entry.kind})")
        return 0

    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
