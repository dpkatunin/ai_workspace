#!/usr/bin/env python3
# MCP-сервер поиска по базе знаний 1С:УНФ 3.0 (MCP Python SDK v2).

from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional
import numpy as np

from embedder import Embedder, default_cache_dir
from kb_loader import Card, load_cards
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

# --- Индекс карточек ---

class Index:
    def __init__(self, kb_root: Path, cache_dir: Optional[Path] = None) -> None:
        self.kb_root = Path(kb_root).resolve()
        self.cards: list[Card] = load_cards(self.kb_root)
        self.embedder = Embedder(cache_dir=cache_dir or default_cache_dir(self.kb_root))
        self.matrix = self.embedder.embed_passages([c.embedding_text() for c in self.cards])
        self._by_id = {c.id: c for c in self.cards}

    def search(self, query: str, top_k: int = 3, type: Optional[str] = None, status: Optional[str] = None, level: Optional[str] = None) -> list[tuple[Card, float]]:
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
    raise FileNotFoundError("Не нашёл каталог kb/unf30. Укажите его явно: --kb <путь> или переменной KB_PATH.")

# --- Форматирование ---

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

# --- MCP Инструменты ---

mcp = MCPServer("unf30-kb")

@mcp.tool()
def search_kb(query: str, top_k: int = 3, type: Optional[str] = None, status: Optional[str] = None, level: Optional[str] = None) -> str:
    # Найти карточки базы знаний по запросу.
    index = get_index()
    hits = index.search(query, top_k=top_k, type=type, status=status, level=level)
    if not hits:
        return f"По запросу «{query}» ничего не найдено (фильтры: type={type}, status={status}, level={level})."
    blocks = [_format_hit(i + 1, card, score) for i, (card, score) in enumerate(hits)]
    return f"Найдено карточек: {len(hits)} по запросу «{query}».\n\n" + "\n---\n\n".join(blocks)

@mcp.tool()
def get_card(card_id: str) -> str:
    # Вернуть полный текст карточки по id.
    index = get_index()
    card = index.get(card_id)
    if card is None:
        return f"Карточка с id «{card_id}» не найдена."
    meta_lines = [f"- {k}: {v}" for k, v in card.meta.items()]
    return f"# {card.title}\n\nисточник: `{card.path}`\n\nМетаданные:\n" + "\n".join(meta_lines) + "\n\n---\n\n" + card.body.strip()

@mcp.tool()
def kb_stats() -> str:
    # Показать состав базы знаний.
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
def read_meta_file(rel_path: str, start_char: int = 0, max_chars: int = 10000) -> str:
    # Прочитать файл из каталога _meta (с поддержкой пагинации для длинных файлов).
    index = get_index()
    repo_root = index.kb_root.parent.parent
    meta_dir = repo_root / "_meta"
    if not meta_dir.exists():
        return "Ошибка: каталог _meta не найден."
    target_file = (meta_dir / rel_path).resolve()
    try:
        target_file.relative_to(meta_dir)
    except ValueError:
        return "Ошибка безопасности: доступ за пределы _meta запрещён."
    if not target_file.exists() or not target_file.is_file():
        return f"Ошибка: файл «_meta/{rel_path}» не найден."
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        total_len = len(content)
        if start_char >= total_len:
            return f"Достигнут конец файла. Всего символов: {total_len}."

        chunk = content[start_char:start_char + max_chars]
        end_char = start_char + len(chunk)

        result = f"# Файл: _meta/{rel_path} (символы {start_char}-{end_char} из {total_len})\n\n{chunk}"
        
        if end_char < total_len:
            result += f"\n\n... (файл обрезан, для продолжения вызовите read_meta_file с start_char={end_char})"
            
        return result
    except Exception as e:
        return f"Ошибка чтения: {e}"

@mcp.tool()
def search_config(query: str, kind: Optional[str] = None, limit: int = 50) -> str:
    # Найти объекты конфигурации 1С по подстроке в имени.
    index = get_index()
    repo_root = index.kb_root.parent.parent
    index_file = repo_root / "_raw" / "unf30_xml" / "config_index.json"
    if not index_file.exists():
        return "Ошибка: config_index.json не найден. Запустите tools/parse_config_index.py"
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except Exception as e:
        return f"Ошибка чтения индекса: {e}"
    query_lower = query.lower()
    results = []
    for obj in config_data:
        if kind and obj.get("kind", "").lower() != kind.lower():
            continue
        if query_lower in obj.get("name", "").lower() or query_lower in obj.get("synonym", "").lower():
            results.append(obj)
    if not results:
        return f"В конфигурации не найдено объектов по запросу «{query}»."
    total_found = len(results)
    results = results[:limit]
    lines = [f"Найдено объектов: {total_found} (показано {len(results)}):\n"]
    for obj in results:
        syn = f" (синоним: «{obj['synonym']}»)" if obj['synonym'] else ""
        lines.append(f"- **{obj['kind']}**: `{obj['name']}`{syn}")
    if total_found > limit:
        lines.append(f"\n... (ещё {total_found - limit} скрыто)")
    return "\n".join(lines)

@mcp.tool()
def read_config_file(rel_path: str, max_chars: int = 15000) -> str:
    # Прочитать XML-файл конфигурации.
    index = get_index()
    repo_root = index.kb_root.parent.parent
    config_dir = repo_root / "_raw" / "unf30_xml"
    if not config_dir.exists():
        return "Ошибка: каталог '_raw/unf30_xml' не найден."
    target_file = (config_dir / rel_path).resolve()
    try:
        target_file.relative_to(config_dir)
    except ValueError:
        return "Ошибка безопасности: доступ за пределы каталога конфигурации запрещён."
    if not target_file.exists() or not target_file.is_file():
        return f"Ошибка: файл «{rel_path}» не найден."
    if target_file.suffix.lower() not in (".xml", ".bsl", ".txt", ".json"):
         return "Ошибка: недопустимое расширение файла."
    try:
        with open(target_file, "r", encoding="utf-8-sig") as f:
            content = f.read(max_chars + 1)
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... (файл обрезан)"
        return f"# Файл конфигурации: {rel_path}\n\n{content}"
    except Exception as e:
        return f"Ошибка чтения: {e}"

@mcp.tool()
def verify_card_facts(card_text: str) -> str:
    # Проверить упоминания объектов 1С в тексте карточки на соответствие конфигурации.
    index = get_index()
    repo_root = index.kb_root.parent.parent
    index_file = repo_root / "_raw" / "unf30_xml" / "config_index.json"
    if not index_file.exists():
        return "Ошибка: config_index.json не найден. Запустите tools/parse_config_index.py"
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except Exception as e:
        return f"Ошибка чтения индекса: {e}"

    known_terms = {}
    for obj in config_data:
        tag = f"{obj['kind']}.{obj['name']}"
        if obj.get('name'):
            known_terms[obj['name'].lower()] = tag
        if obj.get('synonym'):
            known_terms[obj['synonym'].lower()] = tag

    matches = re.findall(r'`([^`]+)`|"([^"]+)"|«([^»]+)»', card_text)
    
    found_issues = []
    verified_terms = set()

    for match in matches:
        term = next((x for x in match if x), None)
        if not term:
            continue
        term = term.strip()
        term_lower = term.lower()
        
        if term_lower.startswith("unf30-") or term_lower.startswith("adr-") or term_lower.startswith("_meta") or term_lower.endswith(".md"):
            continue
            
        if term_lower in known_terms:
            verified_terms.add(f"✅ `{term}` -> {known_terms[term_lower]}")
        else:
            clean_term = re.sub(r'\s+', ' ', term_lower).strip()
            if clean_term in known_terms:
                verified_terms.add(f"✅ `{term}` -> {known_terms[clean_term]}")
            else:
                found_issues.append(f"❌ `{term}` -> НЕ НАЙДЕНО В КОНФИГУРАЦИИ")

    result = ["### Результат сверки с конфигурацией:\n"]
    if verified_terms:
        result.append("**Успешно подтверждено:**")
        result.extend(sorted(list(verified_terms)))
        result.append("")
    if found_issues:
        result.append("**ВНИМАНИЕ! Возможные галлюцинации:**")
        result.extend(sorted(list(set(found_issues))))
        result.append("\n*Если это название объекта 1С — исправь его, найдя точное имя через search_config. Если это просто текст — проигнорируй.*")
    else:
        result.append("Все проверенные объекты найдены в конфигурации.")
    return "\n".join(result)

# --- Запуск ---

def _build_transport_security(no_dns_protection: bool) -> TransportSecuritySettings:
    if no_dns_protection:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    raw_origins = os.environ.get("MCP_ALLOWED_ORIGINS", "https://chat.deepseek.com,chrome-extension://*")
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=origins,
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    parser.add_argument("--kb", default=None)
    parser.add_argument("--no-dns-protection", action="store_true")
    args = parser.parse_args()

    kb_root = _detect_kb_root(args.kb)
    os.environ["KB_PATH"] = str(kb_root)
    get_index()

    security = _build_transport_security(args.no_dns_protection)

    if args.transport == "stdio":
        print("[mcp_server] транспорт: stdio", file=sys.stderr)
        mcp.run()
    else:
        print(f"[mcp_server] транспорт: streamable-http, http://{args.host}:{args.port}/mcp", file=sys.stderr)
        print(f"[mcp_server] разрешённые Origin: {security.allowed_origins}", file=sys.stderr)
        mcp.run(transport="streamable-http", host=args.host, port=args.port, transport_security=security)

if __name__ == "__main__":
    main()
