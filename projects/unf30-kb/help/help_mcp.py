#!/usr/bin/env python3
r"""
help_mcp.py — MCP-сервер слоя HELP (УНФ 3.0): справка конфигурации из Help/ru.html.

Каркас скопирован с struct_mcp.py один в один:
  • SDK mcp v2.x (MCPServer, transport_security передаётся в run()), fallback v1 (FastMCP);
  • лимит ответа 15 КБ, флаг truncated;
  • стабильные ID фактов: help:, hlink:.

5 инструментов: help_search, help_get_article, help_get_object_articles,
help_get_links, help_stats.

Запуск (из корня ai_workspace/):
    .venv\Scripts\python.exe projects/unf30-kb/help/help_mcp.py \
        --db projects/unf30-kb/help/data/help.db \
        --struct-db projects/unf30-kb/struct/data/struct.db --port 8002

Анти-зацикливание (2026-11-09): пустые ответы help_get_object_articles/help_get_article
снабжаются meta.verdict — счётчиком повторов, вердиктом struct.db
(объект есть/нет в конфигурации, похожие имена) и на пределе повторов — stop-директивой.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

# --------------------------------------------------------------------------
# Адаптер SDK: v2 (MCPServer) с fallback на v1 (FastMCP)
# --------------------------------------------------------------------------

_SDK_VERSION = 0
MCPServer = None  # type: ignore
TransportSecuritySettings = None  # type: ignore

try:
    from mcp.server import MCPServer as _MCPServer_v2  # type: ignore
    MCPServer = _MCPServer_v2
    _SDK_VERSION = 2
    try:
        from mcp.server.transport_security import (  # noqa: F401
            TransportSecuritySettings as _TSS_v2,
        )
        TransportSecuritySettings = _TSS_v2
    except ImportError:
        TransportSecuritySettings = None
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as _FastMCP_v1  # type: ignore
        MCPServer = _FastMCP_v1
        _SDK_VERSION = 1
    except ImportError:
        print(
            "Не установлен пакет 'mcp' в этом интерпретаторе.\n"
            "Установите:  <путь-к-venv>\\Scripts\\python.exe -m pip install \"mcp[cli]\"",
            file=sys.stderr,
        )
        sys.exit(1)

# --------------------------------------------------------------------------
# Константы
# --------------------------------------------------------------------------

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "help.db"
RESPONSE_LIMIT_BYTES = 15 * 1024
SEARCH_LIMIT = 10
ARTICLE_TEXT_LIMIT = 8000   # текст статьи длиннее — обрезаем с пометкой
SNIPPET_RADIUS = 80

# --------------------------------------------------------------------------
# Подключение к БД
# --------------------------------------------------------------------------

_db_path_global: Path = DEFAULT_DB
_conn_global: Optional[sqlite3.Connection] = None

# Анти-зацикливание: сервер помнит негативные ответы и на повторном запросе
# выдаёт однозначный вердикт вместо очередного пустого JSON.
# Ключ: (имя инструмента, аргумент) -> число повторов.
_struct_db_path: Optional[Path] = None
_miss_counts: dict[tuple[str, str], int] = {}
MISS_REPEAT_LIMIT = 2  # столько раз можно получить пустой ответ; дальше — STOP-вердикт

def _conn() -> sqlite3.Connection:
    global _conn_global
    if _conn_global is None:
        _conn_global = sqlite3.connect(
            str(_db_path_global), check_same_thread=False
        )
        _conn_global.row_factory = sqlite3.Row
    return _conn_global

# --------------------------------------------------------------------------
# Хелперы
# --------------------------------------------------------------------------

def _rows(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def _fts_query(raw: str) -> Optional[str]:
    """Свободный текст → безопасный FTS5 AND-запрос из слов (дефисы и прочее отбрасываем).
    Внимание: unicode61 не знает морфологии ('зарезервировать' ≠ 'резервировать')."""
    tokens = re.findall(r"\w+", raw or "", re.UNICODE)
    if not tokens:
        return None
    return " ".join(tokens)

def _snippet(text: Optional[str], tokens: list[str]) -> Optional[str]:
    if not text:
        return text
    if len(text) <= 300:
        return text
    low = text.lower()
    for t in tokens:
        idx = low.find(t.lower())
        if idx >= 0:
            start = max(0, idx - SNIPPET_RADIUS)
            end = min(len(text), idx + len(t) + SNIPPET_RADIUS)
            pre = "..." if start > 0 else ""
            suf = "..." if end < len(text) else ""
            return pre + text[start:end] + suf
    return text[:300] + "..."

def _cut_text(text: str) -> tuple[str, bool]:
    if len(text) <= ARTICLE_TEXT_LIMIT:
        return text, False
    return text[:ARTICLE_TEXT_LIMIT] + "\n...[обрезано]", True

# --------------------------------------------------------------------------
# Формирование ответа с лимитом (паттерн struct_mcp._finalize)
# --------------------------------------------------------------------------

def _shrink_once(facts: list[dict]) -> bool:
    best: Optional[tuple[dict, str, int]] = None
    for f in facts:
        d = f.get("data")
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if isinstance(v, list) and len(v) > 1:
                if best is None or len(v) > best[2]:
                    best = (d, k, len(v))
    if best is not None:
        d, k, n = best
        d[k] = d[k][: max(1, n // 2)]
        return True
    for f in facts:
        d = f.get("data")
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if isinstance(v, str) and len(v) > 200:
                d[k] = v[:200] + "..."
                return True
    return False

def _finalize(facts: list[dict], not_found: list[str], meta: dict) -> str:
    resp = {"facts": facts, "not_found": not_found, "meta": meta}
    data = json.dumps(resp, ensure_ascii=False)
    if len(data.encode("utf-8")) <= RESPONSE_LIMIT_BYTES:
        return data

    original_size = len(data.encode("utf-8"))
    while True:
        resp = {
            "facts": facts,
            "not_found": not_found,
            "meta": {**meta, "truncated": True, "original_size_bytes": original_size},
        }
        data = json.dumps(resp, ensure_ascii=False)
        if len(data.encode("utf-8")) <= RESPONSE_LIMIT_BYTES:
            return data
        if not _shrink_once(facts):
            return data

# --------------------------------------------------------------------------
# Реализация инструментов (чистые функции, без MCP-обвязки)
# --------------------------------------------------------------------------

def _article_fact(r: dict, tokens: list[str], with_text: bool = False) -> dict:
    data: dict[str, Any] = {
        "path": r.get("path"),
        "title": r.get("title"),
        "object_full_name": r.get("object_full_name"),
        "ref_kind": r.get("ref_kind"),
        "form_name": r.get("form_name"),
    }
    if with_text:
        text, cut = _cut_text(r.get("text") or "")
        data["text"] = text
        data["text_cut"] = cut
        data["sections"] = json.loads(r.get("sections_json") or "[]")
        data["anchors"] = json.loads(r.get("anchors_json") or "[]")
    else:
        data["snippet"] = _snippet(r.get("text"), tokens)
        data["text_len"] = len(r.get("text") or "")
    return {
        "fact_id": f"help:{r.get('path')}",
        "type": "help_article",
        "source": "HELP",
        "source_file": r.get("source_file") or "",
        "data": data,
    }

def _do_help_search(
    conn: sqlite3.Connection,
    query: str,
    ref_kind: Optional[str],
    object_full_name: Optional[str],
    limit: int,
) -> tuple[list[dict], list[str], dict]:
    limit = max(1, min(int(limit or SEARCH_LIMIT), SEARCH_LIMIT))
    fq = _fts_query(query)
    if not fq:
        return [], ["<empty_query>"], {"truncated": False, "total": 0}

    sql = """
        SELECT a.* FROM help_articles_fts f
        JOIN help_articles a ON a.id = f.rowid
        WHERE help_articles_fts MATCH ?
    """
    params: list = [fq]
    if ref_kind:
        sql += " AND a.ref_kind = ?"
        params.append(ref_kind)
    if object_full_name:
        sql += " AND a.object_full_name = ?"
        params.append(object_full_name)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    try:
        rows = _rows(conn, sql, params)
    except sqlite3.OperationalError as e:
        return [], [f"<fts_error: {e}>"], {"truncated": False, "total": 0}

    tokens = fq.split()
    facts = [_article_fact(r, tokens) for r in rows]
    return facts, [], {"truncated": False, "total": len(facts)}

def _do_help_get_article(
    conn: sqlite3.Connection,
    path: str,
) -> tuple[list[dict], list[str], dict]:
    rows = _rows(conn, "SELECT * FROM help_articles WHERE path = ?", (path,))
    if not rows:
        # Мягкий fallback: точный путь не найден — пробуем суффикс (пользователь
        # мог скопировать путь без префикса вида объекта).
        rows = _rows(
            conn,
            "SELECT * FROM help_articles WHERE path LIKE ? ORDER BY path LIMIT 5",
            ("%" + path,),
        )
    if not rows:
        return [], [path], {
            "truncated": False, "total": 0,
            **_miss_verdict("help_get_article", path),
        }
    _miss_counts.pop(("help_get_article", path), None)
    facts = [_article_fact(r, [], with_text=True) for r in rows]
    links = _rows(
        conn,
        "SELECT href, link_kind, to_object_full_name FROM help_links WHERE from_path = ?",
        (rows[0]["path"],),
    )
    facts[0]["data"]["links"] = links[:50]
    facts[0]["data"]["links_total"] = len(links)
    return facts, [], {"truncated": len(rows) > 1, "total": len(rows)}

def _verdict_struct(object_full_name: str) -> Optional[dict]:
    """Проверить ПолноеИмя в struct.db (если сервер запущен с --struct-db).
    Возвращает None, если struct.db не подключён."""
    if _struct_db_path is None or not _struct_db_path.exists():
        return None
    conn = sqlite3.connect(str(_struct_db_path))
    try:
        row = conn.execute(
            "SELECT full_name, kind FROM objects WHERE full_name = ?",
            (object_full_name,),
        ).fetchone()
        if row:
            return {"in_config": True, "kind": row[1]}
        # Мягкая подсказка: объекта нет, но есть ли похожие по суффиксу имени?
        like = conn.execute(
            "SELECT full_name FROM objects WHERE full_name LIKE ? LIMIT 5",
            ("%.%" + object_full_name.split(".")[-1],),
        ).fetchall()
        return {
            "in_config": False,
            "similar": [r[0] for r in like],
        }
    finally:
        conn.close()


def _miss_verdict(tool: str, arg: str, object_full_name: Optional[str] = None) -> dict:
    """Счётчик повторов + вердикт для пустого ответа. Гасит зацикливание LLM:
    на N-й повтор явно говорим 'объекта/статьи нет — не повторяй запрос'."""
    key = (tool, arg)
    n = _miss_counts.get(key, 0) + 1
    _miss_counts[key] = n
    verdict: dict[str, Any] = {"repeat": n, "empty_result": True}
    if object_full_name is not None:
        sv = _verdict_struct(object_full_name)
        if sv is not None:
            verdict["struct"] = sv
            if sv.get("in_config"):
                verdict["meaning"] = (
                    "объект есть в конфигурации, но статей справки по нему нет; "
                    "запрос исчерпан — не повторяй его, ищи через help_search или соседние объекты"
                )
            else:
                verdict["meaning"] = (
                    "такого объекта нет в конфигурации (struct.db): возможно, "
                    "неверное ПолноеИмя или объект из другой редакции/МП-контура; "
                    "не повторяй запрос"
                )
                if sv.get("similar"):
                    verdict["similar_in_struct"] = sv["similar"]
    if n > MISS_REPEAT_LIMIT:
        verdict["stop"] = (
            f"запрос '{tool}({arg})' уже выполнялся {n} раз с пустым результатом. "
            "Дальнейшие повторы бесполезны — смени стратегию: help_search по словам, "
            "проверь ПолноеИмя через struct-слой или переформулируй вопрос."
        )
    return verdict


def _do_help_get_object_articles(
    conn: sqlite3.Connection,
    object_full_name: str,
) -> tuple[list[dict], list[str], dict]:
    rows = _rows(
        conn,
        "SELECT * FROM help_articles WHERE object_full_name = ? "
        "ORDER BY ref_kind, path LIMIT 50",
        (object_full_name,),
    )
    if not rows:
        return [], [object_full_name], {
            "truncated": False, "total": 0,
            **_miss_verdict("help_get_object_articles", object_full_name, object_full_name),
        }
    _miss_counts.pop(("help_get_object_articles", object_full_name), None)
    facts = [_article_fact(r, []) for r in rows]
    return facts, [], {"truncated": len(rows) >= 50, "total": len(rows)}

def _do_help_get_links(
    conn: sqlite3.Connection,
    path: str,
    link_kind: Optional[str],
) -> tuple[list[dict], list[str], dict]:
    base = _rows(conn, "SELECT id FROM help_articles WHERE path = ?", (path,))
    if not base:
        return [], [path], {"truncated": False, "total": 0}
    sql = "SELECT href, link_kind, to_object_full_name FROM help_links WHERE from_path = ?"
    params: list = [path]
    if link_kind:
        sql += " AND link_kind = ?"
        params.append(link_kind)
    sql += " LIMIT 100"
    rows = _rows(conn, sql, params)
    facts = []
    for r in rows:
        facts.append(
            {
                "fact_id": f"hlink:{path}->{r.get('href')}",
                "type": "help_link",
                "source": "HELP",
                "data": {
                    "href": r.get("href"),
                    "link_kind": r.get("link_kind"),
                    "to_object_full_name": r.get("to_object_full_name"),
                },
            }
        )
    return facts, [], {"truncated": len(rows) >= 100, "total": len(rows)}

def _do_help_stats(
    conn: sqlite3.Connection,
) -> tuple[list[dict], list[str], dict]:
    total = conn.execute("SELECT COUNT(*) FROM help_articles").fetchone()[0]
    by_kind = {
        r["ref_kind"]: r["c"]
        for r in _rows(
            conn,
            "SELECT ref_kind, COUNT(*) AS c FROM help_articles GROUP BY ref_kind",
        )
    }
    linked = conn.execute(
        "SELECT COUNT(*) FROM help_articles WHERE object_full_name IS NOT NULL"
    ).fetchone()[0]
    links = conn.execute("SELECT COUNT(*) FROM help_links").fetchone()[0]
    fact = {
        "fact_id": "help:stats",
        "type": "config",
        "source": "HELP",
        "data": {
            "articles_total": total,
            "by_ref_kind": by_kind,
            "articles_with_object": linked,
            "links_total": links,
        },
    }
    return [fact], [], {"truncated": False, "total": 1}

# --------------------------------------------------------------------------
# Transport security — паттерн struct_mcp / tools/mcp_server.py
# --------------------------------------------------------------------------

def _build_transport_security(no_dns_protection: bool):
    if TransportSecuritySettings is None:
        return None
    if no_dns_protection:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    raw_origins = os.environ.get(
        "MCP_ALLOWED_ORIGINS", "https://chat.deepseek.com,chrome-extension://*"
    )
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=origins,
    )

# --------------------------------------------------------------------------
# Сборка сервера (v2: MCPServer, v1: FastMCP)
# --------------------------------------------------------------------------

def _build_server():
    """Создаёт сервер и регистрирует 5 инструментов HELP-слоя."""
    server = None
    for args in (
        ("help-unf30", "1.0.0"),
        ("help-unf30",),
    ):
        try:
            server = MCPServer(*args)
            break
        except TypeError:
            continue
    if server is None:
        raise RuntimeError("Не удалось создать MCPServer — проверьте сигнатуру SDK")

    @server.tool()
    def help_search(
        query: str,
        ref_kind: Optional[str] = None,
        object_full_name: Optional[str] = None,
        limit: int = SEARCH_LIMIT,
    ) -> str:
        """FTS5-поиск по справке (title + текст). Несколько слов через пробел = И.
        ref_kind ∈ {object, form, subsystem, configuration, template, other}.
        limit ≤ 10. Морфология не поддерживается: ищите точные формы слов."""
        facts, nf, meta = _do_help_search(
            _conn(), query, ref_kind, object_full_name, limit
        )
        return _finalize(facts, nf, meta)

    @server.tool()
    def help_get_article(path: str) -> str:
        """Полный текст статьи по её path из результатов help_search
        (напр. Documents/ЗаказПокупателя/Ext/Help/ru.html), плюс её ссылки."""
        facts, nf, meta = _do_help_get_article(_conn(), path)
        return _finalize(facts, nf, meta)

    @server.tool()
    def help_get_object_articles(object_full_name: str) -> str:
        """Все статьи справки, привязанные к объекту метаданных
        (напр. Документ.ЗаказПокупателя): сама справка объекта, справки форм, макетов."""
        facts, nf, meta = _do_help_get_object_articles(_conn(), object_full_name)
        return _finalize(facts, nf, meta)

    @server.tool()
    def help_get_links(path: str, link_kind: Optional[str] = None) -> str:
        """Ссылки из статьи. link_kind ∈ {object_help, anchor, external, external_its, other}.
        object_help.to_object_full_name — мост к слою STRUCT."""
        facts, nf, meta = _do_help_get_links(_conn(), path, link_kind)
        return _finalize(facts, nf, meta)

    @server.tool()
    def help_stats() -> str:
        """Счётчики HELP-слоя: статей, по видам, привязка к объектам, ссылки."""
        facts, nf, meta = _do_help_stats(_conn())
        return _finalize(facts, nf, meta)

    return server

# --------------------------------------------------------------------------
# Проверка схемы и точка входа
# --------------------------------------------------------------------------

def _check_schema() -> list[str]:
    conn = _conn()
    warnings: list[str] = []
    for t in ("help_articles", "help_links"):
        try:
            conn.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchall()
        except sqlite3.OperationalError:
            warnings.append(f"нет таблицы {t}")
    try:
        conn.execute("SELECT rowid FROM help_articles_fts LIMIT 1").fetchall()
    except sqlite3.OperationalError as e:
        warnings.append(f"help_articles_fts не читается ({e}) → help_search не работает")
    return warnings

def main() -> None:
    global _db_path_global

    ap = argparse.ArgumentParser(description="MCP-сервер слоя HELP (УНФ 3.0)")
    ap.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Путь к SQLite (по умолчанию: {DEFAULT_DB})",
    )
    ap.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    ap.add_argument(
        "--port", type=int, default=int(os.environ.get("MCP_PORT", "8002"))
    )
    ap.add_argument(
        "--transport",
        default="streamable-http",
        choices=["streamable-http", "sse", "stdio"],
    )
    ap.add_argument(
        "--struct-db",
        default=None,
        help="Путь к struct.db: для вердиктов 'объект есть/нет в конфигурации' "
        "на пустые ответы (опционально, но рекомендуется).",
    )
    ap.add_argument(
        "--no-dns-protection",
        action="store_true",
        help="Отключить DNS-rebinding protection (как у KB-сервера).",
    )
    args = ap.parse_args()

    global _struct_db_path

    _db_path_global = Path(args.db).resolve()
    if args.struct_db:
        _struct_db_path = Path(args.struct_db).resolve()
        if not _struct_db_path.exists():
            print(f"[help_mcp] WARN: --struct-db не найдена: {_struct_db_path}", file=sys.stderr)
            _struct_db_path = None
    if not _db_path_global.exists():
        print(f"[help_mcp] БД не найдена: {_db_path_global}", file=sys.stderr)
        sys.exit(1)

    warnings = _check_schema()
    server = _build_server()
    security = _build_transport_security(args.no_dns_protection)

    print(
        f"[help_mcp] DB:        {_db_path_global}\n"
        f"[help_mcp] SDK:       mcp v{_SDK_VERSION} "
        f"({'MCPServer' if _SDK_VERSION == 2 else 'FastMCP'})\n"
        f"[help_mcp] transport: {args.transport}\n"
        f"[help_mcp] struct_db: {_struct_db_path or 'не подключена (вердикты недоступны)'}\n"
        f"[help_mcp] endpoint:  http://{args.host}:{args.port}/mcp",
        file=sys.stderr,
    )
    if security is not None:
        try:
            print(
                f"[help_mcp] dns_protection: "
                f"{security.enable_dns_rebinding_protection}, "
                f"origins: {security.allowed_origins}",
                file=sys.stderr,
            )
        except AttributeError:
            pass
    for w in warnings:
        print(f"[help_mcp] WARN: {w}", file=sys.stderr)

    if args.transport == "stdio":
        server.run()
        return

    if _SDK_VERSION == 2:
        # Ключевое: transport_security передаётся в run(), как в KB/STRUCT-серверах
        server.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
            transport_security=security,
        )
    else:
        # v1 FastMCP
        server.settings.host = args.host  # type: ignore
        server.settings.port = args.port  # type: ignore
        server.run(transport=args.transport)

if __name__ == "__main__":
    main()
