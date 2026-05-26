from __future__ import annotations

from pathlib import Path

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

from .models import Product


class EmbeddingRetriever:
    def __init__(self, products: list[Product], model_dir: str | Path, device: str = "cuda:0", use_embedding: bool = True):
        self.products = products
        self.tokenized = [self._tokenize(product.chunk) for product in products]
        self.bm25 = BM25Okapi(self.tokenized)
        self.model = None
        self.embeddings = None
        self.use_embedding = use_embedding
        model_path = Path(model_dir)
        if use_embedding and model_path.exists():
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(str(model_path), device=device)
                self.embeddings = self.model.encode(
                    [product.chunk for product in products],
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
            except Exception:
                self.model = None
                self.embeddings = None

    def search(self, query: str, top_k: int = 20) -> list[tuple[Product, float]]:
        query_tokens = self._tokenize(query)
        bm25_scores = np.asarray(self.bm25.get_scores(query_tokens), dtype=float)
        bm25_scores = _normalize(bm25_scores)
        scores = bm25_scores
        if self.model is not None and self.embeddings is not None:
            query_vec = self.model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
            dense_scores = np.dot(self.embeddings, query_vec)
            dense_scores = _normalize(dense_scores)
            scores = 0.65 * dense_scores + 0.35 * bm25_scores
        order = np.argsort(scores)[::-1][:top_k]
        return [(self.products[int(i)], float(scores[int(i)])) for i in order]

    def _tokenize(self, text: str) -> list[str]:
        return [token.strip().lower() for token in jieba.lcut(text) if token.strip()]


class BM25OnlyRetriever(EmbeddingRetriever):
    def __init__(self, products: list[Product]):
        super().__init__(products, model_dir=".", use_embedding=False)


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    min_score = float(scores.min())
    max_score = float(scores.max())
    if max_score == min_score:
        return np.zeros_like(scores)
    return (scores - min_score) / (max_score - min_score)
