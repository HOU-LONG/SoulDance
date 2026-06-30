from __future__ import annotations

from pathlib import Path

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

from ..config import RetrievalConfig
from ..models import Product


class EmbeddingRetriever:
    """基础内存检索器：BM25 + 可选 dense，加权和融合。

    主要职责：
    - 启动时把所有商品的 chunk 文本编码为 embedding 矩阵（self.embeddings），供 HybridRetriever 复用。
    - 进程内简单查询入口（query → top_k），保留作为 AdaptiveRetriever 在 hybrid 不可用时的回退路径。
    - 融合权重从 RetrievalConfig 读，不再硬编码 0.65/0.35。
    """

    def __init__(
        self,
        products: list[Product],
        model_dir: str | Path,
        device: str = "cuda:0",
        use_embedding: bool = True,
        *,
        config: RetrievalConfig | None = None,
    ):
        self.products = products
        self.config = config or RetrievalConfig()
        self.tokenized = [self._tokenize(product.chunk) for product in products]
        self.bm25 = BM25Okapi(self.tokenized)
        self.model = None
        self.embeddings: np.ndarray | None = None
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
        if self.model is not None and self.embeddings is not None and self.config.fusion_strategy != "bm25_only":
            query_vec = self.model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
            dense_scores = np.dot(self.embeddings, query_vec)
            dense_scores = _normalize(dense_scores)
            if self.config.fusion_strategy == "dense_only":
                scores = dense_scores
            elif self.config.fusion_strategy == "rrf":
                # 内存路径下 RRF 退化为加权和的等价形式不直观，统一用加权和；
                # 真正想跑 RRF ablation 应该走 HybridRetriever 路径。
                scores = self.config.dense_weight * dense_scores + self.config.bm25_weight * bm25_scores
            else:  # weighted
                scores = self.config.dense_weight * dense_scores + self.config.bm25_weight * bm25_scores
        order = np.argsort(scores)[::-1][:top_k]
        return [(self.products[int(i)], float(scores[int(i)])) for i in order]

    def _tokenize(self, text: str) -> list[str]:
        # 预处理：在 CJK 字符和 ASCII/数字之间插入空格，修复"小米17Max"→"小米 17 Max"
        normalized = _normalize_cjk_ascii(text)
        return [token.strip().lower() for token in jieba.lcut(normalized) if token.strip()]

    def _tokenize_product(self, product: Product) -> list[str]:
        """对商品文本分词——标题/搜索文本中的空格已足够，不需要额外预处理。"""
        text = product.chunk
        return [token.strip().lower() for token in jieba.lcut(text) if token.strip()]


class BM25OnlyRetriever(EmbeddingRetriever):
    def __init__(self, products: list[Product], *, config: RetrievalConfig | None = None):
        super().__init__(products, model_dir=".", use_embedding=False, config=config)


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    min_score = float(scores.min())
    max_score = float(scores.max())
    if max_score == min_score:
        return np.zeros_like(scores)
    return (scores - min_score) / (max_score - min_score)


_CJK_ASCII_BOUNDARY = __import__('re').compile(r'([一-鿿㐀-䶿])([a-zA-Z0-9])|([a-zA-Z0-9])([一-鿿㐀-䶿])')
_DIGIT_ALPHA_BOUNDARY = __import__('re').compile(r'([0-9])([a-zA-Z])|([a-zA-Z])([0-9])')


def _normalize_cjk_ascii(text: str) -> str:
    """CJK↔ASCII + 数字↔字母 之间插入空格，修复"小米17Max"→"小米 17 Max"。"""
    text = _CJK_ASCII_BOUNDARY.sub(r'\1\3 \2\4', text)
    text = _DIGIT_ALPHA_BOUNDARY.sub(r'\1\3 \2\4', text)
    return text
