-- HELP-слой УНФ 3.0: справка конфигурации (Help/ru.html) → SQLite.
-- Отдельная БД от struct.db: свой цикл обновления (по релизу УНФ), свой FTS.

CREATE TABLE IF NOT EXISTS help_articles (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,          -- относительный путь от корня выгрузки: Documents/ЗаказПокупателя/Help/ru.html
    lang TEXT NOT NULL DEFAULT 'ru',
    title TEXT,                         -- h1, иначе первый h2, иначе имя объекта
    object_full_name TEXT,              -- Документ.ЗаказПокупателя; NULL для Configuration/Help
    ref_kind TEXT NOT NULL,             -- object | form | subsystem | configuration | other
    form_name TEXT,                     -- для ref_kind='form'
    text TEXT NOT NULL,                 -- очищенный текст статьи
    sections_json TEXT,                 -- ["Заказ покупателя", "Заказ-наряд"]
    anchors_json TEXT,                  -- ["Заказ_покупателя", "Заказ-наряд", "FAQ"]
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS help_links (
    id INTEGER PRIMARY KEY,
    from_path TEXT NOT NULL,
    href TEXT NOT NULL,
    link_kind TEXT NOT NULL,            -- object_help | anchor | external | external_its | other
    to_object_full_name TEXT,           -- Документ.ЗаказПокупателя для object_help
    UNIQUE(from_path, href)
);

CREATE INDEX IF NOT EXISTS idx_help_articles_object ON help_articles(object_full_name);
CREATE INDEX IF NOT EXISTS idx_help_links_to ON help_links(to_object_full_name);

-- FTS создаётся кодом (ingest_help.build_fts), как в STRUCT.
