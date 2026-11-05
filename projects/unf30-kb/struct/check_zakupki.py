# check_zakupki.py — проверка подсистем в struct.db
# Запуск из корня ai_workspace:
#   .venv\Scripts\python.exe projects/unf30-kb/struct/check_zakupki.py [подсистема]
# Аргумент необязателен, по умолчанию проверяет все. Пример: check_zakupki.py Закуп
import sqlite3
import sys

DB = r"projects/unf30-kb/struct/data/struct.db"
SUB = f"%{sys.argv[1]}%" if len(sys.argv) > 1 else "%"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

def fk_col(table):
    """Колонка в table, ссылающаяся на objects(id); None если нет."""
    for fk in cur.execute(f"PRAGMA foreign_key_list({table})"):
        if fk["table"] == "objects":
            return fk["from"]
    return None

print("== config (строк должна быть 1) ==")
print("rows:", cur.execute("SELECT COUNT(*) n FROM config").fetchone()["n"])

print("\n== objects по подсистемам ==")
for r in cur.execute("SELECT COALESCE(subsystem,'(пусто)') s, COUNT(*) n FROM objects GROUP BY s ORDER BY n DESC"):
    print(f"  {r['s']}: {r['n']}")

print("\n== дубликаты full_name (должно быть пусто) ==")
dup = list(cur.execute("SELECT full_name, COUNT(*) n FROM objects GROUP BY full_name HAVING n > 1"))
if dup:
    for r in dup:
        print(f"  {r['full_name']}: {r['n']}")
else:
    print("  (нет)")

print(f"\n== Подсистемы LIKE '{SUB}': объекты по видам ==")
for r in cur.execute("""
    SELECT CASE WHEN instr(full_name,'.')>0 THEN substr(full_name,1,instr(full_name,'.')-1) ELSE full_name END k, COUNT(*) n
    FROM objects WHERE subsystem LIKE ? GROUP BY k ORDER BY n DESC""", (SUB,)):
    print(f"  {r['k']}: {r['n']}")

print(f"\n== Подсистемы LIKE '{SUB}': документы и регистры ==")
for r in cur.execute("""SELECT full_name FROM objects
    WHERE subsystem LIKE ? AND (full_name LIKE 'Документ.%' OR full_name LIKE 'Регистр%')
    ORDER BY full_name""", (SUB,)):
    print(" ", r["full_name"])

print(f"\n== Подсистемы LIKE '{SUB}': записи в дочерних таблицах ==")
for t in ["attributes", "attribute_types", "movements", "object_links", "tabular_sections", "enum_values"]:
    col = fk_col(t)
    if col:
        n = cur.execute(f"""SELECT COUNT(*) n FROM {t} x JOIN objects o ON o.id = x.{col}
                            WHERE o.subsystem LIKE ?""", (SUB,)).fetchone()["n"]
        print(f"  {t}: {n}")
    else:
        print(f"  {t}: (нет FK на objects — считаем отдельно, пришли .schema)")

print(f"\n== Подсистемы LIKE '{SUB}': subsystem_path не заполнен ==",
      cur.execute("""SELECT COUNT(*) n FROM objects
                     WHERE subsystem LIKE ? AND (subsystem_path IS NULL OR subsystem_path='')""", (SUB,)).fetchone()["n"])

print("\n== всего объектов в базе (было 381 до Закупок) ==",
      cur.execute("SELECT COUNT(*) n FROM objects").fetchone()["n"])
