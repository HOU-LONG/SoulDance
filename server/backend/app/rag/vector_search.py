"""Dense 向量检索。

设计要点：
- dense index 在进程启动时一次性构建（product → embedding 矩阵），所有查询共享同一份。
- ProductChunk.embedding 字段保留作为持久化缓存：启动时若 DB 中嵌入与当前商品文本 hash 匹配，
  可直接 reuse，避免重启时重新调用嵌入模型。
- 查询走 numpy 矩阵点积（O(N · d)，100 商品下不到 1ms）。
- 硬约束（category / sub_category）在 product 级别过滤；BM25 走 chunk 级长尾召回不在这里。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from ..db.models import ProductChunk
from ..models import HardConstraints, Product


@dataclass
class DenseIndex:
    """Product 级 dense 索引。

    Attributes:
        product_ids: 与 matrix 行对应的 product_id 列表。
        matrix: shape (N, d) 的归一化向量矩阵。
        product_meta: product_id → (category, sub_category)，用于约束过滤。
    """

    product_ids: list[str]
    matrix: np.ndarray
    product_meta: dict[str, tuple[str, str]]

    @property
    def is_empty(self) -> bool:
        return self.matrix.size == 0

    def search(
        self,
        query_vector: np.ndarray,
        constraints: HardConstraints,
        top_k: int = 30,
    ) -> list[tuple[str, float]]:
        if self.is_empty:
            return []
        query_vec = np.asarray(query_vector, dtype=float)
        if query_vec.shape[-1] != self.matrix.shape[1]:
            return []
        scores = self.matrix @ query_vec
        normalized = _normalize(scores)
        allowed = self._allowed_indices(constraints)
        if not allowed:
            return []
        ranked = [(self.product_ids[i], float(normalized[i])) for i in allowed]
        return sorted(ranked, key=lambda item: item[1], reverse=True)[:top_k]

    def _allowed_indices(self, constraints: HardConstraints) -> list[int]:
        allowed: list[int] = []
        for idx, product_id in enumerate(self.product_ids):
            category, sub_category = self.product_meta.get(product_id, ("", ""))
            if constraints.category and category != constraints.category:
                continue
            if constraints.sub_category and sub_category != constraints.sub_category:
                continue
            allowed.append(idx)
        return allowed


def build_dense_index(
    products: list[Product],
    embeddings: np.ndarray | None,
) -> DenseIndex:
    """从已编码的 embedding 矩阵构造 dense index。

    embeddings 行序与 products 一致；如果为 None 或维度不匹配，返回空 index。
    """
    if embeddings is None or embeddings.size == 0 or len(products) == 0:
        return DenseIndex(product_ids=[], matrix=np.zeros((0, 0)), product_meta={})
    if embeddings.shape[0] != len(products):
        return DenseIndex(product_ids=[], matrix=np.zeros((0, 0)), product_meta={})
    product_ids = [product.product_id for product in products]
    meta = {
        product.product_id: (product.category or "", product.sub_category or "")
        for product in products
    }
    return DenseIndex(
        product_ids=product_ids,
        matrix=np.asarray(embeddings, dtype=float),
        product_meta=meta,
    )


def load_dense_index_from_db(
    session: Session,
    products: list[Product],
    expected_dim: int,
) -> DenseIndex | None:
    """从 ProductChunk.embedding 持久化缓存重建 dense index。

    仅当所有 product 都有可用嵌入、维度匹配时返回 index；否则返回 None
    让调用方走重新编码路径。

    持久化策略：每个 product 取其 chunk_type='description' 且最新版本的 chunk
    作为代表性嵌入（与启动时 encode 用的文本一致）。
    """
    if not products or expected_dim <= 0:
        return None
    chunk_rows = (
        session.query(
            ProductChunk.product_id,
            ProductChunk.embedding,
            ProductChunk.chunk_type,
            ProductChunk.document_version,
        )
        .filter(
            ProductChunk.is_active.is_(True),
            ProductChunk.embedding.is_not(None),
        )
        .all()
    )
    best: dict[str, list[float]] = {}
    best_version: dict[str, int] = {}
    for product_id, embedding, chunk_type, version in chunk_rows:
        if not isinstance(embedding, list) or len(embedding) != expected_dim:
            continue
        if chunk_type and chunk_type != "description":
            continue
        if version >= best_version.get(product_id, -1):
            best[product_id] = embedding
            best_version[product_id] = version
    if len(best) != len(products):
        return None
    matrix = np.asarray([best[product.product_id] for product in products], dtype=float)
    return build_dense_index(products, matrix)


def vector_search_chunks(
    session: Session,
    query_vector: np.ndarray,
    constraints: HardConstraints,
    top_k: int = 30,
    *,
    dense_index: DenseIndex | None = None,
) -> list[tuple[str, float]]:
    """Dense 检索入口。

    优先走传入的 dense_index（推荐路径，调用方在启动时构建一次）；
    若未提供 index，回退到从 SQLite ProductChunk.embedding 现场构造一次
    index（旧路径，保留是为了让仍直接调用此函数的测试不破坏）。
    """
    if dense_index is not None:
        return dense_index.search(query_vector, constraints, top_k=top_k)
    rows = _load_active_embeddings(session, constraints)
    if not rows:
        return []
    query_vec = np.asarray(query_vector, dtype=float)
    raw_scores: list[tuple[str, float]] = []
    for product_id, embedding in rows:
        vector = np.asarray(embedding, dtype=float)
        if vector.shape != query_vec.shape:
            continue
        raw_scores.append((product_id, float(np.dot(vector, query_vec))))
    if not raw_scores:
        return []
    scores = _normalize(np.asarray([score for _, score in raw_scores], dtype=float))
    best_by_product: dict[str, float] = {}
    for (product_id, _), score in zip(raw_scores, scores):
        best_by_product[product_id] = max(best_by_product.get(product_id, 0.0), float(score))
    return sorted(best_by_product.items(), key=lambda item: item[1], reverse=True)[:top_k]


def _load_active_embeddings(
    session: Session,
    constraints: HardConstraints,
) -> list[tuple[str, list[float]]]:
    query = session.query(ProductChunk.product_id, ProductChunk.embedding).filter(
        ProductChunk.is_active.is_(True),
        ProductChunk.embedding.is_not(None),
    )
    if constraints.category:
        query = query.filter(ProductChunk.category_id == constraints.category)
    if constraints.sub_category:
        query = query.filter(ProductChunk.sub_category == constraints.sub_category)
    return [
        (product_id, embedding)
        for product_id, embedding in query.all()
        if isinstance(embedding, list) and embedding
    ]


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    min_score = float(scores.min())
    max_score = float(scores.max())
    if max_score == min_score:
        return np.zeros_like(scores)
    return (scores - min_score) / (max_score - min_score)
