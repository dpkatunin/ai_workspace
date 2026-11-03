-- SQLite-схема для STRUCT-слоя базы знаний 1С
-- Базовая схема. FTS-индекс создаётся отдельно (см. ingest.py, build_fts).

PRAGMA foreign_keys = ON;

-- Конфигурация
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    dump_date TEXT,
    source_file TEXT,
    UNIQUE(name, version)
);

-- Объекты метаданных
CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY,
    config_id INTEGER REFERENCES config(id),
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    synonym TEXT,
    full_name TEXT NOT NULL UNIQUE,
    comment TEXT,
    register_kind TEXT,
    periodicity TEXT,
    write_mode TEXT,
    conduction TEXT,
    hierarchy_type TEXT,
    is_hierarchical INTEGER,
    code_length INTEGER,
    code_type TEXT,
    name_length INTEGER,
    plan_accounts TEXT,
    plan_calculation_types TEXT,
    max_subconto INTEGER,
    properties_json TEXT,
    value_types_json TEXT,
    value_length INTEGER,
    value_precision INTEGER,
    value_string_length INTEGER,
    source_file TEXT
);

CREATE INDEX IF NOT EXISTS idx_objects_kind ON objects(kind);
CREATE INDEX IF NOT EXISTS idx_objects_name ON objects(name);

-- Реквизиты / измерения / ресурсы / стандартные
CREATE TABLE IF NOT EXISTS attributes (
    id INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES objects(id),
    name TEXT NOT NULL,
    synonym TEXT,
    comment TEXT,
    role TEXT NOT NULL,
    tabular_section TEXT NOT NULL DEFAULT '',
    check_fill TEXT,
    length INTEGER,
    precision INTEGER,
    string_length INTEGER,
    source_file TEXT,
    UNIQUE(object_id, tabular_section, role, name)
);

CREATE INDEX IF NOT EXISTS idx_attributes_object ON attributes(object_id);

-- Типы реквизита (многие ко многим)
CREATE TABLE IF NOT EXISTS attribute_types (
    attribute_id INTEGER NOT NULL REFERENCES attributes(id),
    type_name TEXT NOT NULL,
    is_reference INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (attribute_id, type_name)
);

-- Табличные части
CREATE TABLE IF NOT EXISTS tabular_sections (
    id INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES objects(id),
    name TEXT NOT NULL,
    synonym TEXT,
    UNIQUE(object_id, name)
);

-- Движения документа по регистрам
CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES objects(id),
    register_full_name TEXT NOT NULL,
    register_kind TEXT,
    register_name TEXT,
    source_file TEXT,
    UNIQUE(document_id, register_full_name)
);

-- Граф связей (владельцы, регистраторы, основания, движения)
CREATE TABLE IF NOT EXISTS object_links (
    id INTEGER PRIMARY KEY,
    from_object_id INTEGER NOT NULL REFERENCES objects(id),
    link_type TEXT NOT NULL,
    to_full_name TEXT NOT NULL,
    to_object_id INTEGER REFERENCES objects(id),
    source_file TEXT,
    UNIQUE(from_object_id, link_type, to_full_name)
);

CREATE INDEX IF NOT EXISTS idx_links_from ON object_links(from_object_id);
CREATE INDEX IF NOT EXISTS idx_links_to ON object_links(to_full_name);
CREATE INDEX IF NOT EXISTS idx_links_type ON object_links(link_type);

-- Значения перечислений
CREATE TABLE IF NOT EXISTS enum_values (
    id INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES objects(id),
    name TEXT NOT NULL,
    synonym TEXT,
    UNIQUE(object_id, name)
);

-- Предопределённые элементы
CREATE TABLE IF NOT EXISTS predefined (
    object_id INTEGER NOT NULL REFERENCES objects(id),
    name TEXT NOT NULL,
    PRIMARY KEY (object_id, name)
);

-- View: кто пишет в регистр
CREATE VIEW IF NOT EXISTS v_register_writers AS
SELECT o.full_name AS register, l.to_full_name AS document
FROM object_links l
JOIN objects o ON o.id = l.from_object_id
WHERE l.link_type = 'registrator';

-- View: куда пишет документ
CREATE VIEW IF NOT EXISTS v_document_movements AS
SELECT o.full_name AS document, m.register_full_name AS register
FROM movements m
JOIN objects o ON o.id = m.document_id;
