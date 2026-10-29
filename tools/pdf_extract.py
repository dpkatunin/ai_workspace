#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_extract.py — извлечение текста из PDF в Markdown с отсевом шума.

Зачем две стадии очистки:
  1. Сначала убираем boilerplate (виджеты, навигацию, футеры) — паттерны
     шума. Без этого «пустые» страницы-скриншоты с чат-виджетом проходят
     порог и попадают в чанки как будто это контент.
  2. Потом считаем «осмысленные» символы (буквы, цифры) и отсеиваем
     страницы ниже порога. Такие страницы — скриншоты, где текстового
     слоя нет вообще.

Использование (из корня репозитория, в активированном .venv):

    py tools\\pdf_extract.py "_source/01_unf/03_external/article.pdf"
    py tools\\pdf_extract.py article.pdf --min-chars 100
    py tools\\pdf_extract.py article.pdf --no-strip        # отладка
    py tools\\pdf_extract.py article.pdf --strip-file my_noise.txt

Файл паттернов шума (--strip-file): по строке на паттерн, name<TAB>regex.
Пустые строки и строки с # игнорируются.

Зависимость: PyMuPDF (fitz).

    py -m pip install -r tools\\requirements-pdf.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---------- Шум (boilerplate), удаляется ДО подсчёта символов ----------

DEFAULT_STRIP_PATTERNS: list[tuple[str, str]] = [
    (
        "chat_widget_roman",
        # Чат-виджет «Роман Месяткин», повторяется на каждой странице
        # PDF от 1С:Идея. Многострочный блок: имя, приветствие, приглашение
        # написать. \s[\s\S] — матчит любые символы, включая переносы строк.
        r"Роман\s+Месяткин[\s\S]{0,300}?вопросы\.",
    ),
]

def load_strip_patterns(path: Path | None) -> list[tuple[str, str]]:
    """Собрать паттерны: дефолтные + пользовательские из файла."""
    patterns = list(DEFAULT_STRIP_PATTERNS)
    if path is None:
        return patterns
    if not path.exists():
        print(f"WARN: файл паттернов не найден: {path}", file=sys.stderr)
        return patterns

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
            print(
                f"WARN: {path.name}:{line_no}: нет таба между name и pattern",
                file=sys.stderr,
            )
            continue
        name, _, pattern = line.partition("\t")
        patterns.append((name.strip(), pattern.strip()))
    return patterns

def apply_strip_patterns(
    text: str, patterns: list[tuple[str, str]]
) -> tuple[str, list[str]]:
    """Прогнать текст через паттерны. Вернуть (очищенный_текст, [имена сработавших])."""
    fired: list[str] = []
    for name, pattern in patterns:
        try:
            new_text = re.sub(pattern, "", text, flags=re.MULTILINE)
        except re.error as exc:
            print(f"WARN: паттерн {name!r} не применился: {exc}", file=sys.stderr)
            continue
        if new_text != text:
            fired.append(name)
            text = new_text
    return text, fired

# ---------- Извлечение ----------

def extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Вернуть [(номер страницы, текст), ...]. Номер — с 1."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print(
            "ERROR: не установлен PyMuPDF. Установите:\n"
            "  py -m pip install -r tools\\requirements-pdf.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    pages: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append((i, text))
    return pages

def count_chars(text: str) -> int:
    """Считать только «осмысленные» символы: буквы и цифры."""
    return len(re.findall(r"[A-Za-zА-Яа-я0-9]", text))

# ---------- Рендер ----------

def render_markdown(
    pdf_path: Path,
    pages: list[tuple[int, str]],
    min_chars: int,
    patterns: list[tuple[str, str]],
) -> tuple[str, dict]:
    """Вернуть (markdown, stats)."""
    kept: list[tuple[int, str]] = []
    dropped_empty: list[int] = []
    dropped_noise_only: list[int] = []
    fired_by_page: dict[int, list[str]] = {}

    for num, original in pages:
        cleaned, fired = apply_strip_patterns(original, patterns)
        if fired:
            fired_by_page[num] = fired

        chars_orig = count_chars(original)
        chars_clean = count_chars(cleaned)

        if chars_clean < min_chars:
            # Если до очистки страница была непустая, а после — пустая,
            # это страница «только со шумом» (виджет на скриншоте).
            if chars_orig >= min_chars:
                dropped_noise_only.append(num)
            else:
                dropped_empty.append(num)
            continue

        kept.append((num, cleaned))

    total_orig = sum(count_chars(t) for _, t in pages)
    total_clean = sum(count_chars(t) for _, t in kept)

    out: list[str] = []
    out.append(f"# {pdf_path.stem}\n")
    out.append(f"<!-- source: {pdf_path.as_posix()} -->\n")
    out.append(f"<!-- pages_total: {len(pages)}, min_chars: {min_chars} -->\n")
    if dropped_empty:
        out.append(
            f"<!-- dropped_empty: {', '.join(str(p) for p in dropped_empty)} -->\n"
        )
    if dropped_noise_only:
        out.append(
            f"<!-- dropped_noise_only: {', '.join(str(p) for p in dropped_noise_only)} -->\n"
        )
    if fired_by_page:
        summary = ", ".join(
            f"p{p}:{','.join(names)}" for p, names in sorted(fired_by_page.items())
        )
        out.append(f"<!-- noise_fired: {summary} -->\n")

    for num, text in kept:
        out.append(f"\n<!-- page {num} -->\n")
        out.append(text.rstrip())
        out.append("\n")

    stats = {
        "pages": len(pages),
        "kept": len(kept),
        "dropped_empty": dropped_empty,
        "dropped_noise_only": dropped_noise_only,
        "fired_by_page": fired_by_page,
        "chars_original": total_orig,
        "chars_cleaned": total_clean,
    }
    return "".join(out), stats

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Извлечь текст из PDF в Markdown, отсеять шум и пустые страницы."
    )
    ap.add_argument("pdf", type=Path, help="путь к PDF-файлу")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="куда сохранить .md (по умолчанию — рядом с PDF, с тем же именем)",
    )
    ap.add_argument(
        "--min-chars",
        type=int,
        default=50,
        help="порог «осмысленных» символов ПОСЛЕ очистки от шума (по умолчанию 50)",
    )
    ap.add_argument(
        "--strip-file",
        type=Path,
        default=None,
        help="файл с доп. паттернами шума: name<TAB>regex, по строке",
    )
    ap.add_argument(
        "--no-strip",
        action="store_true",
        help="не применять паттерны шума (для отладки)",
    )
    args = ap.parse_args()

    pdf_path = args.pdf
    if not pdf_path.exists():
        print(f"ERROR: файл не найден: {pdf_path}", file=sys.stderr)
        return 1
    if pdf_path.suffix.lower() != ".pdf":
        print(f"ERROR: ожидался .pdf, получен {pdf_path.suffix}", file=sys.stderr)
        return 1

    pages = extract_pages(pdf_path)
    if not pages:
        print("ERROR: PDF не содержит страниц", file=sys.stderr)
        return 1

    patterns = [] if args.no_strip else load_strip_patterns(args.strip_file)
    markdown, stats = render_markdown(pdf_path, pages, args.min_chars, patterns)

    out_path = args.out or pdf_path.with_suffix(".md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")

    print(f"PDF: {pdf_path.name}")
    print(f"  страниц:              {stats['pages']}")
    print(f"  оставлено:            {stats['kept']}")
    print(
        f"  отброшено пустых:     {len(stats['dropped_empty'])}"
        + (f" — {stats['dropped_empty']}" if stats["dropped_empty"] else "")
    )
    print(
        f"  отброшено шум-только: {len(stats['dropped_noise_only'])}"
        + (f" — {stats['dropped_noise_only']}" if stats["dropped_noise_only"] else "")
    )
    if stats["fired_by_page"]:
        print("  шум сработал на страницах:")
        for page, names in sorted(stats["fired_by_page"].items()):
            print(f"    p{page}: {', '.join(names)}")
    print(
        f"  символов: было {stats['chars_original']}, стало {stats['chars_cleaned']}"
    )
    print(f"  → сохранено:          {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
