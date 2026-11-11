import sqlite3
c = sqlite3.connect("projects/unf30-kb/struct/data/struct.db")
rows = c.execute("SELECT full_name FROM objects WHERE full_name LIKE ? ORDER BY 1", ("%квайринг%",)).fetchall()
print("naydeno:", len(rows))
for r in rows:
    print(" ", r[0])
