"""
ingest_help.py — HELP-слой УНФ 3.0: импорт справки конфигурации (Help/ru.html) в SQLite.

Источник: выгрузка конфигурации в файлы (корень выгрузки, где лежат Documents/, Catalogs/,
Configuration/...). Каждый файл */Help/ru.html становится одной статьёй (один чанк).

Идемпотентно: ключ = относительный путь, повторный запуск обновляет статьи (INSERT OR REPLACE),
поэтому подмешивать новые файлы можно без перезаливки базы.

Использование:
    python -X utf8 ingest_help.py --root <корень_выгрузки> [--db data/help.db]
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

SCHEMA = Path(__file__).parent / 'schema.sql'

# Английские имена в href (Document.ЗаказПокупателя.Form.../Help) → русские виды.
HREF_KIND = {
    'Document': 'Документ', 'Catalog': 'Справочник', 'Report': 'Отчет',
    'DataProcessor': 'Обработка', 'InformationRegister': 'РегистрСведений',
    'AccumulationRegister': 'РегистрНакопления', 'AccountingRegister': 'РегистрБухгалтерии',
    'CalculationRegister': 'РегистрРасчета', 'ExchangePlan': 'ПланОбмена',
    'ChartOfAccounts': 'ПланСчетов', 'ChartOfCharacteristicTypes': 'ПланВидовХарактеристик',
    'ChartOfCalculationTypes': 'ПланВидовРасчета', 'BusinessProcess': 'БизнесПроцесс',
    'Task': 'Задача', 'Enum': 'Перечисление', 'Constant': 'Константа',
    'CommonModule': 'ОбщийМодуль', 'CommonForm': 'ОбщаяФорма', 'CommonCommand': 'ОбщаяКоманда',
    'DocumentJournal': 'ЖурналДокументов', 'FilterCriterion': 'КритерийОтбора',
    'SettingsStorage': 'ХранилищеНастроек', 'FunctionalOption': 'ФункциональнаяОпция',
    'FunctionalOptionsParameter': 'ПараметрФункциональныхОпций', 'Role': 'Роль',
    'SessionParameter': 'ПараметрСеанса', 'DefinedType': 'ОпределяемыйТип',
    'EventSubscription': 'ПодпискаНаСобытие', 'ScheduledJob': 'РегламентноеЗадание',
    'Subsystem': 'Подсистема', 'WebService': 'WebСервис', 'HTTPService': 'HTTPСервис',
    'WSReference': 'WSСсылка', 'Style': 'Стиль', 'Language': 'Язык',
    'ExternalDataSource': 'ВнешнийИсточникДанных', 'Sequence': 'Последовательность',
    'DocumentNumerator': 'НумераторДокументов', 'CommonPicture': 'ОбщаяКартинка',
    'CommonTemplate': 'ОбщийМакет', 'Package': 'ПакетXDTO',
}

# Имена папок выгрузки (мн. число) → русский вид, для вывода object_full_name из пути файла.
DIR_KIND = {
    'Documents': 'Документ', 'Catalogs': 'Справочник', 'Reports': 'Отчет',
    'DataProcessors': 'Обработка', 'InformationRegisters': 'РегистрСведений',
    'AccumulationRegisters': 'РегистрНакопления', 'AccountingRegisters': 'РегистрБухгалтерии',
    'CalculationRegisters': 'РегистрРасчета', 'ExchangePlans': 'ПланОбмена',
    'ChartsOfAccounts': 'ПланСчетов', 'ChartsOfCharacteristicTypes': 'ПланВидовХарактеристик',
    'ChartsOfCalculationTypes': 'ПланВидовРасчета', 'BusinessProcesses': 'БизнесПроцесс',
    'Tasks': 'Задача', 'Enums': 'Перечисление', 'Constants': 'Константа',
    'CommonModules': 'ОбщийМодуль', 'CommonForms': 'ОбщаяФорма', 'CommonCommands': 'ОбщаяКоманда',
    'DocumentJournals': 'ЖурналДокументов', 'FilterCriteria': 'КритерийОтбора',
    'SettingsStorages': 'ХранилищеНастроек', 'FunctionalOptions': 'ФункциональнаяОпция',
    'FunctionalOptionsParameters': 'ПараметрФункциональныхОпций', 'Roles': 'Роль',
    'SessionParameters': 'ПараметрСеанса', 'DefinedTypes': 'ОпределяемыйТип',
    'EventSubscriptions': 'ПодпискаНаСобытие', 'ScheduledJobs': 'РегламентноеЗадание',
    'Subsystems': 'Подсистема', 'WebServices': 'WebСервис', 'HTTPServices': 'HTTPСервис',
    'WSReferences': 'WSСсылка', 'Styles': 'Стиль', 'Languages': 'Язык',
    'ExternalDataSources': 'ВнешнийИсточникДанных', 'Sequences': 'Последовательность',
}

# Теги, содержимое которых пропускаем целиком (до закрывающего).
SKIP_TAGS = {'style', 'script'}
# Одиночные теги без закрывающего: пропускаем сами, но НЕ глубину (meta/link/img без </...>).
DROP_TAGS = {'img', 'link', 'meta', 'input'}
BLOCK_TAGS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'br', 'hr', 'ul', 'ol', 'table'}


class HelpHTMLParser(HTMLParser):
    """Вытаскивает из MSHTML-справки: заголовок h1, разделы h2, якоря, ссылки, чистый текст."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts = []
        self.title = None
        self.sections = []
        self.anchors = []
        self.links = []
        self._in_h1 = False
        self._in_h2 = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth or tag in DROP_TAGS:
            return
        if tag in BLOCK_TAGS:
            self._flush_line()
        if tag == 'h1':
            self._in_h1 = True
            self._buf = []
        elif tag == 'h2':
            self._in_h2 = True
            self._buf = []
        elif tag == 'a':
            a = dict(attrs)
            if a.get('name'):
                self.anchors.append(a['name'])
            href = a.get('href')
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth or tag in DROP_TAGS:
            return
        if tag in BLOCK_TAGS:
            self._flush_line()
        if tag == 'h1' and self._in_h1:
            t = ' '.join(''.join(self._buf).split())
            if t and not self.title:
                self.title = t
            self._in_h1 = False
            self._buf = []
        elif tag == 'h2' and self._in_h2:
            t = ' '.join(''.join(self._buf).split())
            if t:
                self.sections.append(t)
            self._in_h2 = False
            self._buf = []

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self._in_h1 or self._in_h2:
            self._buf.append(data)
        self.parts.append(data)

    def _flush_line(self):
        self.parts.append('\n')

    def text(self):
        raw = ''.join(self.parts)
        lines = [' '.join(line.split()) for line in raw.split('\n')]
        lines = [l for l in lines if l]
        return '\n'.join(lines)


def read_text(path: Path) -> str:
    """UTF-8 (с/без BOM) → cp1251 fallback. Ничего не выдумываем: неведомая кодировка = ошибка файла."""
    b = path.read_bytes()
    for enc in ('utf-8-sig', 'utf-8', 'cp1251'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError('unknown', b, 0, 1, f'не смогли декодировать {path}')


def classify_path(rel: Path):
    """Из пути файла выводим (object_full_name, ref_kind, form_name). Не угадываем: непонятно → other/NULL.
    Реальная структура выгрузки: <Вид>/<Имя>/[Ext/]Help/ru.html — уровень Ext может быть, может отсутствовать."""
    parts = [p for p in rel.parts[:-1] if p not in ('Help', 'Ext')]
    if not parts:
        return None, 'other', None
    if parts[0] == 'Configuration':
        return None, 'configuration', None
    kind = DIR_KIND.get(parts[0])
    if not kind:
        return None, 'other', None
    if len(parts) == 2:
        ref = 'subsystem' if kind == 'Подсистема' else 'object'
        return f'{kind}.{parts[1]}', ref, None
    # Вложенные подсистемы: Subsystems/Продажи/Subsystems/РозничныеПродажи
    if kind == 'Подсистема':
        names = [parts[i + 1] for i in range(0, len(parts) - 1, 2)
                 if parts[i] == 'Subsystems' and i + 1 < len(parts)]
        if names:
            return 'Подсистема.' + '.Подсистема.'.join(names), 'subsystem', None
        return None, 'other', None
    if len(parts) >= 4 and parts[2] == 'Forms':
        return f'{kind}.{parts[1]}', 'form', parts[3]
    if len(parts) >= 4 and parts[2] == 'Templates':
        return f'{kind}.{parts[1]}', 'template', parts[3]
    return None, 'other', None


def classify_link(href: str):
    """→ (link_kind, to_object_full_name). Формат object_help: 'Document.ЗаказПокупателя[.Form.X]/Help'."""
    if href.startswith('#'):
        return 'anchor', None
    if href.startswith('v8help://'):
        return 'other', None
    if href.lower().startswith(('http://', 'https://')):
        return ('external_its' if 'its.1c.ru' in href else 'external'), None
    m = re.match(r'^([A-Za-z]+)\.([^.\\/]+)', href)
    if m and m.group(1) in HREF_KIND:
        return 'object_help', f"{HREF_KIND[m.group(1)]}.{m.group(2)}"
    return 'other', None


def ingest_file(conn, db_dir: Path, path: Path, root: Path):
    rel = path.relative_to(root)
    rel_posix = rel.as_posix()
    try:
        html = read_text(path)
    except Exception as e:
        print(f'  !! пропуск {rel_posix}: {e}', file=sys.stderr)
        return False
    p = HelpHTMLParser()
    try:
        p.feed(html)
        p.close()
    except Exception as e:
        print(f'  !! HTML повреждён {rel_posix}: {e}', file=sys.stderr)
    text = p.text()
    if not text.strip():
        print(f'  !! пустой текст {rel_posix}', file=sys.stderr)
        return False
    if p.title:
        title = p.title
    elif p.sections:
        title = p.sections[0]
    else:
        # Запасной вариант: имя объекта из пути, пропуская технические уровни Help/Ext.
        title = next((q.name for q in path.parents
                      if q.name not in ('Help', 'Ext')), path.stem)
    obj, ref_kind, form_name = classify_path(rel)
    conn.execute(
        """INSERT OR REPLACE INTO help_articles
           (path, lang, title, object_full_name, ref_kind, form_name, text,
            sections_json, anchors_json, source_file)
           VALUES (?, 'ru', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rel_posix, title, obj, ref_kind, form_name, text,
         json.dumps(p.sections, ensure_ascii=False), json.dumps(p.anchors, ensure_ascii=False),
         str(path)))
    conn.execute('DELETE FROM help_links WHERE from_path = ?', (rel_posix,))
    seen = set()
    for href in p.links:
        if href in seen:
            continue
        seen.add(href)
        kind, to_obj = classify_link(href)
        conn.execute(
            'INSERT OR IGNORE INTO help_links (from_path, href, link_kind, to_object_full_name) VALUES (?,?,?,?)',
            (rel_posix, href, kind, to_obj))
    return True


def build_fts(conn):
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS help_articles_fts USING fts5(
        title, text, content='help_articles', content_rowid='id')""")
    conn.execute("INSERT INTO help_articles_fts(help_articles_fts) VALUES('rebuild')")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, help='корень выгрузки конфигурации (где Documents/, Configuration/)')
    ap.add_argument('--db', default=str(Path(__file__).parent / 'data' / 'help.db'))
    args = ap.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f'!! нет каталога: {root}', file=sys.stderr)
        sys.exit(1)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript(SCHEMA.read_text(encoding='utf-8'))
    files = sorted(f for f in root.rglob('ru.html') if 'Help' in f.parts)
    if not files:
        print('!! файлов */ru.html не найдено — проверь --root', file=sys.stderr)
        sys.exit(1)
    t0 = time.time()
    ok = fail = 0
    for i, f in enumerate(files, 1):
        if ingest_file(conn, db_path.parent, f, root):
            ok += 1
        else:
            fail += 1
        if i % 200 == 0:
            conn.commit()
            print(f'  ... {i}/{len(files)} ({time.time() - t0:.0f} c)')
    build_fts(conn)
    conn.commit()
    total = conn.execute('SELECT COUNT(*) FROM help_articles').fetchone()[0]
    links = conn.execute('SELECT COUNT(*) FROM help_links').fetchone()[0]
    print(f'OK: статей всего в базе {total} (обработано {ok}, пропущено {fail}), ссылок {links}, {time.time() - t0:.0f} c')
    conn.close()


if __name__ == '__main__':
    main()
