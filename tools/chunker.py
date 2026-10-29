#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chunker.py — разбиение извлечённого текста (.md) на смысловые чанки.

v2: добавлены склейка мелких чанков и фильтр мусора.
  - Склейка: если чанк меньше --merge-min слов, он приклеивается к соседу
    (сверху или снизу — к тому, что ближе по смыслу: если у соседа тот же
    page_range, к нему; иначе к следующему непустому).
  - Фильтр мусора: вырезаются строки-обрывки (< 3 слов без знаков препинания),
    маркеры скриншотов ("! ! !"), навигационные блоки по паттернам.

Использование:

    py tools\\chunker.py "_source/01_unf/03_external/article.md"
    py tools\\chunker.py article.md --target-words 400 --max-words 700
    py tools\\chunker.py article.md --out chunks/ --also-md
    py tools\\chunker.py article.md --no-merge       # не склеивать мелкие
    py tools\\chunker.py article.md --no-clean       # не фильтровать мусор

Формат чанка (JSON):

    {
      "id": "article-chunk-001",
      "source": "_source/01_unf/03_external/article.md",
      "source_pdf": "article.pdf",
      "page_range": [1, 2],
      "text": "...",
      "words": 450,
      "chars": 3000,
      "tokens_estimate": 585
    }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---------- Модель чанка ----------

@dataclass
class Chunk:
    id: str
    source: str
    source_pdf: str | None
    page_range: list[int]
    text: str
    words: int
    chars: int
    tokens_estimate: int

# ---------- Парсинг входа ----------

_PAGE_RE = re.compile(r"<!--\s*page\s+(\d+)\s*-->")
_SOURCE_RE = re.compile(r"<!--\s*source:\s*(.+?)\s*-->")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9]+")

# ---------- Фильтр мусора ----------

# Строки-обрывки, которые не несут смысла. Сюда не попадают строки
# с ":" и "=" (это могут быть реквизиты), а также заголовки.
_GARBAGE_LINE_RE = re.compile(
    r"^[\s!?.,;:…—–-]{0,5}$"       # только мусорные символы
    r"|^!(\s*!)*\s*$"               # "! ! !"
    r"|^[.\-_=*]{3,}$"              # разделители
)

# Навигационные блоки (типовые для сайтов): строка за строкой названия разделов.
# Если блок из ≥ 3 подряд идущих коротких строк без глаголов и точек — режем.
_NAV_HEADER_LINE_RE = re.compile(
    r"^(ГЛАВНАЯ|СТАТЬИ|КОНСУЛЬТАЦИЯ|КОНТАКТЫ|КАРЬЕРА|"
    r"О\s+КОМПАНИИ|НАШИ\s+УСЛУГИ|ЭТАПЫ\s+РАБОТЫ|"
    r"ПРИМЕРЫ\s+АВТОМАТИЗАЦИИ|ЗАКАЗАТЬ\s+ЗВОНОК|"
    r"1С[\s-]ИДЕЯ|ПРИСОЕДИНЯЙТЕСЬ|НАВЕРХ)$",
    re.IGNORECASE,
)

def clean_text(text: str) -> str:
    """Убрать мусорные строки и навигационные блоки. Вернуть текст."""
    lines = text.split("\n")
    out: list[str] = []
    nav_buffer: list[str] = []

    def flush_nav():
        # Если накопили ≥ 3 навигационных строки — выкидываем
        nonlocal nav_buffer
        if len(nav_buffer) >= 3:
            nav_buffer = []
        else:
            out.extend(nav_buffer)
            nav_buffer = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_nav()
            out.append("")
            continue
        if _GARBAGE_LINE_RE.match(stripped):
            continue
        if _NAV_HEADER_LINE_RE.match(stripped):
            nav_buffer.append(line)
            continue
        flush_nav()
        out.append(line)
    flush_nav()

    # Схлопнуть больше двух пустых строк
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return result.strip()

# ---------- Извлечение из .md ----------

def read_input(path: Path) -> str:
    if not path.exists():
        print(f"ERROR: файл не найден: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")

def extract_meta(text: str) -> tuple[str | None, str | None]:
    source_pdf = None
    m = _SOURCE_RE.search(text)
    if m:
        source_pdf = Path(m.group(1)).name
    title = None
    m = _H1_RE.search(text)
    if m:
        title = m.group(1).strip()
    return source_pdf, title

def split_by_pages(text: str) -> list[tuple[int, str]]:
    parts = _PAGE_RE.split(text)
    result: list[tuple[int, str]] = []
    i = 1
    while i + 1 < len(parts):
        num = int(parts[i])
        body = parts[i + 1].strip()
        if body:
            result.append((num, body))
        i += 2
    return result

def split_by_headers(text: str) -> list[tuple[str, str]]:
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_header = ""
    current_body: list[str] = []
    for line in lines:
        m = _H2_RE.match(line)
        if m:
            if current_header or current_body:
                sections.append((current_header, current_body))
            current_header = m.group(1).strip()
            current_body = []
        else:
            current_body.append(line)
    if current_header or current_body:
        sections.append((current_header, current_body))
    result = []
    for header, body in sections:
        body_text = "\n".join(body).strip()
        if body_text or header:
            result.append((header, body_text))
    return result

def split_by_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

# ---------- Метрики ----------

def count_words(text: str) -> int:
    return len(_TOKEN_RE.findall(text))

def estimate_tokens(words: int) -> int:
    return int(words * 1.3)

def split_oversized(text: str, max_words: int) -> list[str]:
    if count_words(text) <= max_words:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current: list[str] = []
    current_words = 0
    for sent in sentences:
        sent_words = count_words(sent)
        if current_words + sent_words > max_words and current:
            pieces.append(" ".join(current))
            current = [sent]
            current_words = sent_words
        else:
            current.append(sent)
            current_words += sent_words
    if current:
        pieces.append(" ".join(current))
    return pieces

def group_paragraphs(
    paragraphs: list[str],
    target_words: int,
    max_words: int,
) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for para in paragraphs:
        for part in split_oversized(para, max_words):
            part_words = count_words(part)
            if current_words + part_words > max_words and current:
                chunks.append("\n\n".join(current))
                current = [part]
                current_words = part_words
            elif current_words >= target_words:
                chunks.append("\n\n".join(current))
                current = [part]
                current_words = part_words
            else:
                current.append(part)
                current_words += part_words
    if current:
        chunks.append("\n\n".join(current))
    return chunks

# ---------- Склейка мелких чанков ----------

def merge_small(
    chunks: list[tuple[str, list[int]]],
    merge_min: int,
    max_words: int,
) -> list[tuple[str, list[int]]]:
    """
    Склеить чанки, в которых меньше merge_min слов, с соседями.

    Логика: если чанк меньше порога, приклеиваем его к следующему
    (или, если следующего нет, к предыдущему). Склеенный чанк
    не должен превысить max_words — иначе оставляем как есть.
    """
    if not chunks:
        return []

    result: list[tuple[str, list[int]]] = []
    pending_text: list[str] = []
    pending_pages: list[int] = []

    for text, pages in chunks:
        words = count_words(text)
        pending_text.append(text)
        for p in pages:
            if p not in pending_pages:
                pending_pages.append(p)
        pending_words = sum(count_words(t) for t in pending_text)

        if pending_words >= merge_min:
            result.append(("\n\n".join(pending_text), pending_pages))
            pending_text = []
            pending_pages = []

    # Остаток приклеиваем к последнему
    if pending_text:
        if result:
            last_text, last_pages = result[-1]
            merged = last_text + "\n\n" + "\n\n".join(pending_text)
            if count_words(merged) <= max_words:
                for p in pending_pages:
                    if p not in last_pages:
                        last_pages.append(p)
                result[-1] = (merged, last_pages)
            else:
                result.append(("\n\n".join(pending_text), pending_pages))
        else:
            result.append(("\n\n".join(pending_text), pending_pages))

    return result

# ---------- Основной проход ----------

def build_chunks(
    text: str,
    source_path: Path,
    target_words: int,
    max_words: int,
    min_words: int,
    merge_min: int,
    clean: bool,
    merge: bool,
) -> list[Chunk]:
    source_pdf, title = extract_meta(text)
    source_str = source_path.as_posix()
    base_id = source_path.stem

    pages = split_by_pages(text)
    raw: list[tuple[str, list[int]]] = []

    if pages:
        for page_num, page_text in pages:
            body = clean_text(page_text) if clean else page_text
            if not body.strip():
                continue
            paragraphs = split_by_paragraphs(body)
            for chunk_text in group_paragraphs(paragraphs, target_words, max_words):
                raw.append((chunk_text, [page_num]))
    else:
        sections = split_by_headers(text)
        for header, body in sections:
            body_clean = clean_text(body) if clean else body
            paragraphs = split_by_paragraphs(body_clean)
            if header:
                paragraphs = [header] + paragraphs
            for chunk_text in group_paragraphs(paragraphs, target_words, max_words):
                raw.append((chunk_text, []))

    # Склейка мелких чанков
    if merge:
        raw = merge_small(raw, merge_min=merge_min, max_words=max_words)

    # Финальная сборка
    result: list[Chunk] = []
    skipped = 0
    for chunk_text, page_list in raw:
        w = count_words(chunk_text)
        if w < min_words:
            skipped += 1
            continue
        result.append(
            Chunk(
                id=f"{base_id}-chunk-{len(result) + 1:03d}",
                source=source_str,
                source_pdf=source_pdf,
                page_range=sorted(set(page_list)),
                text=chunk_text,
                words=w,
                chars=len(chunk_text),
                tokens_estimate=estimate_tokens(w),
            )
        )
    if skipped:
        print(f"  (пропущено коротких чанков после склейки: {skipped})", file=sys.stderr)
    return result

# ---------- Рендер в Markdown ----------

def render_markdown(chunks: list[Chunk], title: str | None) -> str:
    out: list[str] = []
    out.append(f"# Чанки: {title or 'без названия'}\n")
    out.append(f"<!-- chunks_total: {len(chunks)} -->\n")
    for c in chunks:
        pages = f"стр. {c.page_range}" if c.page_range else "—"
        out.append(f"\n## {c.id}\n")
        out.append(
            f"<!-- pages: {pages}, words: {c.words}, ~tokens: {c.tokens_estimate} -->\n"
        )
        out.append(c.text)
        out.append("\n")
    return "".join(out)

# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="Разбить .md на смысловые чанки.")
    ap.add_argument("input", type=Path, help="входной .md-файл")
    ap.add_argument("--out", type=Path, default=None,
                    help="куда сохранить .json (по умолчанию рядом, .chunks.json)")
    ap.add_argument("--target-words", type=int, default=500)
    ap.add_argument("--max-words", type=int, default=800)
    ap.add_argument("--min-words", type=int, default=80)
    ap.add_argument("--merge-min", type=int, default=150,
                    help="чанки короче склеивать с соседями (по умолчанию 150)")
    ap.add_argument("--no-merge", action="store_true",
                    help="не склеивать мелкие чанки")
    ap.add_argument("--no-clean", action="store_true",
                    help="не фильтровать мусор (навигация, '! ! !')")
    ap.add_argument("--also-md", action="store_true")
    args = ap.parse_args()

    text = read_input(args.input)
    _, title = extract_meta(text)

    chunks = build_chunks(
        text,
        args.input,
        target_words=args.target_words,
        max_words=args.max_words,
        min_words=args.min_words,
        merge_min=args.merge_min,
        clean=not args.no_clean,
        merge=not args.no_merge,
    )

    out_json = args.out or args.input.with_suffix(".chunks.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps([asdict(c) for c in chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Вход:  {args.input}")
    print(f"Чанков: {len(chunks)}")
    if chunks:
        wc = [c.words for c in chunks]
        print(f"  слов: min={min(wc)}, среднее={sum(wc) // len(wc)}, max={max(wc)}")
        print(f"  ~токенов всего: {sum(c.tokens_estimate for c in chunks)}")
    print(f"  → сохранено: {out_json}")

    if args.also_md:
        out_md = out_json.with_suffix(".md")
        out_md.write_text(render_markdown(chunks, title), encoding="utf-8")
        print(f"  → сохранено: {out_md}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
