#!/usr/bin/env python3
"""
MCP-сервер поиска по базе знаний 1С:УНФ 3.0 (MCP Python SDK v2).

Фаза 1: сервер умеет ТОЛЬКО поиск (retrieval), чтение мета-файлов и точечное 
чтение/поиск по XML-выгрузке конфигурации. Генерацию ответа делает тот, кто 
вызвал инструмент — BDS, другой агент или человек.

Инструменты:
  search_kb        — top-N карточек по запросу (с фильтрами по type/status/level)
  get_card         — полный текст карточки по id
  kb_stats         — сколько карточек, из чего состоят
  read_meta_file   — прочитать правила/архитектуру из каталога _meta/
  read_config_file — прочитать XML-файл конфигурации из _raw/unf30_xml
  search_config    — найти объект конфигурации по подстроке имени

Запуск (из корня репозитория, в активированном .venv):

    py tools/mcp_server.py
    py tools/mcp_server.py --port 8100
    py tools/mcp_server.py --stdio
    py tools/mcp_server.py --kb D:/path/kb/unf30
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from embedder import Embedder, default_cache_dir
from kb_loader import Card, load_cards

# --------------------------------------------------------------------------- #
# Индекс
# --------------------------------------------------------------------------- #

class Index:
    """Карточки + матрица эмбеддингов + поиск по косинусу."""

    def __init__(self, kb_root: Path, cache_dir: Optional[Path] = None) -> None:
        self.kb_root = Path(kb_root).resolve()
        self.cards: list[Card] = load_cards(self.kb_root)
        self.embedder = Embedder(cache_dir=cache_dir or default_cache_dir(self.kb_root))
        self.matrix = self.embedder.embed_passages([c.embedding_text() for c in self.cards])
        self._by_id = {c.id: c for c in self.cards}

    def search(
        self,
        query: str,
        top_k: int = 3,
        type: Optional[str] = None,
        status: Optional[str] = None,
        level: Optional[str] = None,
    ) -> list[tuple[Card, float]]:
        if not query or not query.strip():
            return []

        query_vector = self.embedder.embed_query(query.strip())
        scores = self.matrix @ query_vector
        order = np.argsort(-scores)

        def matches(card: Card) -> bool:
            if type and card.type.lower() != type.lower():
                return False
            if status and card.status.lower() != status.lower():
                return False
            if level and card.level.lower() != level.lower():
                return False
            return True

        results: list[tuple[Card, float]] = []
        for i in order:
            card = self.cards[int(i)]
            if not matches(card):
                continue
            results.append((card, float(scores[int(i)])))
            if len(results) >= max(1, top_k):
                break
        return results

    def get(self, card_id: str) -> Optional[Card]:
        return self._by_id.get(card_id)

_INDEX: Optional[Index] = None

def get_index() -> Index:
    """Ленивая инициализация: карточки и эмбеддинги читаются при первом вызове."""
    global _INDEX
    if _INDEX is None:
        kb_root = Path(os.environ["KB_PATH"]) if os.environ.get("KB_PATH") else _detect_kb_root(None)
        print(f"[mcp_server] каталог карточек: {kb_root}", file=sys.stderr)
        _INDEX = Index(kb_root)
        print(f"[mcp_server] карточек в индексе: {len(_INDEX.cards)}", file=sys.stderr)
    return _INDEX

def _detect_kb_root(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()

    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "kb" / "unf30",
        here.parent.parent.parent / "kb" / "unf30",
        Path.cwd() / "kb" / "unf30",
        Path.cwd() / "ai_workspace" / "kb" / "unf30",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    raise FileNotFoundError(
        "Не нашёл каталог kb/unf30. Укажите его явно: --kb <путь> или переменной KB_PATH."
    )

# --------------------------------------------------------------------------- #
# Форматирование ответа
# --------------------------------------------------------------------------- #

def _format_hit(rank: int, card: Card, score: float, body_limit: int = 1500) -> str:
    meta_bits = [f"id={card.id}"]
    for key in ("type", "level", "status"):
        if card.meta.get(key):
            meta_bits.append(f"{key}={card.meta[key]}")

    body = card.body.strip()
    if len(body) > body_limit:
        body = body[:body_limit].rstrip() + "\n…(фрагмент обрезан, полный текст — get_card)"

    return (
        f"### {rank}. {card.title}\n"
        f"`{', '.join(meta_bits)}`  \n"
        f"источник: `{card.path}` · релевантность: {score:.3f}\n\n"
        f"{body}\n"
    )

# --------------------------------------------------------------------------- #
# MCP: объявление инструментов (SDK v2)
# --------------------------------------------------------------------------- #

from mcp.server import MCPServer  # v2: было mcp.server.fastmcp.FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = MCPServer("unf30-kb")

@mcp.tool()
def search_kb(
    query: str,
    top_k: int = 3,
    type: Optional[str] = None,
    status: Optional[str] = None,
    level: Optional[str] = None,
) -> str:
    """Найти карточки базы знаний 1С:УНФ 3.0, релевантные вопросу.

    Возвращает top_k карточек в markdown: заголовок, id, источник, оценка
    релевантности и текст. Используй этот инструмент ПЕРЕД ответом на любой
    вопрос по УНФ 3.0: сначала найди карточки, потом отвечай только по ним.

    Args:
        query: вопрос или ключевые слова на естественном языке.
        top_k: сколько карточек вернуть (по умолчанию 3, разумно 3-5).
        type: фильтр по типу: object, mechanism, playbook, pitfall, case.
        status: фильтр по статусу: verified или draft.
        level: фильтр по уровню: kb или projects.
    """
    index = get_index()
    hits = index.search(query, top_k=top_k, type=type, status=status, level=level)
    if not hits:
        return f"По запросу «{query}» ничего не найдено (фильтры: type={type}, status={status}, level={level})."

    blocks = [_format_hit(i + 1, card, score) for i, (card, score) in enumerate(hits)]
    return f"Найдено карточек: {len(hits)} по запросу «{query}».\n\n" + "\n---\n\n".join(blocks)

@mcp.tool()
def get_card(card_id: str) -> str:
    """Вернуть полный текст карточки базы знаний по её id.

    Args:
        card_id: идентификатор карточки, например unf30.warehouse.orderny-sklad.
    """
    index = get_index()
    card = index.get(card_id)
    if card is None:
        return f"Карточка с id «{card_id}» не найдена. Используй search_kb, чтобы найти нужную."

    meta_lines = [f"- {k}: {v}" for k, v in card.meta.items()]
    return (
        f"# {card.title}\n\n"
        f"источник: `{card.path}`\n\n"
        f"Метаданные:\n" + "\n".join(meta_lines) + "\n\n---\n\n" + card.body.strip()
    )

@mcp.tool()
def kb_stats() -> str:
    """Показать состав базы знаний: всего карточек, по типам и статусам."""
    index = get_index()

    def counter(attr: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for card in index.cards:
            value = getattr(card, attr) or "—"
            result[value] = result.get(value, 0) + 1
        return dict(sorted(result.items(), key=lambda kv: -kv[1]))

    lines = [f"Всего карточек: {len(index.cards)}", f"Каталог: {index.kb_root}", "", "По типу:"]
    lines += [f"  {k}: {v}" for k, v in counter("type").items()]
    lines += ["", "По статусу:"]
    lines += [f"  {k}: {v}" for k, v in counter("status").items()]
    lines += ["", "По уровню:"]
    lines += [f"  {k}: {v}" for k, v in counter("level").items()]
    return "\n".join(lines)

@mcp.tool()
def read_meta_file(rel_path: str) -> str:
    """Прочитать файл из каталога _meta (правила, архитектура, ADR).

    Используй этот инструмент, чтобы узнать правила работы с базой,
    архитектуру проекта или текущие планы.

    Args:
        rel_path: путь относительно каталога _meta, например 
                  "design/01-vision.md", "conventions.md", "index.md".
    """
    index = get_index()
    repo_root = index.kb_root.parent.parent
    meta_dir = repo_root / "_meta"

    if not meta_dir.exists():
        return "Ошибка: каталог _meta не найден в репозитории."

    target_file = (meta_dir / rel_path).resolve()

    try:
        target_file.relative_to(meta_dir)
    except ValueError:
        return "Ошибка безопасности: доступ за пределы каталога _meta запрещён."

    if not target_file.exists() or not target_file.is_file():
        return f"Ошибка: файл «_meta/{rel_path}» не найден."

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
        return f"# Файл: _meta/{rel_path}\n\n{content}"
    except Exception as e:
        return f"Ошибка чтения файла: {e}"

@mcp.tool()
def read_config_file(rel_path: str, max_chars: int = 15000) -> str:
    """Прочитать XML-файл конфигурации из выгрузки _raw/unf30_xml.

    Используй этот инструмент для проверки фактов в самой конфигурации 1С:
    наличие объектов, точные имена реквизитов, перечисления, тексты модулей.
    Не используй для чтения огромных файлов целиком (например, Configuration.xml).

    Args:
        rel_path: путь относительно каталога _raw/unf30_xml, например
                  "Documents/РеализацияТоваровУслуг/Ext/ObjectModule.bsl",
                  "Enums/ВидыОпераций/.../Ext/ObjectModule.bsl".
        max_chars: лимит символов для чтения (защита от переполнения контекста).
    """
    index = get_index()
    repo_root = index.kb_root.parent.parent
    config_dir = repo_root / "_raw" / "unf30_xml"

    if not config_dir.exists():
        return "Ошибка: каталог выгрузки конфигурации '_raw/unf30_xml' не найден."

    target_file = (config_dir / rel_path).resolve()

    # Защита от path traversal
    try:
        target_file.relative_to(config_dir)
    except ValueError:
        return "Ошибка безопасности: доступ за пределы каталога конфигурации запрещён."

    if not target_file.exists() or not target_file.is_file():
        return f"Ошибка: файл «{rel_path}» не найден в выгрузке конфигурации."

    # Проверяем расширение (чтобы случайно не прочитать бинарник)
    if target_file.suffix.lower() not in (".xml", ".bsl", ".txt", ".json"):
         return f"Ошибка: чтение файлов с расширением '{target_file.suffix}' не поддерживается."

    try:
        with open(target_file, "r", encoding="utf-8-sig") as f:  # utf-8-sig борется с BOM 1С
            content = f.read(max_chars + 1)
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... (файл обрезан, превышен лимит символов)"
        return f"# Файл конфигурации: {rel_path}\n\n{content}"
    except UnicodeDecodeError:
        return "Ошибка: файл не является текстовым (возможно, бинарный) или имеет другую кодировку."
    except Exception as e:
        return f"Ошибка чтения файла: {e}"

@mcp.tool()
def search_config(
    query: str,
    kind: Optional[str] = None,
    objects_only: bool = True,
    limit: int = 50,
) -> str:
    """Найти объекты конфигурации 1С по подстроке в имени.

    Используй этот инструмент, когда нужно узнать точное имя документа,
    справочника, перечисления или регистра. Например: «есть ли документ,
    фиксирующий выполнение этапа производства?» — запрос «этап» с
    kind=Document. Инструмент читает реестр ConfigDumpInfo.xml из
    _raw/unf30_xml и не требует чтения тяжёлых XML-файлов.

    Args:
        query: подстрока имени, например «этап» или «Спецификац».
        kind: фильтр по типу: Document, Catalog, Enum, AccumulationRegister,
              InformationRegister, Report, DataProcessor.
        objects_only: только сами объекты (без реквизитов и модулей).
        limit: максимум строк в ответе.
    """
    try:
        from config_search import ConfigIndex
    except ImportError:
        return "Ошибка: модуль config_search.py не найден рядом с mcp_server.py."

    index = get_index()
    repo_root = index.kb_root.parent.parent
    dump_path = repo_root / "_raw" / "unf30_xml" / "ConfigDumpInfo.xml"

    try:
        cfg = ConfigIndex(dump_path)
        rows = cfg.search(
            query,
            kind=kind,
            objects_only=objects_only,
            limit=limit,
        )
    except FileNotFoundError as exc:
        return f"Ошибка: {exc}"
    except Exception as exc:
        return f"Ошибка поиска по конфигурации: {exc}"

    if not rows:
        return f"Ничего не найдено по запросу «{query}» (kind={kind})."

    lines = [f"Найдено {len(rows)} (лимит {limit}):", ""]
    for entry in rows:
        suffix = "" if entry.sub is None else f"  [{entry.sub}]"
        lines.append(f"- {entry.obj}{suffix}  ({entry.kind})")
    return "\n".join(lines)

# --------------------------------------------------------------------------- #
# Запуск
# --------------------------------------------------------------------------- #

def _build_transport_security(no_dns_protection: bool) -> TransportSecuritySettings:
    """Настройка DNS-rebinding защиты."""
    if no_dns_protection:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    raw_origins = os.environ.get(
        "MCP_ALLOWED_ORIGINS",
        "https://chat.deepseek.com,chrome-extension://*",
    )
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=origins,
    )

def main() -> None:
    parser = argparse.ArgumentParser(description="MCP-сервер поиска по базе знаний УНФ 3.0")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    parser.add_argument("--kb", default=None, help="путь к каталогу карточек (kb/unf30)")
    parser.add_argument(
        "--no-dns-protection",
        action="store_true",
        help="отключить проверку Origin (только для локальной отладки)",
    )
    args = parser.parse_args()

    kb_root = _detect_kb_root(args.kb)
    os.environ["KB_PATH"] = str(kb_root)
    get_index()  # прогреваем индекс

    security = _build_transport_security(args.no_dns_protection)

    if args.transport == "stdio":
        print("[mcp_server] транспорт: stdio", file=sys.stderr)
        mcp.run()
    else:
        print(f"[mcp_server] транспорт: streamable-http, http://{args.host}:{args.port}/mcp", file=sys.stderr)
        print(f"[mcp_server] разрешённые Origin: {security.allowed_origins}", file=sys.stderr)
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            transport_security=security,
        )

if __name__ == "__main__":
    main()
