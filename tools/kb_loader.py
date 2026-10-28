#!/usr/bin/env python3
"""
Загрузка карточек базы знаний 1С:УНФ 3.0 из kb/unf30.

Карточка — Markdown-файл с YAML-фронтматтером:

    ---
    id: unf30.warehouse.orderny-sklad
    title: Ордерный склад
    type: object
    level: kb
    status: verified
    tags: [склад, ордерный]
    synonyms: [ордерная схема, ордерный склад]
    ---
    ## Что это
    ...

Модуль не зависит от MCP и fastembed — только stdlib + pyyaml.
Используется mcp_server.py; при желании — любым другим инструментом.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # фронтматтер можно разобрать и без PyYAML
    yaml = None  # type: ignore[assignment]

_FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)\Z", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

@dataclass
class Card:
    """Одна карточка базы знаний."""

    id: str
    title: str
    path: str          # путь относительно корня репозитория, напр. kb/unf30/objects/x.md
    body: str          # тело карточки без фронтматтера
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return str(self.meta.get("type") or "")

    @property
    def status(self) -> str:
        return str(self.meta.get("status") or "")

    @property
    def level(self) -> str:
        return str(self.meta.get("level") or "")

    def embedding_text(self) -> str:
        """Текст, который уходит в эмбеддинг: заголовок + синонимы + теги + тело.

        Синонимы важны: пользователь спрашивает «ордерная схема», а в карточке
        написано «ордерный склад» — без синонимов такой запрос промахнётся.
        """
        parts: list[str] = [self.title]

        synonyms = self.meta.get("synonyms")
        if synonyms:
            if isinstance(synonyms, (list, tuple)):
                parts.append("Синонимы: " + ", ".join(str(s) for s in synonyms))
            else:
                parts.append(f"Синонимы: {synonyms}")

        tags = self.meta.get("tags")
        if tags:
            if isinstance(tags, (list, tuple)):
                parts.append("Теги: " + ", ".join(str(t) for t in tags))
            else:
                parts.append(f"Теги: {tags}")

        parts.append(self.body)
        return "\n\n".join(p for p in parts if p and p.strip())

def _fallback_parse(header: str) -> dict[str, Any]:
    """Разбор простого YAML без PyYAML (key: value, key: [a, b])."""
    meta: dict[str, Any] = {}
    for line in header.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key, raw = key.strip(), raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            meta[key] = [x.strip().strip("'\"") for x in raw[1:-1].split(",") if x.strip()]
        else:
            meta[key] = raw.strip("'\"")
    return meta

def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw

    header, body = match.group(1), match.group(2)
    meta: dict[str, Any]
    if yaml is None:
        meta = _fallback_parse(header)
    else:
        try:
            loaded = yaml.safe_load(header)
            meta = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError:
            meta = _fallback_parse(header)

    return meta, body.lstrip("\n")

def _guess_title(meta: dict[str, Any], body: str, fallback: str) -> str:
    title = meta.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    match = _H1_RE.search(body)
    if match:
        return match.group(1).strip()
    return fallback

def load_cards(kb_root: Path) -> list[Card]:
    """Прочитать все *.md из каталога карточек (рекурсивно).

    Служебные файлы (начинаются с «_») пропускаются.
    """
    kb_root = Path(kb_root).resolve()
    if not kb_root.is_dir():
        raise FileNotFoundError(f"Каталог карточек не найден: {kb_root}")

    repo_root = kb_root.parent.parent  # kb/unf30 -> корень репозитория (ai_workspace)
    cards: list[Card] = []
    seen_ids: set[str] = set()

    for path in sorted(kb_root.rglob("*.md")):
        if path.name.startswith("_"):
            continue

        raw = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(raw)

        rel = path.relative_to(repo_root).as_posix()
        card_id = str(meta.get("id") or path.stem)
        if card_id in seen_ids:          # страховка от дублей id
            card_id = f"{card_id}@{rel}"
        seen_ids.add(card_id)

        cards.append(
            Card(
                id=card_id,
                title=_guess_title(meta, body, path.stem),
                path=rel,
                body=body,
                meta=meta,
            )
        )

    if not cards:
        raise RuntimeError(f"В {kb_root} не найдено ни одной карточки (*.md)")

    return cards

if __name__ == "__main__":  # быстрая проверка: py tools/kb_loader.py <путь к kb/unf30>
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "kb" / "unf30"
    loaded = load_cards(root)
    print(f"Карточек загружено: {len(loaded)}")
    for c in loaded:
        print(f"  {c.id:40s} {c.type:10s} {c.status:9s} {c.path}")
