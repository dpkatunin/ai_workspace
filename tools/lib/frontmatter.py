"""
Surgical operations on YAML frontmatter inside markdown cards.

Принципы:
- Никогда не переформатируем YAML через safe_dump целиком — это стирает
  комментарии и меняет порядок ключей. Только точечная вставка.
- Все операции возвращают новый текст; файл пишет вызывающий код.
"""
from __future__ import annotations

import re

import yaml

DELIM = "---"

def split(text: str) -> tuple[str, str]:
    """Разделить markdown на (frontmatter_text, body_text). Делимитеры в fm не входят."""
    text = text.lstrip("\ufeff")
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIM:
        raise ValueError(f"file does not start with '{DELIM}' (first line: {lines[0]!r})")
    for i in range(1, len(lines)):
        if lines[i].strip() == DELIM:
            fm = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            return fm, body
    raise ValueError("unclosed frontmatter (no closing '---')")

def parse(fm_text: str) -> dict:
    """Разобрать YAML-фронтматтер в dict. Пустой fm → {}."""
    return yaml.safe_load(fm_text) or {}

def render_list_block(key: str, values: list[str]) -> str:
    """
    Отрендерить пару:
        key:
          - v1
          - v2
    С минимальным, но корректным экранированием YAML.
    """
    out = [f"{key}:"]
    for v in values:
        s = str(v)
        needs_quotes = (
            not s
            or any(c in s for c in ':#\'"[]{}&*!|>%@`')
            or s.startswith((" ", "\t", "-"))
            or s.endswith((" ", "\t"))
        )
        if needs_quotes:
            escaped = '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
        else:
            escaped = s
        out.append(f"  - {escaped}")
    return "\n".join(out)

def insert_block_after_key(fm_text: str, after_key: str, new_block: str) -> str:
    """
    Вставить многострочный блок после блока ключа `after_key:`.
    Если ключ не найден — добавить в конец frontmatter.
    """
    lines = fm_text.split("\n")
    insert_at = len(lines)
    key_re = re.compile(rf"^{re.escape(after_key)}\s*:")
    for i, line in enumerate(lines):
        if key_re.match(line):
            insert_at = i + 1
            j = i + 1
            # Пропустить вложенные линии (с отступом)
            while j < len(lines) and (lines[j].startswith("  ") or lines[j].startswith("\t")):
                insert_at = j + 1
                j += 1
            break
    return "\n".join(lines[:insert_at] + new_block.split("\n") + lines[insert_at:])

def rebuild(text: str, new_fm: str) -> str:
    """Собрать обратно: ---\\n new_fm \\n---\\n body."""
    text = text.lstrip("\ufeff")
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIM:
        raise ValueError("file does not start with '---'")
    for i in range(1, len(lines)):
        if lines[i].strip() == DELIM:
            body = "\n".join(lines[i + 1:])
            return f"{DELIM}\n{new_fm}\n{DELIM}\n{body}"
    raise ValueError("unclosed frontmatter")
