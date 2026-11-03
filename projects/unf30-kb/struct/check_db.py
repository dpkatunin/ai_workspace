import sqlite3, json
c = sqlite3.connect('data/struct.db')
c.row_factory = sqlite3.Row

print('=== objects ===')
for row in c.execute('SELECT full_name, register_kind, conduction, properties_json FROM objects'):
    print(row['full_name'])
    print('  register_kind:', row['register_kind'])
    print('  conduction:   ', row['conduction'])
    print('  props_json:   ', (row['properties_json'] or '')[:300])

print('=== movements ===')
for row in c.execute('SELECT o.full_name, m.register_full_name FROM movements m JOIN objects o ON o.id=m.document_id'):
    print(row[0], '->', row[1])

print('=== links ===')
for row in c.execute('SELECT o.full_name, l.link_type, l.to_full_name FROM object_links l JOIN objects o ON o.id=l.from_object_id'):
    print(row[0], '|', row[1], '->', row[2])
