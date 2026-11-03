"""
Потоковый импорт JSON-выгрузки 1С метаданных в SQLite.

Логика:
1. Создать схему (schema.sql), если БД новая.
2. Прочитать заголовок (Конфигурация, Версия, ДатаВыгрузки).
3. Пройти по объектам потоком (ijson) и вставить каждый:
   - строку в objects,
   - реквизиты/измерения/ресурсы в attributes + типы в attribute_types,
   - ТЧ в tabular_sections,
   - движения в movements,
   - связи в object_links (owner, registrator, based_on, movement),
   - значения перечислений в enum_values,
   - предопределённые в predefined.
4. Пост-обработка: resolve_links (закрыть граф), build_fts (FTS5, если доступно).

Идемпотентность: повторный ingest того же файла не создаёт дубликатов
(UNIQUE + INSERT OR IGNORE / SELECT по full_name).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from _common import iter_header, iter_json_files, iter_objects

SCHEMA_PATH = Path(__file__).parent / 'schema.sql'

# ---------- инициализация ----------

def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    with open(SCHEMA_PATH, encoding='utf-8') as f:
        conn.executescript(f.read())
    return conn

def build_fts(conn: sqlite3.Connection) -> bool:
    """Создать FTS5-индекс, если модуль доступен. Возвращает True при успехе."""
    try:
        conn.execute(
            '''CREATE VIRTUAL TABLE IF NOT EXISTS objects_fts USING fts5(
                full_name, name, synonym, comment,
                content='objects', content_rowid='id'
            )'''
        )
        conn.execute("INSERT INTO objects_fts(objects_fts) VALUES('rebuild')")
        return True
    except sqlite3.OperationalError:
        return False

# ---------- вставка ----------

def upsert_config(conn, name, version, dump_date, source_file):
    conn.execute(
        '''INSERT OR IGNORE INTO config (name, version, dump_date, source_file)
           VALUES (?, ?, ?, ?)''',
        (name, version, dump_date, source_file),
    )
    cur = conn.execute(
        'SELECT id FROM config WHERE name=? AND version=?',
        (name, version),
    )
    return cur.fetchone()[0]

def insert_attribute(conn, object_id, attr, role, tabular_section, source_file):
    tch = tabular_section or ''
    cur = conn.execute(
        '''SELECT id FROM attributes
           WHERE object_id=? AND name=? AND role=? AND tabular_section=?''',
        (object_id, attr.get('Имя'), role, tch),
    )
    row = cur.fetchone()
    if row:
        attr_id = row[0]
    else:
        cur = conn.execute(
            '''INSERT INTO attributes
                (object_id, name, synonym, comment, role, tabular_section,
                 check_fill, length, precision, string_length, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                object_id,
                attr.get('Имя'),
                attr.get('Синоним'),
                attr.get('Комментарий'),
                role,
                tch,
                attr.get('ПроверкаЗаполнения'),
                attr.get('Длина'),
                attr.get('Точность'),
                attr.get('ДлинаСтроки'),
                source_file,
            ),
        )
        attr_id = cur.lastrowid

    for type_name in attr.get('Типы', []):
        is_reference = 1 if '.' in type_name else 0
        conn.execute(
            '''INSERT OR IGNORE INTO attribute_types
                (attribute_id, type_name, is_reference)
               VALUES (?, ?, ?)''',
            (attr_id, type_name, is_reference),
        )

def link(conn, from_id, link_type, to_full_name, source_file):
    if not to_full_name:
        return
    conn.execute(
        '''INSERT OR IGNORE INTO object_links
            (from_object_id, link_type, to_full_name, source_file)
           VALUES (?, ?, ?, ?)''',
        (from_id, link_type, to_full_name, source_file),
    )

def ingest_object(conn, config_id, obj, source_file):
    full_name = obj.get('ПолноеИмя')
    if not full_name:
        return None, False

    cur = conn.execute('SELECT id FROM objects WHERE full_name=?', (full_name,))
    row = cur.fetchone()
    if row:
        return row[0], False

    props = obj.get('СвойстваОбъекта') or {}
    cur = conn.execute(
        '''INSERT INTO objects (
            config_id, kind, name, synonym, full_name, comment,
            register_kind, periodicity, write_mode, conduction,
            hierarchy_type, is_hierarchical, code_length, code_type, name_length,
            plan_accounts, plan_calculation_types, max_subconto,
            properties_json, value_types_json,
            value_length, value_precision, value_string_length,
            source_file
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            config_id,
            obj.get('ВидОбъекта'),
            obj.get('Имя'),
            obj.get('Синоним'),
            full_name,
            obj.get('Комментарий'),
            props.get('ВидРегистра'),
            props.get('Периодичность'),
            props.get('РежимЗаписи'),
            props.get('Проведение'),
            props.get('ВидИерархии'),
            1 if props.get('Иерархический') else 0,
            props.get('ДлинаКода'),
            props.get('ТипКода'),
            props.get('ДлинаНаименования'),
            props.get('ПланСчетов'),
            props.get('ПланВидовРасчета'),
            props.get('МаксимальноеКоличествоСубконто'),
            json.dumps(props, ensure_ascii=False) if props else None,
            json.dumps(obj.get('Типы'), ensure_ascii=False) if obj.get('Типы') else None,
            obj.get('Длина'),
            obj.get('Точность'),
            obj.get('ДлинаСтроки'),
            source_file,
        ),
    )
    obj_id = cur.lastrowid

    # Реквизиты шапки / стандартные
    for role, key in (
        ('attribute', 'Реквизиты'),
        ('dimension', 'Измерения'),
        ('resource', 'Ресурсы'),
        ('standard', 'СтандартныеРеквизиты'),
    ):
        for attr in obj.get(key, []):
            insert_attribute(conn, obj_id, attr, role, None, source_file)

    # ТЧ
    for tch in obj.get('ТабличныеЧасти', []):
        tch_name = tch.get('Имя')
        conn.execute(
            '''INSERT OR IGNORE INTO tabular_sections (object_id, name, synonym)
               VALUES (?, ?, ?)''',
            (obj_id, tch_name, tch.get('Синоним')),
        )
        for attr in tch.get('Реквизиты', []):
            insert_attribute(conn, obj_id, attr, 'attribute', tch_name, source_file)

    # Движения (только у документов)
    for move in obj.get('Движения', []):
        conn.execute(
            '''INSERT OR IGNORE INTO movements
                (document_id, register_full_name, register_kind, register_name, source_file)
               VALUES (?, ?, ?, ?, ?)''',
            (
                obj_id,
                move.get('ПолноеИмя'),
                move.get('Вид'),
                move.get('Имя'),
                source_file,
            ),
        )
        link(conn, obj_id, 'movement', move.get('ПолноеИмя'), source_file)

    # Связи из СвойстваОбъекта
    for owner in props.get('Владельцы', []) or []:
        link(conn, obj_id, 'owner', owner, source_file)
    for reg in props.get('Регистраторы', []) or []:
        link(conn, obj_id, 'registrator', reg, source_file)
    for based in props.get('ВводитсяНаОсновании', []) or []:
        link(conn, obj_id, 'based_on', based, source_file)

    # Значения перечислений
    for ev in obj.get('ЗначенияПеречисления', []) or []:
        conn.execute(
            '''INSERT OR IGNORE INTO enum_values (object_id, name, synonym)
               VALUES (?, ?, ?)''',
            (obj_id, ev.get('Имя'), ev.get('Синоним')),
        )

    # Предопределённые
    for predef in obj.get('Предопределённые', []) or []:
        conn.execute(
            'INSERT OR IGNORE INTO predefined (object_id, name) VALUES (?, ?)',
            (obj_id, predef),
        )

    return obj_id, True

def resolve_links(conn):
    """Проставить to_object_id там, где объект уже загружен."""
    conn.execute(
        '''UPDATE object_links
           SET to_object_id = (
               SELECT id FROM objects WHERE objects.full_name = object_links.to_full_name
           )
           WHERE to_object_id IS NULL'''
    )

# ---------- main ----------

def main() -> None:
    parser = argparse.ArgumentParser(description='Ingest JSON 1С → SQLite')
    parser.add_argument('--input', required=True, help='Файл или папка с JSON')
    parser.add_argument('--db', required=True, help='Путь к SQLite-базе')
    parser.add_argument(
        '--no-fts',
        action='store_true',
        help='Не строить FTS-индекс (быстрее, но поиск только по индексам)',
    )
    args = parser.parse_args()

    try:
        files = iter_json_files(Path(args.input))
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not files:
        print(f'Нет .json в {args.input}', file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(db_path)

    total, skipped = 0, 0
    try:
        for fp in files:
            print(f'  {fp.name} ({fp.stat().st_size / 1024 / 1024:.1f} МБ)...',
                  file=sys.stderr)
            header = iter_header(fp)
            config_id = None
            if header['config_name'] and header['config_version']:
                config_id = upsert_config(
                    conn,
                    header['config_name'],
                    header['config_version'],
                    header['dump_date'],
                    fp.name,
                )

            for obj in iter_objects(fp):
                _, inserted = ingest_object(conn, config_id, obj, fp.name)
                if inserted:
                    total += 1
                else:
                    skipped += 1
            conn.commit()

        resolve_links(conn)
        conn.commit()

        if not args.no_fts:
            print('  Строю FTS-индекс...', file=sys.stderr)
            ok = build_fts(conn)
            if not ok:
                print('  WARN: FTS5 недоступен, поиск по именам будет медленнее',
                      file=sys.stderr)
        conn.commit()
    finally:
        conn.close()

    print(f'Готово: вставлено {total}, пропущено {skipped} → {db_path}',
          file=sys.stderr)

if __name__ == '__main__':
    main()
