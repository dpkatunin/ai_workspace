#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_names.py — пост-процессор проверки имён объектов 1С в ответах LLM.

Проверяет, что объекты 1С, упомянутые в тексте ответа, существуют в struct.db.
Интеграция в struct_mcp.py: обернуть финальный ответ через check_text().

Usage:
    python validate_names.py "текст ответа"
    python validate_names.py --file answer.txt
    python validate_names.py --self-test

Exit codes:
    0 — нет точных ссылок Вид.Имя вне БД (предупреждения возможны)
    1 — найдены точные ссылки Вид.Имя, которых нет в struct.db
    2 — ошибка открытия/чтения БД
"""

import argparse
import os
import re
import sqlite3
import sys

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "struct.db")

# Точные ссылки вида "Документ.РеализацияТоваровУслуг" (возможны пробелы вокруг точки)
RE_DOTTED = re.compile(
    r"([А-ЯA-Z][А-Яа-яA-Za-z0-9_]*)\s*\.\s*([А-ЯA-Z][А-Яа-яA-Za-z0-9_]*)"
)
# Вероятные имена объектов: идентификатор с цифрой/подчёркиванием или CamelCase-границей
RE_IDENT = re.compile(r"[А-Яа-яA-Za-z][А-Яа-яA-Za-z0-9_]{2,}")
RE_CAMEL_BOUNDARY = re.compile(r"[а-яёa-z][А-ЯЁA-Z]")

# Частые русские слова, которые не являются именами объектов (снижение шума)
STOPWORDS = set("""
авто акт все вам вас вид время год два для дня док доку ему ещё его за из или имя
и их не на но но он от по со то ты у уже эти это был был была были быть вас всего
данных дата день если есть или иль над ней ним она они оно под при так там тем тот
чем что через час штук сумма суммы товар товара товары услуга услуги цена цены
номер номера дата даты датой клиент клиента поставщик склад склада деньги оплата
продажа продажи закупка закупки остаток остатки реализация поступление выписка
""".split())


def _norm(s):
    return (s or "").strip().lower()


class NameValidator:
    """Валидация имён объектов 1С по struct.db (только stdlib, без зависимостей)."""

    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = db_path
        self.known = set()          # всё, что считаем валидным (lower-case)
        self.names = set()          # короткие имена объектов (lower-case)
        self.full_names = set()     # полные имена Вид.Имя (lower-case)
        self._load()

    def _load(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError("БД не найдена: %s" % self.db_path)
        con = sqlite3.connect("file:%s?mode=ro" % self.db_path, uri=True)
        try:
            cur = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='objects'"
            )
            if cur.fetchone() is None:
                raise RuntimeError("таблица objects не найдена в %s" % self.db_path)
            cols = [r[1] for r in con.execute("PRAGMA table_info(objects)")]
            lower = {c.lower(): c for c in cols}

            def col(*cands):
                for c in cands:
                    if c in lower:
                        return lower[c]
                return None

            c_full = col("full_name")
            c_name = col("name", "object_name", "objectname", "title")
            if c_full is None and c_name is None:
                raise RuntimeError(
                    "не найдена колонка имён (full_name/name) в objects: %s" % cols
                )
            select = [c for c in (c_full, c_name) if c]
            rows = con.execute("SELECT DISTINCT %s FROM objects" % ", ".join(select))
            for row in rows:
                if c_full is not None:
                    full = _norm(row[select.index(c_full)])
                    if full:
                        self.known.add(full)
                        self.full_names.add(full)
                        # короткая часть после последней точки — тоже валидна
                        self.known.add(full.split(".")[-1])
                if c_name is not None:
                    nm = _norm(row[select.index(c_name)])
                    if nm:
                        self.known.add(nm)
                        self.names.add(nm)
            # Виды объектов (Документ, Справочник и т.п.) — валидны как левая часть
            c_kind = col("kind", "type", "object_kind", "вид")
            if c_kind:
                for (k,) in con.execute("SELECT DISTINCT %s FROM objects" % c_kind):
                    if k and str(k).strip():
                        self.known.add(_norm(str(k)))
        finally:
            con.close()

    def is_known(self, word):
        return _norm(word) in self.known

    def check_text(self, text):
        """Возвращает (errors, warnings).

        errors   — точные ссылки Вид.Имя, отсутствующие в struct.db
        warnings — вероятные имена-идентификаторы, отсутствующие в БД
        """
        errors, warnings = [], []
        consumed = set()

        for m in RE_DOTTED.finditer(text):
            left, right = m.group(1), m.group(2)
            whole = "%s.%s" % (left, right)
            consumed.add((m.start(1), m.end(2)))
            if self.is_known(whole):
                continue
            # известное имя после точки и известный вид слева — не ошибка
            if self.is_known(left) and self.is_known(right):
                warnings.append(whole)
            else:
                errors.append(whole)

        for m in RE_IDENT.finditer(text):
            span = (m.start(), m.end())
            if any(s <= span[0] and span[1] <= e for s, e in consumed):
                continue  # уже проверено как часть Вид.Имя
            w = m.group(0)
            lw = _norm(w)
            if lw in STOPWORDS or lw in self.known:
                continue
            if any(ch.isdigit() for ch in w) or "_" in w or RE_CAMEL_BOUNDARY.search(w):
                warnings.append(w)

        return sorted(set(errors)), sorted(set(warnings))


_SELFTEST_TEXT = (
    "Документ.РеализацияТоваровУслуг проводится после Документ.ВыпискаБанка. "
    "Проверим несуществующее: Документ.ФиктивныйДокументЗз. Также CommonModule "
    "и какой-то Штука123 в тексте."
)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка имён объектов 1С по struct.db")
    ap.add_argument("text", nargs="?", help="текст ответа LLM")
    ap.add_argument("--file", help="файл с текстом ответа")
    ap.add_argument("--db", default=DEFAULT_DB, help="путь к struct.db")
    ap.add_argument("--self-test", action="store_true",
                    help="прогнать встроенный пример и показать результат")
    args = ap.parse_args(argv)

    try:
        v = NameValidator(args.db)
    except Exception as exc:
        print("ОШИБКА БД: %s" % exc, file=sys.stderr)
        return 2

    if args.self_test:
        text = _SELFTEST_TEXT
    elif args.file:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    elif args.text:
        text = args.text
    else:
        ap.print_help()
        return 2

    errors, warnings = v.check_text(text)
    print("Валидных имён в БД: %d (full_name %d, коротких %d)"
          % (len(v.known), len(v.full_names), len(v.names)))
    if errors:
        print("\nОШИБКИ — точные ссылки вне struct.db:")
        for e in errors:
            print("  - %s" % e)
    if warnings:
        print("\nПредупреждения — вероятные имена вне struct.db:")
        for w in warnings:
            print("  - %s" % w)
    if not errors and not warnings:
        print("Все упомянутые имена найдены в struct.db.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
