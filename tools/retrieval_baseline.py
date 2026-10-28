#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Лексический baseline-ретривер для RAG по базе знаний УНФ 3.0.

Без эмбеддингов и LLM. Только:
  - точное вхождение синонима (подстрока для многословных)
  - пересечение токенов (title / synonyms / body)
  - IDF-взвешивание (редкие токены ценнее частых)

Метрика: hit@k — доля вопросов, где ожидаемая карточка попала в top-k.

Использование:
    py tools\\retrieval_baseline.py
    py tools\\retrieval_baseline.py --top-k 5
    py tools\\retrieval_baseline.py --show-all
    py tools\\retrieval_baseline.py --question "почему цена не подтянулась"
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_KB_DIR = Path("kb/unf30")
DEFAULT_QUESTIONS = Path("tools/test_questions.json")

# Минимальный стоп-лист. Расширять по мере надобности.
STOPWORDS = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне
было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него
до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы
тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому
этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда
можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много
разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда
конечно всю между это весь вся всё
""".split())

def normalize(text: str) -> str:
    """Lowercase + ё→е. Единая нормализация для вопроса и карточки."""
    return text.lower().replace("ё", "е")

def tokenize(text: str) -> list:
    """
    Грубая токенизация под русский без внешних зависимостей:
    - lower + ё→е
    - только буквы/цифры
    - отбрасываем слова короче 3 символов и стоп-слова
    - усечение до 5 символов (грубый стемминг: ловит падежи/окончания)
    """
    text = normalize(text)
    tokens = re.findall(r"[a-zа-я0-9]+", text)
    result = []
    for t in tokens:
        if len(t) < 3:
            continue
        if t in STOPWORDS:
            continue
        result.append(t[:5])
    return result

def parse_card(path: Path):
    """
    Парсит md-карточку: YAML-шапку (плоский key: value и key: [a, b, c])
    и тело. Возвращает dict или None, если шапки нет.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    front = text[4:end].strip()
    body = text[end + 4:].strip()

    meta = {}
    for line in front.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",")]
            meta[key] = [x for x in items if x]
        else:
            meta[key] = val.strip('"').strip("'")

    title = ""
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    return {
        "id": meta.get("id") or path.stem,
        "type": meta.get("type", ""),
        "level": meta.get("level", ""),
        "status": meta.get("status", "draft"),
        "title": title,
        "synonyms": meta.get("synonyms", []),
        "tags": meta.get("tags", []),
        "related": meta.get("related", []),
        "body": body,
        "path": str(path),
    }

def load_cards(kb_dir: Path):
    """Загружает все карточки из каталога, пропуская _index.md и прочие _*."""
    cards = []
    for p in sorted(kb_dir.glob("*.md")):
        if p.name.startswith("_"):
            continue
        c = parse_card(p)
        if c:
            cards.append(c)
    return cards

class CardIndex:
    """Предвычисленные токены карточки — чтобы не парсить на каждый вопрос."""
    __slots__ = ("card", "title_tokens", "synonym_tokens", "body_tokens", "syn_norm")

    def __init__(self, card):
        self.card = card
        self.title_tokens = set(tokenize(card["title"]))
        self.synonym_tokens = set()
        for s in card["synonyms"]:
            self.synonym_tokens.update(tokenize(s))
        self.body_tokens = set(tokenize(card["body"]))
        self.syn_norm = [normalize(s) for s in card["synonyms"] if s]

def compute_idf(indexes):
    """IDF как в TF-IDF: log((N+1)/(df+1)) + 1. Редкие токены получают больший вес."""
    df = Counter()
    for idx in indexes:
        for t in idx.title_tokens | idx.synonym_tokens | idx.body_tokens:
            df[t] += 1
    n = len(indexes)

    def idf(t):
        return math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0

    return idf

def score_card(idx, q_norm, q_tokens, idf):
    """
    Скоринг карточки под вопрос.
    Приоритет: синоним-токен > title-токен > body-токен.
    Плюс бонус за фразовое вхождение многословного синонима.
    """
    score = 0.0

    # Фразовое совпадение (для многословных синонимов типа "цена не подтянулась")
    for syn in idx.syn_norm:
        if len(syn) >= 6 and syn in q_norm:
            score += 8.0

    # Токены с IDF
    for t in q_tokens:
        w = idf(t)
        if t in idx.synonym_tokens:
            score += 4.0 * w
        elif t in idx.title_tokens:
            score += 2.0 * w
        elif t in idx.body_tokens:
            score += 0.5 * w

    # Малый бонус за verified — при равенстве выигрывает проверенная карточка
    if idx.card["status"] == "verified":
        score += 0.1

    return score

def retrieve(question, indexes, idf, top_k=3):
    q_norm = normalize(question)
    q_tokens = tokenize(question)
    scored = [(idx.card["id"], score_card(idx, q_norm, q_tokens, idf)) for idx in indexes]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]

def main():
    ap = argparse.ArgumentParser(description="Лексический baseline-ретривер УНФ 3.0")
    ap.add_argument("--kb-dir", default=str(DEFAULT_KB_DIR))
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--show-all", action="store_true", help="показать top-10 для каждого вопроса")
    ap.add_argument("--question", help="прогнать один вопрос из командной строки")
    args = ap.parse_args()

    kb_dir = Path(args.kb_dir)
    if not kb_dir.exists():
        print(f"ERROR: KB dir not found: {kb_dir}", file=sys.stderr)
        sys.exit(1)

    cards = load_cards(kb_dir)
    if not cards:
        print(f"ERROR: no cards found in {kb_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(cards)} cards from {kb_dir}\n")

    indexes = [CardIndex(c) for c in cards]
    idf = compute_idf(indexes)

    if args.question:
        questions = [{"question": args.question}]
    else:
        qfile = Path(args.questions)
        if not qfile.exists():
            print(f"WARN: questions file not found: {qfile}", file=sys.stderr)
            print('Pass --question "..." for ad-hoc test.', file=sys.stderr)
            sys.exit(2)
        questions = json.loads(qfile.read_text(encoding="utf-8"))

    hit = 0
    total = 0
    show = 10 if args.show_all else args.top_k

    for q in questions:
        question = q["question"]
        expected = q.get("expected")
        exp_list = [expected] if isinstance(expected, str) else (expected or [])
        top = retrieve(question, indexes, idf, top_k=show)

        if exp_list:
            ids = [tid for tid, _ in top[: args.top_k]]
            ok = any(e in ids for e in exp_list)
            total += 1
            if ok:
                hit += 1
            mark = "OK  " if ok else "MISS"
        else:
            mark = "????"

        print(f"[{mark}] {question}")
        if exp_list:
            print(f"        expected: {', '.join(exp_list)}")
        for rank, (tid, sc) in enumerate(top, 1):
            print(f"        {rank:2d}. {tid:38s} score={sc:6.2f}")
        print()

    if total:
        pct = 100.0 * hit / total
        print(f"=== hit@{args.top_k}: {hit}/{total} = {pct:.1f}% ===")

if __name__ == "__main__":
    main()
