#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_subsystem_path.py — шаг 1 гибридного плана: временное заполнение
subsystem_path = '<Подсистема>/<Вид>' (плоская схема).

Шаг 2 (иерархия из JSON-выгрузки 1С) заменит значения через доработанный ingest.py.

По умолчанию работает в режиме DRY-RUN (ничего не пишет в БД).
Для записи: добавить --apply.

Заодно отчитывается о дубликатах full_name (закрывает висящий вопрос
проверки без ожидания вывода check_zakupki.py).

Usage (из папки projects/unf30-kb/struct):
    ..\\..\\..\\.venv\\Scripts\\python.exe fix_subsystem_path.py            # dry-run
    ..\\..\\..\\.venv\\Scripts\\python.exe fix_subsystem_path.py --apply   # запись
    ..\\..\\..\\.venv\\Scripts\\python.exe fix_subsystem_path.py --db data/struct.db
"""

import argparse
import os
import sqlite3
import sys

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "struct.db")


def _pick(lower_map, *cands):
    for c in cands:
        if c in lower_map:
            return lower_map[c]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Заполнение subsystem_path (плоская схема) + отчёт о дубликатах"
    )
    ap.add_argument("--db", default=DEFAULT_DB, help="путь к struct.db")
    ap.add_argument("--apply", action="store_true",
                    help="выполнить UPDATE (по умолчанию только dry-run)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ОШИБКА: БД не найдена: %s" % args.db, file=sys.stderr)
        return 2

    con = sqlite3.connect(args.db)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(objects)")]
        lower = {c.lower(): c for c in cols}

        c_path = _pick(lower, "subsystem_path", "subsystempath", "path")
        c_sub = _pick(lower, "subsystem", "subsystem_name", "subsystemname")
        c_kind = _pick(lower, "kind", "type", "object_kind", "вид")
        c_full = _pick(lower, "full_name", "fullname")

        missing = [n for n, c in (("subsystem_path", c_path),
                                  ("subsystem", c_sub),
                                  ("kind/type", c_kind)) if c is None]
        if missing:
            print("ОШИБКА: в objects нет колонок: %s" % ", ".join(missing), file=sys.stderr)
            print("Найденные колонки: %s" % cols, file=sys.stderr)
            return 2

        print("Колонки: path=%s subsystem=%s kind=%s" % (c_path, c_sub, c_kind))

        # --- Отчёт о дубликатах full_name ---
        if c_full:
            dups = con.execute(
                "SELECT %s, COUNT(*) c FROM objects GROUP BY %s HAVING c > 1 "
                "ORDER BY c DESC, %s" % (c_full, c_full, c_full)
            ).fetchall()
            print("\n=== Дубликаты %s: %d групп ===" % (c_full, len(dups)))
            for name, cnt in dups[:50]:
                print("  %dx  %s" % (cnt, name))
            if len(dups) > 50:
                print("  ... и ещё %d" % (len(dups) - 50))
        else:
            print("\n(колонка full_name не найдена — отчёт о дубликатах пропущен)")

        # --- Заполнение subsystem_path ---
        total = con.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        empty = con.execute(
            "SELECT COUNT(*) FROM objects WHERE %s IS NULL OR TRIM(%s) = ''"
            % (c_path, c_path)
        ).fetchone()[0]
        print("\nВсего объектов: %d; с пустым %s: %d" % (total, c_path, empty))

        expr = "%s || '/' || %s" % (c_sub, c_kind)
        samples = con.execute(
            "SELECT %s, %s, %s FROM objects WHERE %s IS NULL OR TRIM(%s) = '' "
            "LIMIT 10" % (c_sub, c_kind, c_full or c_sub, c_path, c_path)
        ).fetchall()
        print("\nПримеры будущих значений (dry-run):")
        for sub, kind, full in samples:
            print("  %s/%s   <- %s" % (sub, kind, full))

        if not args.apply:
            print("\nDRY-RUN: изменения не внесены. Для записи добавь --apply.")
            return 0

        cur = con.execute(
            "UPDATE objects SET %s = %s WHERE %s IS NULL OR TRIM(%s) = ''"
            % (c_path, expr, c_path, c_path)
        )
        con.commit()
        print("\nAPPLY: обновлено строк: %d" % cur.rowcount)

        left = con.execute(
            "SELECT COUNT(*) FROM objects WHERE %s IS NULL OR TRIM(%s) = ''"
            % (c_path, c_path)
        ).fetchone()[0]
        print("Осталось пустых %s: %d" % (c_path, left))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
