import sqlite3
c = sqlite3.connect('data/struct.db')
c.row_factory = sqlite3.Row

print('=== counts ===')
for t in ['objects','attributes','attribute_types','object_links','movements']:
    n = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t:20s}: {n}')

print()
print('=== objects by kind ===')
for r in c.execute('SELECT kind, COUNT(*) n FROM objects GROUP BY kind ORDER BY n DESC'):
    print(f'  {r["kind"]:25s}: {r["n"]}')

print()
print('=== registers with register_kind ===')
for r in c.execute("SELECT full_name, register_kind FROM objects WHERE kind LIKE 'Регистр%' ORDER BY full_name"):
    print(f'  {r["full_name"]:60s} {r["register_kind"]}')

print()
print('=== empty properties_json (suspicious) ===')
for r in c.execute("SELECT full_name FROM objects WHERE properties_json IS NULL OR properties_json = '' OR properties_json = '{}'"):
    print(' ', r['full_name'])

print()
print('=== top-5 documents by movements ===')
for r in c.execute('''SELECT o.full_name, COUNT(*) n
                     FROM movements m JOIN objects o ON o.id=m.document_id
                     GROUP BY o.id ORDER BY n DESC LIMIT 5'''):
    print(f'  {r["n"]:3d} -> {r["full_name"]}')

print()
print('=== attribute with many types (Событие.ДокументОснование) ===')
for r in c.execute('''SELECT a.name, COUNT(*) n
                     FROM attribute_types at
                     JOIN attributes a ON a.id=at.attribute_id
                     JOIN objects o ON o.id=a.object_id
                     WHERE o.full_name='Документ.Событие'
                     GROUP BY a.id ORDER BY n DESC LIMIT 5'''):
    print(f'  {r["n"]:3d} -> {r["name"]}')
