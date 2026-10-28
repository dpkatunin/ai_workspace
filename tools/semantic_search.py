#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Семантический (векторный) поиск по базе знаний УНФ 3.0.
Использует модель E5 Large (multilingual) через fastembed.
"""
import sys
import json
import numpy as np
from pathlib import Path
from fastembed import TextEmbedding

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_KB_DIR = Path("kb/unf30")
DEFAULT_QUESTIONS = Path("tools/test_questions.json")

def parse_card(path):
    text = path.read_text(encoding="utf-8-sig") 
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    front = parts[1].strip()
    body = parts[2].strip()

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
        "status": meta.get("status", "draft"),
        "title": title,
        "synonyms": meta.get("synonyms", []),
        "body": body,
    }

def load_cards(kb_dir):
    cards = []
    for p in sorted(kb_dir.rglob("*.md")):
        if p.name.startswith("_"):
            continue
        c = parse_card(p)
        if c:
            cards.append(c)
    return cards

def main():
    kb_dir = Path(DEFAULT_KB_DIR)
    cards = load_cards(kb_dir)
    if not cards:
        print(f"Ошибка: карточки не найдены в {kb_dir}")
        return

    print(f"Загружено {len(cards)} карточек. Подготовка модели...")
    print("При первом запуске модель (~500 МБ) скачается в кеш.")
    
    try:
        # Используем модель e5-large, она точно поддерживается в fastembed
        model = TextEmbedding(model_name="intfloat/multilingual-e5-large")
    except Exception as e:
        print(f"Ошибка загрузки модели: {e}")
        print("\nДоступные мультиязычные модели в fastembed:")
        for m in TextEmbedding.list_supported_models():
            if "multi" in m["model"].lower() or "m3" in m["model"].lower():
                print(f" - {m['model']}")
        return

    # Подготавливаем текст карточек.
    # ВАЖНО: для E5 модель требует префикс "passage: " для документов
    card_texts = []
    for c in cards:
        text = f"passage: {c['title']}. Синонимы: {', '.join(c['synonyms'])}. {c['body']}"
        card_texts.append(text)
    
    print("Генерация эмбеддингов для базы (это займет 10-20 секунд)...")
    card_embeddings = np.array(list(model.embed(card_texts)))

    # Режим 1: проверка на тестовых вопросах
    if "--test" in sys.argv:
        qfile = Path(DEFAULT_QUESTIONS)
        if not qfile.exists():
            print(f"Файл вопросов не найден: {qfile}")
            return
            
        questions = json.loads(qfile.read_text(encoding="utf-8"))
        hit = 0
        total = 0
        
        for q in questions:
            question = q["question"]
            expected = q.get("expected")
            exp_list = [expected] if isinstance(expected, str) else (expected or [])
            
            # ВАЖНО: для E5 модель требует префикс "query: " для вопроса
            q_emb = np.array(list(model.embed([f"query: {question}"]))[0])
            
            # Считаем сходство (скалярное произведение нормализованных векторов)
            scores = card_embeddings.dot(q_emb)
            
            # Берём топ-3
            top_indices = np.argsort(scores)[::-1][:3]
            
            ids = [cards[i]["id"] for i in top_indices]
            ok = any(e in ids for e in exp_list) if exp_list else True
            
            if exp_list:
                total += 1
                if ok: hit += 1
                print(f"[{'OK  ' if ok else 'MISS'}] {question}")
                print(f"        expected: {', '.join(exp_list)}")
            else:
                print(f"[????] {question}")
                
            for rank, idx in enumerate(top_indices, 1):
                print(f"        {rank}. {cards[idx]['id']:38s} score={scores[idx]:.4f}")
            print()
            
        if total:
            print(f"=== Семантический hit@3: {hit}/{total} = {100*hit/total:.1f}% ===")

    # Режим 2: интерактивный поиск (или разовый вопрос)
    else:
        question = sys.argv[1] if len(sys.argv) > 1 else input("Введите вопрос: ")
        q_emb = np.array(list(model.embed([f"query: {question}"]))[0])
        scores = card_embeddings.dot(q_emb)
        top_indices = np.argsort(scores)[::-1][:3]
        
        print(f"\nЛучшие результаты по смыслу для: «{question}»")
        for rank, idx in enumerate(top_indices, 1):
            print(f"{rank}. {cards[idx]['id']:38s} score={scores[idx]:.4f}")

if __name__ == "__main__":
    main()
