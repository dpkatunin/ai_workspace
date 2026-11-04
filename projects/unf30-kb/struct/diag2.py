import sqlite3, json, glob, os
c = sqlite3.connect('data/struct.db')
c.row_factory = sqlite3.Row

print('=== 1. ДокументОснование — с tabular_section ===')
for r in c.execute('''
    SELECT id, role, tabular_section,
           (SELECT COUNT(*) FROM attribute_types at WHERE at.attribute_id = a.id) n
    FROM attributes a
    WHERE a.object_id = (SELECT id FROM objects WHERE full_name='Документ.Событие')
      AND a.name='ДокументОснование'
'''):
    print(f'  id={r["id"]:5d}  role={r["role"]:12s}  tch={r["tabular_section"]!r:20s}  types={r["n"]}')

print()
print('=== 2. value_types_json у констант/перечислений/опред.типов ===')
for kind in ('Константа','Перечисление','ОпределяемыйТип'):
    print(f'-- {kind}')
    for r in c.execute('SELECT name, value_types_json FROM objects WHERE kind=? LIMIT 3', (kind,)):
        print(f'   {r["name"]:40s} {r["value_types_json"]}')

print()
print('=== 3. Счётчики enum_values / predefined ===')
for t in ('enum_values','predefined','tabular_sections'):
    n = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'  {t:20s}: {n}')

print()
print('=== 4. Ключи уровня Объект у ОпределяемыйТип и ЖурналДокументов ===')
for pat in ('ОпределяемыйТип.ДокументыОснованияКОтгрузкеСоСкладов_*.json',
            'ЖурналДокументов.ДокументыПоПродажам_*.json'):
    files = glob.glob(os.path.join(r'C:\obmen\json_sub', pat))
    if not files: 
        print(f'  NOT FOUND: {pat}'); continue
    with open(files[0], encoding='utf-8-sig') as f:
        data = json.load(f)
    obj = data.get('Объект', {})
    print(f'-- {os.path.basename(files[0])}')
    print(f'   Объект keys: {list(obj.keys())}')
    print(f'   Подсистема: {data.get("Подсистема")}')

print()
print('=== 5. Подсистема.ПутьРодителей — есть ли непустые ===')
paths = {}
for fp in glob.glob(os.path.join(r'C:\obmen\json_sub', '*.json'))[:200]:
    try:
        with open(fp, encoding='utf-8-sig') as f:
            data = json.load(f)
        p = data.get('Подсистема', {}).get('Имя')
        paths[p] = paths.get(p, 0) + 1
    except Exception:
        pass
print(f'  {paths}')
