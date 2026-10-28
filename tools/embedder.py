#!/usr/bin/env python3
"""
Эмбеддинги для RAG-поиска по базе знаний 1С:УНФ 3.0.

Модель: intfloat/multilingual-e5-large (та же, что в tools/semantic_search.py —
чтобы результаты были сопоставимы).

Про префиксы: у семейства e5 тексты документов и запросы должны быть помечены
«passage: » и «query: » соответственно. Без этого качество заметно падает.

Кэш: векторы карточек считаются один раз и складываются в .cache/*.npz.
Ключ кэша — хэш модели и текстов, поэтому при правке любой карточки
пересчитываются все (34 карточки — несколько секунд).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-large"
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "

def default_cache_dir(kb_root: Path) -> Path:
    """Кэш кладём рядом с каталогом kb/, в ai_workspace/.cache."""
    return Path(kb_root).resolve().parent.parent / ".cache"

class Embedder:
    def __init__(
        self,
        cache_dir: Path,
        model_name: str = MODEL_NAME,
        batch_size: int = 16,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def _cache_key(self, texts: list[str]) -> str:
        digest = hashlib.sha256()
        digest.update(self.model_name.encode("utf-8"))
        for text in texts:
            digest.update(b"\x1e")
            digest.update(text.encode("utf-8"))
        return digest.hexdigest()[:16]

    def _embed(self, texts: list[str]) -> np.ndarray:
        model = self._ensure_model()
        vectors = np.asarray(list(model.embed(texts, batch_size=self.batch_size)), dtype=np.float32)
        # Косинусное сходство = скалярное произведение нормированных векторов.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        """Векторы карточек, с кэшем на диске."""
        key = self._cache_key(texts)
        cache_file = self.cache_dir / f"passages_e5_{key}.npz"
        if cache_file.exists():
            try:
                return np.load(cache_file)["vectors"]
            except Exception:
                pass  # битый кэш — просто пересчитаем

        vectors = self._embed([PASSAGE_PREFIX + t for t in texts])
        np.savez(cache_file, vectors=vectors)
        return vectors

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([QUERY_PREFIX + text])[0]
