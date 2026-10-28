#!/usr/bin/env python3
"""
MCP-сервер поиска по базе знаний 1С:УНФ 3.0 (MCP Python SDK v2).

Фаза 1: сервер умеет ТОЛЬКО поиск (retrieval). Генерацию ответа делает тот,
кто вызвал инструмент — BDS, другой агент или человек. Это сознательно:
благодаря такой границе переезд на DeepSeek API / Ollama / YandexGPT позже
не потребует менять ни карточки, ни поиск — добавится один новый инструмент.

Важно (SDK v2):
  - FastMCP переименован в MCPServer (mcp.server.mcpserver -> mcp.server);
  - host/port передаются в mcp.run(), а не через mcp.settings;
  - по умолчанию включена DNS-rebinding защита: сервер принимает только
    Origin http://localhost:* / http://127.0.0.1:*. Браузерный клиент (BDS)
    отправляет свой Origin, поэтому его нужно добавить в allowlist через
    TransportSecuritySettings.

Инструменты:
  search_kb  — top-N карточек по запросу (с фильтрами по type/status/level)
  get_card   — полный текст карточки по id
  kb_stats   — сколько карточек, из чего состоят

Запуск (из корня репозитория, в активированном .venv):

    py tools/mcp_server.py
    py tools/mcp_server.py --port 8100
    py tools/mcp_server.py --stdio
    py tools/mcp_server.py --kb D:/path/kb/unf30

Переменные окружения: KB_PATH, MCP_HOST, MCP_PORT, MCP_KB_CACHE_DIR,
MCP_ALLOWED_ORIGINS (через запятую, по умолчанию — https://chat.deepseek.com
и chrome-extension://*).
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

# --------------------------------------------------------------------------- #
# Запуск
# --------------------------------------------------------------------------- #

def _build_transport_security(no_dns_protection: bool) -> TransportSecuritySettings:
    """Настройка DNS-rebinding защиты.

    По умолчанию SDK разрешает только localhost. Браузерный клиент (BDS)
    отправляет Origin https://chat.deepseek.com (веб-версия) или
    chrome-extension://<id> (расширение) — их нужно добавить в allowlist.
    """
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
