from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import Product
from .chunking import canonical_chunk_type

_REVIEW_INTENT_PATTERN = re.compile(
    "|".join([
        "review",
        "feedback",
        "comment",
        "\\u8bc4\\u4ef7",
        "\\u8bc4\\u8bba",
        "\\u53e3\\u7891",
        "\\u5dee\\u8bc4",
        "\\u53cd\\u9988",
        "\\u4e70\\u5bb6",
        "\\u7528\\u6237",
    ]),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChunkSearchResult:
    product_id: str
    chunk_id: str
    sku_id: str | None
    category_id: str
    sub_category: str
    chunk_type: str
    source_type: str
    trust_level: str
    document_version: int
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def excerpt(self) -> str:
        return self.content[:160]


@dataclass(frozen=True)
class ProductRetrievalResult:
    product: Product
    score: float
    evidence_chunks: list[ChunkSearchResult] = field(default_factory=list)


def chunk_result_from_orm(chunk, score: float) -> ChunkSearchResult:
    return ChunkSearchResult(
        product_id=chunk.product_id,
        chunk_id=chunk.chunk_id,
        sku_id=chunk.sku_id,
        category_id=chunk.category_id,
        sub_category=chunk.sub_category,
        chunk_type=canonical_chunk_type(chunk.chunk_type),
        source_type=chunk.source_type,
        trust_level=chunk.trust_level,
        document_version=chunk.document_version,
        content=chunk.content or "",
        score=float(score),
        metadata=dict(chunk.metadata_json or {}),
    )


def chunk_relevance_weight(
    query: str,
    chunk_type: str,
    source_type: str,
    trust_level: str,
) -> float:
    canonical_type = canonical_chunk_type(chunk_type)
    review_intent = bool(_REVIEW_INTENT_PATTERN.search(query or ""))
    if canonical_type == "review_summary":
        return 1.15 if review_intent else 0.65
    if source_type == "marketing_copy" or trust_level == "marketing":
        return 0.55
    weights = {
        "specification": 1.25,
        "sku": 1.2,
        "official_description": 1.05,
        "faq": 1.0,
    }
    return weights.get(canonical_type, 0.8)


def format_chunk_evidence(chunk: ChunkSearchResult) -> str:
    text = chunk.excerpt.strip()
    if not text:
        return ""
    return f"[{chunk.chunk_type}/{chunk.source_type}/v{chunk.document_version}] {text}"
