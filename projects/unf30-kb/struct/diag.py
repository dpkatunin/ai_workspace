import sqlite3, json
c = sqlite3.connect('data/struct.db')
c.row_factory = sqlite3.Row

print('=== 0. Схема ===')
for tbl in ['attributes','attribute_types','objects']:
    print(f'-- {tbl}')
    for r in c.execute(f'PRAGMA table_info({tbl})'):
        print(f'   {r["name"]:25s} {r["type"]}')

print()
print('=== 1. Событие.ДокументОснование ===')
for r in c.execute('''
    SELECT a.id, a.role,
           (SELECT COUNT(*) FROM attribute_types at WHERE at.attribute_id = a.id) n
    FROM attributes a
    JOIN objects o ON o.id = a.object_id
    WHERE o.full_name='Документ.Событие' AND a.name='ДокументОснование'
'''):
    print(f'  attr_id={r["id"]:5d}  role={r["role"]}  types={r["n"]}')

print()
print('=== 2. Регистры сведений (3 шт.) ===')
for r in c.execute("SELECT full_name, properties_json FROM objects WHERE kind='РегистрСведений' LIMIT 3"):
    print(f'  {r["full_name"]}')
    print(f'    {r["properties_json"]}')

print()
print('=== 3. Константа — сырой JSON ===')
with open(r'C:\obmen\json_sub\Константа.ИспользоватьВидыЦен_20261104_020335.json', encoding='utf-8-sig') as f:
    data = json.load(f)
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])

print()
print('=== 4. Перечисление.ТипыКарт — структура JSON ===')
with open(r'C:\obmen\json_sub\Перечисление.ТипыКарт_20261104_020335.json', encoding='utf-8-sig') as f:
    data = json.load(f)
def walk(o, prefix='', depth=0):
    if depth > 3: return
    if isinstance(o, dict):
        for k, v in o.items():
            print(f'  {prefix}{k}: {type(v).__name__}')
            walk(v, prefix + '  ', depth + 1)
    elif isinstance(o, list) and o:
        print(f'  {prefix}[{len(o)} items]')
        if isinstance(o[0], (dict, list)):
            walk(o[0], prefix + '  ', depth + 1)
walk(data)
