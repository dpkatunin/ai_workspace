#!/usr/bin/env python3
"""
struct_mcp.py — MCP-сервер слоя STRUCT (УНФ 3.0).

Совместим с двумя поколениями официального MCP Python SDK:
  • v2.x (MCPServer) — установлен у пользователя (mcp 2.3.0);
  • v1.x (FastMCP)  — старый API, fallback на случай отката.

Ключевая деталь v2: `transport_security` передаётся в `run()`,
а не в конструктор `MCPServer`. Паттерн скопирован с tools/mcp_server.py
(KB-сервер работает на том же SDK v2.3.0).

9 инструментов из tools.md. Лимит ответа — 15 КБ, флаг `truncated`.
Стабильные ID фактов: obj:, attr:, tch:, move:, link:, enum:, cfg:.

Запуск (из корня ai_workspace/):
    .venv\\Scripts\\python.exe projects/unf30-kb/struct/struct_mcp.py \\
        --db projects/unf30-kb/struct/data/struct.db --port 8001
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

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "struct.db"
RESPONSE_LIMIT_BYTES = 15 * 1024
DEFAULT_ARRAY_LIMIT = 20
SNIPPET_RADIUS = 80
SNIPPET_FULL_THRESHOLD = 200
OBJECT_ATTR_LIMIT = 30

# --------------------------------------------------------------------------
# Подключение к БД
# --------------------------------------------------------------------------

_db_path_global: Path = DEFAULT_DB
_conn_global: Optional[sqlite3.Connection] = None
_schema_cache: dict[str, set[str]] = {}

def _conn() -> sqlite3.Connection:
    global _conn_global
    if _conn_global is None:
        _conn_global = sqlite3.connect(
            str(_db_path_global), check_same_thread=False
        )
        _conn_global.row_factory = sqlite3.Row
    return _conn_global

def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _schema_cache:
        try:
            _schema_cache[table] = {
                r[1] for r in conn.execute(f"PRAGMA table_info({table})")
            }
        except sqlite3.OperationalError:
            _schema_cache[table] = set()
    return _schema_cache[table]

def _col(conn: sqlite3.Connection, table: str, *candidates: str) -> Optional[str]:
    cols = _cols(conn, table)
    for c in candidates:
        if c in cols:
            return c
    return None

def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    return bool(_cols(conn, table))

# --------------------------------------------------------------------------
# Хелперы
# --------------------------------------------------------------------------

def _rows(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def _pick(d: dict, *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None

def _fts_query(raw: str) -> Optional[str]:
    tokens = re.findall(r"\w+", raw or "", re.UNICODE)
    if not tokens:
        return None
    return " ".join(tokens)

def _snippet(text: Optional[str], tokens: list[str]) -> Optional[str]:
    if not text:
        return text
    if len(text) <= SNIPPET_FULL_THRESHOLD:
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
    return text[:SNIPPET_FULL_THRESHOLD] + "..."

# --------------------------------------------------------------------------
# Формирование ответа с лимитом
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

def _do_search_objects(
    conn: sqlite3.Connection,
    query: str,
    kind: Optional[str],
    subsystem: Optional[str],
    limit: int,
) -> tuple[list[dict], list[str], dict]:
    limit = max(1, min(int(limit or 20), 20))
    fq = _fts_query(query)
    if not fq:
        return [], ["<empty_query>"], {"truncated": False, "total": 0}

    sql = """
        SELECT o.* FROM objects_fts f
        JOIN objects o ON o.id = f.rowid
        WHERE objects_fts MATCH ?
    """
    params: list = [fq]
    if kind:
        sql += " AND o.kind = ?"
        params.append(kind)
    if subsystem:
        sql += " AND o.subsystem = ?"
        params.append(subsystem)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    try:
        rows = _rows(conn, sql, params)
    except sqlite3.OperationalError as e:
        return [], [f"<fts_error: {e}>"], {"truncated": False, "total": 0}

    tokens = fq.split()
    facts = []
    for r in rows:
        facts.append(
            {
                "fact_id": f"obj:{r.get('full_name')}",
                "type": "object",
                "source": "STRUCT",
                "source_file": _pick(r, "source_file") or "",
                "data": {
                    "kind": r.get("kind"),
                    "full_name": r.get("full_name"),
                    "name": r.get("name"),
                    "synonym": r.get("synonym"),
                    "comment": _snippet(r.get("comment"), tokens),
                    "subsystem": r.get("subsystem"),
                },
            }
        )
    return facts, [], {"truncated": False, "total": len(facts)}

def _do_get_object(
    conn: sqlite3.Connection,
    full_name: str,
    subsystem: Optional[str],
    attributes_limit: int = OBJECT_ATTR_LIMIT,
) -> tuple[list[dict], list[str], dict]:
    sql = "SELECT * FROM objects WHERE full_name = ?"
    params: list = [full_name]
    if subsystem:
        sql += " AND subsystem = ?"
        params.append(subsystem)
    rows = _rows(conn, sql, params)
    if not rows:
        return [], [full_name], {"truncated": False, "total": 0}

    obj = rows[0]
    oid = obj["id"]

    a_obj_col = _col(conn, "attributes", "object_id", "obj_id", "owner_id")
    a_ord_col = _col(conn, "attributes", "ord", "sort_order", "position")
    attrs_total = conn.execute(
        f"SELECT COUNT(*) FROM attributes WHERE {a_obj_col} = ?", (oid,)
    ).fetchone()[0]
    order_by = f"COALESCE({a_ord_col}, 0), name" if a_ord_col else "name"
    attrs = _rows(
        conn,
        f"SELECT * FROM attributes WHERE {a_obj_col} = ? ORDER BY {order_by} LIMIT ?",
        (oid, attributes_limit),
    )

    at_attr_col = _col(conn, "attribute_types", "attribute_id", "attr_id", "attribute")
    at_type_col = _col(
        conn, "attribute_types", "type_name", "type", "type_full_name", "full_name"
    )
    types_by_attr: dict[Any, list[str]] = {}
    if attrs and at_attr_col and at_type_col:
        ids = [a["id"] for a in attrs]
        q = (
            f"SELECT {at_attr_col} AS aid, {at_type_col} AS tname "
            f"FROM attribute_types WHERE {at_attr_col} IN ({','.join('?' * len(ids))})"
        )
        for t in _rows(conn, q, ids):
            types_by_attr.setdefault(t["aid"], []).append(t["tname"])

    props_raw = _pick(obj, "properties_json", "properties", "props", "props_json")
    props: Any = {}
    if props_raw:
        try:
            props = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
        except (json.JSONDecodeError, TypeError):
            props = {"_raw": str(props_raw)}

    tchs: list[dict] = []
    if _has_table(conn, "tabular_sections"):
        ts_obj_col = _col(conn, "tabular_sections", "object_id", "obj_id", "owner_id")
        if ts_obj_col:
            tchs = _rows(
                conn,
                f"SELECT * FROM tabular_sections WHERE {ts_obj_col} = ? ORDER BY name",
                (oid,),
            )

    moves: list[dict] = []
    if _has_table(conn, "movements"):
        m_doc_col = _col(conn, "movements", "document_id", "object_id", "doc_id")
        m_reg_col = _col(
            conn, "movements", "register_full_name", "register", "register_name"
        )
        if m_doc_col and m_reg_col:
            moves = _rows(
                conn,
                f"SELECT * FROM movements WHERE {m_doc_col} = ? "
                f"ORDER BY {m_reg_col} LIMIT 50",
                (oid,),
            )

    enum_vals: list[dict] = []
    if obj.get("kind") == "Перечисление" and _has_table(conn, "enum_values"):
        ev_enum_col = _col(conn, "enum_values", "enum_id", "object_id", "owner_id")
        if ev_enum_col:
            ev_ord_col = _col(conn, "enum_values", "ord", "sort_order", "position")
            ob = f"COALESCE({ev_ord_col}, 0), name" if ev_ord_col else "name"
            enum_vals = _rows(
                conn,
                f"SELECT * FROM enum_values WHERE {ev_enum_col} = ? "
                f"ORDER BY {ob} LIMIT 200",
                (oid,),
            )

    predefined: list[dict] = []
    if _has_table(conn, "predefined"):
        p_obj_col = _col(conn, "predefined", "object_id", "obj_id", "owner_id")
        if p_obj_col:
            try:
                predefined = _rows(
                    conn,
                    f"SELECT * FROM predefined WHERE {p_obj_col} = ? LIMIT 50",
                    (oid,),
                )
            except sqlite3.OperationalError:
                predefined = []

    facts: list[dict] = [
        {
            "fact_id": f"obj:{obj.get('full_name')}",
            "type": "object",
            "source": "STRUCT",
            "source_file": _pick(obj, "source_file") or "",
            "data": {
                "kind": obj.get("kind"),
                "full_name": obj.get("full_name"),
                "name": obj.get("name"),
                "synonym": obj.get("synonym"),
                "comment": obj.get("comment"),
                "subsystem": obj.get("subsystem"),
                "subsystem_path": obj.get("subsystem_path"),
                "properties": props,
                "predefined": predefined,
            },
        }
    ]

    for a in attrs:
        ts_data = types_by_attr.get(a["id"], [])
        returned_types = ts_data[:DEFAULT_ARRAY_LIMIT]
        facts.append(
            {
                "fact_id": f"attr:{obj.get('full_name')}.{a.get('name')}",
                "type": "attribute",
                "source": "STRUCT",
                "data": {
                    "name": a.get("name"),
                    "synonym": a.get("synonym"),
                    "role": a.get("role"),
                    "check_fill": a.get("check_fill"),
                    "types": returned_types,
                    "types_total": len(ts_data),
                    "types_truncated": len(ts_data) > len(returned_types),
                },
            }
        )

    for t in tchs:
        facts.append(
            {
                "fact_id": f"tch:{obj.get('full_name')}.{t.get('name')}",
                "type": "tabular_section",
                "source": "STRUCT",
                "data": {"name": t.get("name"), "synonym": t.get("synonym")},
            }
        )

    for m in moves:
        reg = _pick(m, "register_full_name", "register", "register_name")
        facts.append(
            {
                "fact_id": f"move:{obj.get('full_name')}->{reg}",
                "type": "movement",
                "source": "STRUCT",
                "data": {"register": reg},
            }
        )

    for ev in enum_vals:
        facts.append(
            {
                "fact_id": f"enum:{obj.get('full_name')}.{ev.get('name')}",
                "type": "enum_value",
                "source": "STRUCT",
                "data": {
                    "name": ev.get("name"),
                    "synonym": ev.get("synonym"),
                    "comment": ev.get("comment"),
                },
            }
        )

    meta = {
        "truncated": attrs_total > len(attrs),
        "total_attributes": attrs_total,
        "returned_attributes": len(attrs),
    }
    return facts, [], meta

def _do_get_object_links(
    conn: sqlite3.Connection,
    full_name: str,
    link_type: Optional[str],
    subsystem: Optional[str],
    limit: int = 50,
) -> tuple[list[dict], list[str], dict]:
    limit = max(1, min(int(limit or 50), 50))
    obj_rows = _rows(
        conn, "SELECT * FROM objects WHERE full_name = ?", (full_name,)
    )
    if not obj_rows:
        return [], [full_name], {"truncated": False, "total": 0}
    if subsystem and obj_rows[0].get("subsystem") != subsystem:
        return [], [full_name], {"truncated": False, "total": 0}
    oid = obj_rows[0]["id"]

    src_col = _col(conn, "object_links", "source_id", "source_object_id", "object_id")
    lt_col = _col(conn, "object_links", "link_type", "type", "kind")
    tgt_col = _col(
        conn, "object_links", "target_full_name", "target_name", "target", "target_ref"
    )
    if not src_col or not tgt_col:
        return [], ["<schema:object_links:missing_columns>"], {"truncated": False, "total": 0}

    sql = f"SELECT * FROM object_links WHERE {src_col} = ?"
    params: list = [oid]
    if link_type and lt_col:
        sql += f" AND {lt_col} = ?"
        params.append(link_type)
    sql += " LIMIT ?"
    params.append(limit)

    rows = _rows(conn, sql, params)
    facts = []
    for r in rows:
        lt = _pick(r, lt_col) if lt_col else None
        tgt = r.get(tgt_col)
        facts.append(
            {
                "fact_id": f"link:{full_name}.{lt}.{tgt}",
                "type": "link",
                "source": "STRUCT",
                "data": {"link_type": lt, "target": tgt},
            }
        )
    return facts, [], {"truncated": len(rows) >= limit, "total": len(rows)}

def _do_get_register_writers(
    conn: sqlite3.Connection,
    register_full_name: str,
    subsystem: Optional[str],
    limit: int = 100,
) -> tuple[list[dict], list[str], dict]:
    limit = max(1, min(int(limit or 100), 100))
    reg_col = _col(
        conn, "movements", "register_full_name", "register", "register_name"
    )
    if not reg_col:
        return [], ["<schema:movements:missing_register>"], {"truncated": False, "total": 0}

    doc_col = _col(conn, "movements", "document_id", "object_id", "doc_id")
    if not doc_col:
        return [], ["<schema:movements:missing_document>"], {"truncated": False, "total": 0}

    sql = (
        f"SELECT m.*, o.full_name AS doc_full_name, o.subsystem AS doc_subsystem "
        f"FROM movements m JOIN objects o ON o.id = m.{doc_col} "
        f"WHERE m.{reg_col} = ?"
    )
    params: list = [register_full_name]
    if subsystem:
        sql += " AND o.subsystem = ?"
        params.append(subsystem)
    sql += " LIMIT ?"
    params.append(limit)

    rows = _rows(conn, sql, params)
    facts = []
    for r in rows:
        doc = r.get("doc_full_name")
        facts.append(
            {
                "fact_id": f"link:{doc}.registrator.{register_full_name}",
                "type": "link",
                "source": "STRUCT",
                "data": {"link_type": "registrator", "target": doc},
            }
        )
    return facts, [], {"truncated": len(rows) >= limit, "total": len(rows)}

def _do_get_document_movements(
    conn: sqlite3.Connection,
    document_full_name: str,
    subsystem: Optional[str],
    limit: int = 50,
) -> tuple[list[dict], list[str], dict]:
    limit = max(1, min(int(limit or 50), 50))
    obj_rows = _rows(
        conn, "SELECT * FROM objects WHERE full_name = ?", (document_full_name,)
    )
    if not obj_rows:
        return [], [document_full_name], {"truncated": False, "total": 0}
    if subsystem and obj_rows[0].get("subsystem") != subsystem:
        return [], [document_full_name], {"truncated": False, "total": 0}
    oid = obj_rows[0]["id"]

    m_doc_col = _col(conn, "movements", "document_id", "object_id", "doc_id")
    m_reg_col = _col(conn, "movements", "register_full_name", "register", "register_name")
    if not m_doc_col or not m_reg_col:
        return [], ["<schema:movements:missing_columns>"], {"truncated": False, "total": 0}

    rows = _rows(
        conn,
        f"SELECT * FROM movements WHERE {m_doc_col} = ? "
        f"ORDER BY {m_reg_col} LIMIT ?",
        (oid, limit),
    )
    facts = []
    for r in rows:
        reg = r.get(m_reg_col)
        facts.append(
            {
                "fact_id": f"move:{document_full_name}->{reg}",
                "type": "movement",
                "source": "STRUCT",
                "data": {"register": reg},
            }
        )
    return facts, [], {"truncated": len(rows) >= limit, "total": len(rows)}

def _do_get_attribute(
    conn: sqlite3.Connection,
    object_full_name: str,
    attribute_name: str,
    types_limit: int,
) -> tuple[list[dict], list[str], dict]:
    types_limit = max(1, min(int(types_limit or 20), 20))
    obj_rows = _rows(
        conn, "SELECT * FROM objects WHERE full_name = ?", (object_full_name,)
    )
    if not obj_rows:
        return [], [object_full_name], {"truncated": False, "total": 0}
    oid = obj_rows[0]["id"]

    a_obj_col = _col(conn, "attributes", "object_id", "obj_id", "owner_id")
    attr_rows = _rows(
        conn,
        f"SELECT * FROM attributes WHERE {a_obj_col} = ? AND name = ?",
        (oid, attribute_name),
    )
    if not attr_rows:
        return [], [f"{object_full_name}.{attribute_name}"], {"truncated": False, "total": 0}

    a = attr_rows[0]
    at_attr_col = _col(conn, "attribute_types", "attribute_id", "attr_id", "attribute")
    at_type_col = _col(
        conn, "attribute_types", "type_name", "type", "type_full_name", "full_name"
    )
    types: list[str] = []
    if at_attr_col and at_type_col:
        types = [
            r["tname"]
            for r in _rows(
                conn,
                f"SELECT {at_type_col} AS tname FROM attribute_types "
                f"WHERE {at_attr_col} = ?",
                (a["id"],),
            )
        ]
    returned = types[:types_limit]

    fact = {
        "fact_id": f"attr:{object_full_name}.{attribute_name}",
        "type": "attribute",
        "source": "STRUCT",
        "data": {
            "name": a.get("name"),
            "synonym": a.get("synonym"),
            "role": a.get("role"),
            "check_fill": a.get("check_fill"),
            "types": returned,
            "types_total": len(types),
        },
    }
    meta = {
        "truncated": len(types) > len(returned),
        "types_total": len(types),
        "types_returned": len(returned),
    }
    return [fact], [], meta

def _do_get_enum_values(
    conn: sqlite3.Connection,
    enum_full_name: str,
    subsystem: Optional[str],
    limit: int = 200,
) -> tuple[list[dict], list[str], dict]:
    limit = max(1, min(int(limit or 200), 200))
    obj_rows = _rows(
        conn, "SELECT * FROM objects WHERE full_name = ?", (enum_full_name,)
    )
    if not obj_rows:
        return [], [enum_full_name], {"truncated": False, "total": 0}
    obj = obj_rows[0]
    if subsystem and obj.get("subsystem") != subsystem:
        return [], [enum_full_name], {"truncated": False, "total": 0}
    if obj.get("kind") != "Перечисление":
        return [], [enum_full_name], {
            "truncated": False,
            "total": 0,
            "note": f"kind={obj.get('kind')} != Перечисление",
        }
    oid = obj["id"]

    ev_enum_col = _col(conn, "enum_values", "enum_id", "object_id", "owner_id")
    if not ev_enum_col:
        return [], ["<schema:enum_values:missing_enum_id>"], {"truncated": False, "total": 0}
    ev_ord_col = _col(conn, "enum_values", "ord", "sort_order", "position")
    ob = f"COALESCE({ev_ord_col}, 0), name" if ev_ord_col else "name"

    rows = _rows(
        conn,
        f"SELECT * FROM enum_values WHERE {ev_enum_col} = ? ORDER BY {ob} LIMIT ?",
        (oid, limit),
    )
    facts = []
    for ev in rows:
        facts.append(
            {
                "fact_id": f"enum:{enum_full_name}.{ev.get('name')}",
                "type": "enum_value",
                "source": "STRUCT",
                "data": {
                    "name": ev.get("name"),
                    "synonym": ev.get("synonym"),
                    "comment": ev.get("comment"),
                },
            }
        )
    return facts, [], {"truncated": len(rows) >= limit, "total": len(rows)}

def _do_get_config_info(
    conn: sqlite3.Connection,
) -> tuple[list[dict], list[str], dict]:
    if not _has_table(conn, "config"):
        return [], ["<schema:config:missing_table>"], {"truncated": False, "total": 0}
    rows = _rows(conn, "SELECT * FROM config")
    facts = []
    for r in rows:
        name = _pick(r, "name", "config_name", "synonym")
        facts.append(
            {
                "fact_id": f"cfg:{name}",
                "type": "config",
                "source": "STRUCT",
                "data": {
                    "name": name,
                    "version": _pick(r, "version", "ver"),
                    "dump_date": _pick(r, "dump_date", "date", "dump_at"),
                    "source_file": _pick(r, "source_file"),
                },
            }
        )
    return facts, [], {"truncated": False, "total": len(facts)}

def _do_validate_names(
    conn: sqlite3.Connection,
    full_names: list[str],
) -> tuple[list[dict], list[str], dict]:
    if not full_names:
        return [], [], {"truncated": False, "total": 0}
    seen: set[str] = set()
    cleaned: list[str] = []
    for n in full_names:
        n2 = (n or "").strip()
        if n2 and n2 not in seen:
            seen.add(n2)
            cleaned.append(n2)

    known: list[str] = []
    for i in range(0, len(cleaned), 500):
        chunk = cleaned[i : i + 500]
        q = (
            "SELECT full_name FROM objects WHERE full_name IN ("
            + ",".join("?" * len(chunk))
            + ")"
        )
        found = {r["full_name"] for r in _rows(conn, q, chunk)}
        known.extend([n for n in chunk if n in found])

    known_set = set(known)
    unknown = [n for n in cleaned if n not in known_set]

    fact = {
        "fact_id": "validation:names",
        "type": "validation",
        "source": "STRUCT",
        "data": {"known": known, "unknown": unknown},
    }
    return [fact], [], {"truncated": False, "total": len(cleaned)}

# --------------------------------------------------------------------------
# Transport security — тот же паттерн, что в tools/mcp_server.py
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
    """Создаёт сервер и регистрирует 9 инструментов. Без transport_security —
    он передаётся позже в run(), как в KB-сервере."""
    server = None
    for args in (
        ("struct-unf30", "1.0.0"),
        ("struct-unf30",),
    ):
        try:
            server = MCPServer(*args)
            break
        except TypeError:
            continue
    if server is None:
        raise RuntimeError("Не удалось создать MCPServer — проверьте сигнатуру SDK")

    @server.tool()
    def search_objects(
        query: str,
        kind: Optional[str] = None,
        subsystem: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """FTS5-поиск объектов по full_name, name, synonym, comment.
        Несколько слов через пробел = логическое И. limit ≤ 20."""
        facts, nf, meta = _do_search_objects(_conn(), query, kind, subsystem, limit)
        return _finalize(facts, nf, meta)

    @server.tool()
    def get_object(
        full_name: str,
        subsystem: Optional[str] = None,
        attributes_limit: int = OBJECT_ATTR_LIMIT,
    ) -> str:
        """Полное описание объекта: свойства, реквизиты (≤30), ТЧ, движения,
        значения перечисления, predefined (заглушка на будущее)."""
        facts, nf, meta = _do_get_object(
            _conn(), full_name, subsystem, attributes_limit
        )
        return _finalize(facts, nf, meta)

    @server.tool()
    def get_object_links(
        full_name: str,
        link_type: Optional[str] = None,
        subsystem: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """Ссылки объекта. link_type ∈ {owner, registrator, based_on, movement}.
        limit ≤ 50."""
        facts, nf, meta = _do_get_object_links(
            _conn(), full_name, link_type, subsystem, limit
        )
        return _finalize(facts, nf, meta)

    @server.tool()
    def get_register_writers(
        register_full_name: str,
        subsystem: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        """Документы, которые пишут движения в указанный регистр. limit ≤ 100."""
        facts, nf, meta = _do_get_register_writers(
            _conn(), register_full_name, subsystem, limit
        )
        return _finalize(facts, nf, meta)

    @server.tool()
    def get_document_movements(
        document_full_name: str,
        subsystem: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """Регистры, в которые пишет движения указанный документ. limit ≤ 50."""
        facts, nf, meta = _do_get_document_movements(
            _conn(), document_full_name, subsystem, limit
        )
        return _finalize(facts, nf, meta)

    @server.tool()
    def get_attribute(
        object_full_name: str,
        attribute_name: str,
        types_limit: int = DEFAULT_ARRAY_LIMIT,
    ) -> str:
        """Один реквизит объекта + его типы (≤20)."""
        facts, nf, meta = _do_get_attribute(
            _conn(), object_full_name, attribute_name, types_limit
        )
        return _finalize(facts, nf, meta)

    @server.tool()
    def get_enum_values(
        enum_full_name: str,
        subsystem: Optional[str] = None,
        limit: int = 200,
    ) -> str:
        """Значения перечисления. limit ≤ 200."""
        facts, nf, meta = _do_get_enum_values(
            _conn(), enum_full_name, subsystem, limit
        )
        return _finalize(facts, nf, meta)

    @server.tool()
    def get_config_info() -> str:
        """Сведения о конфигурации: name, version, dump_date, source_file."""
        facts, nf, meta = _do_get_config_info(_conn())
        return _finalize(facts, nf, meta)

    @server.tool()
    def validate_names(full_names: list[str]) -> str:
        """Валидатор имён 1С. Возвращает { known: [...], unknown: [...] }.
        Используется как пост-процессор ответа модели: все ПолноеИмя,
        упомянутые LLM, прогоняются здесь; unknown → блок/пометка."""
        facts, nf, meta = _do_validate_names(_conn(), full_names)
        return _finalize(facts, nf, meta)

    return server

# --------------------------------------------------------------------------
# Проверка схемы и точка входа
# --------------------------------------------------------------------------

def _check_schema() -> list[str]:
    conn = _conn()
    warnings: list[str] = []
    required = ["objects", "attributes", "attribute_types"]
    for t in required:
        if not _has_table(conn, t):
            warnings.append(f"нет таблицы {t}")
    try:
        conn.execute("SELECT rowid FROM objects_fts LIMIT 1").fetchall()
    except sqlite3.OperationalError as e:
        warnings.append(f"objects_fts не читается ({e}) → search_objects не работает")
    return warnings

def main() -> None:
    global _db_path_global

    ap = argparse.ArgumentParser(description="MCP-сервер слоя STRUCT (УНФ 3.0)")
    ap.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Путь к SQLite (по умолчанию: {DEFAULT_DB})",
    )
    ap.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    ap.add_argument(
        "--port", type=int, default=int(os.environ.get("MCP_PORT", "8001"))
    )
    ap.add_argument(
        "--transport",
        default="streamable-http",
        choices=["streamable-http", "sse", "stdio"],
    )
    ap.add_argument(
        "--no-dns-protection",
        action="store_true",
        help="Отключить DNS-rebinding protection (как у KB-сервера).",
    )
    args = ap.parse_args()

    _db_path_global = Path(args.db).resolve()
    if not _db_path_global.exists():
        print(f"[struct_mcp] БД не найдена: {_db_path_global}", file=sys.stderr)
        sys.exit(1)

    warnings = _check_schema()
    server = _build_server()
    security = _build_transport_security(args.no_dns_protection)

    print(
        f"[struct_mcp] DB:        {_db_path_global}\n"
        f"[struct_mcp] SDK:       mcp v{_SDK_VERSION} "
        f"({'MCPServer' if _SDK_VERSION == 2 else 'FastMCP'})\n"
        f"[struct_mcp] transport: {args.transport}\n"
        f"[struct_mcp] endpoint:  http://{args.host}:{args.port}/mcp",
        file=sys.stderr,
    )
    if security is not None:
        try:
            print(
                f"[struct_mcp] dns_protection: "
                f"{security.enable_dns_rebinding_protection}, "
                f"origins: {security.allowed_origins}",
                file=sys.stderr,
            )
        except AttributeError:
            pass
    for w in warnings:
        print(f"[struct_mcp] WARN: {w}", file=sys.stderr)

    if args.transport == "stdio":
        server.run()
        return

    if _SDK_VERSION == 2:
        # Ключевое: transport_security передаётся в run(), как в KB-сервере
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
