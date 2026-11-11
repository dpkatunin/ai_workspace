import sqlite3
c = sqlite3.connect('projects/unf30-kb/struct/data/struct.db')
print('vsego:', c.execute('SELECT COUNT(*) FROM objects').fetchone()[0])
print('SkidkiNovaya:', c.execute("SELECT COUNT(*) FROM objects WHERE full_name='Обработка.ВидыСкидокНаценокРучныеИАвтоматические'").fetchone()[0])
print('SkidkiStaraya:', c.execute("SELECT COUNT(*) FROM objects WHERE full_name='Обработка.УдалитьВидыСкидокНаценокРучныеИАвтоматические'").fetchone()[0])
c.execute("ATTACH 'projects/unf30-kb/help/data/help.db' AS helpdb")
rows = c.execute("""SELECT DISTINCT h.object_full_name FROM helpdb.help_articles h
WHERE h.object_full_name IS NOT NULL
AND h.object_full_name NOT IN (SELECT full_name FROM objects)
AND h.object_full_name NOT LIKE 'Подсистема.%'
AND h.object_full_name NOT LIKE '%.Удалить%' ORDER BY 1""").fetchall()
print('gap:', len(rows))
for r in rows: print(' ', r[0])
