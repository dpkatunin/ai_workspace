"""
Проверка STRUCT-базы после ingest:
- счётчики по таблицам
- config_id заполнен у всех объектов
- подсистема проставлена
- дата выгрузки разобрана
- дубль ДокументОснование (два реквизита с разными tabular_section)
"""
import sqlite3

c = sqlite3.connect('data/struct.db')
c.row_factory = sqlite3.Row

print('=== counts ===')
for t in ['objects', 'attributes', 'attribute_types', 'object_links',
          'movements', 'enum_values', 'tabular_sections']:
    n = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'  {t:20s}: {n}')

print()
print('=== config ===')
for r in c.execute('SELECT id, name, version, dump_date FROM config'):
    print(f'  {r["id"]}  {r["name"]}  v{r["version"]}  {r["dump_date"]}')

print()
print('=== objects без config_id (должно быть 0) ===')
n = c.execute('SELECT COUNT(*) FROM objects WHERE config_id IS NULL').fetchone()[0]
print(f'  {n}')

print()
print('=== objects по подсистемам ===')
for r in c.execute('SELECT subsystem, COUNT(*) n FROM objects GROUP BY subsystem'):
    print(f'  {r["subsystem"]!r:20s}: {r["n"]}')

print()
print('=== Документ.ЗаказПокупателя ===')
r = c.execute(
    "SELECT subsystem, subsystem_path FROM objects WHERE full_name='Документ.ЗаказПокупателя'"
).fetchone()
print(f'  subsystem={r["subsystem"]}  path={r["subsystem_path"]}')

print()
print('=== ДокументОснование — оба реквизита ===')
for r in c.execute('''
    SELECT a.id, a.role, a.tabular_section
    FROM attributes a
    WHERE a.object_id = (SELECT id FROM objects WHERE full_name='Документ.Событие')
      AND a.name='ДокументОснование'
'''):
    print(f'  id={r["id"]}  role={r["role"]}  tch={r["tabular_section"]!r}')

print()
print('=== top-5 документов по движениям ===')
for r in c.execute('''
    SELECT o.full_name, COUNT(*) n
    FROM movements m JOIN objects o ON o.id = m.document_id
    GROUP BY o.id ORDER BY n DESC LIMIT 5
'''):
    print(f'  {r["n"]:3d} -> {r["full_name"]}')
