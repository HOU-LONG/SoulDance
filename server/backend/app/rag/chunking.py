from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import Product


@dataclass(frozen=True)
class ChunkMeta:
    product_id: str
    sku_id: str | None
    category_id: str
    sub_category: str
    chunk_type: str
    source_type: str
    trust_level: str
    document_version: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_product(product: Product, version: int = 1) -> list[ChunkMeta]:
    chunks: list[ChunkMeta] = []

    def add(
        chunk_type: str,
        content: str,
        source_type: str = "official_detail",
        trust_level: str = "official",
        sku_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized = _normalize_space(content)
        if not normalized:
            return
        chunks.append(
            ChunkMeta(
                product_id=product.product_id,
                sku_id=sku_id,
                category_id=product.category,
                sub_category=product.sub_category,
                chunk_type=chunk_type,
                source_type=source_type,
                trust_level=trust_level,
                document_version=version,
                content=normalized,
                metadata=metadata or {},
            )
        )

    spec_parts = [
        f"商品名称: {product.title}",
        f"品牌: {product.brand}",
        f"类目: {product.category}",
        f"子类目: {product.sub_category}",
    ]
    if product.extracted_terms:
        spec_parts.append("属性词: " + " ".join(product.extracted_terms))
    if product.skus:
        sku_text = []
        for sku in product.skus:
            properties = " ".join(f"{key}:{value}" for key, value in sku.properties.items())
            sku_text.append(f"{sku.sku_id} {properties} 价格:{sku.price}")
        spec_parts.append("SKU: " + "；".join(sku_text))
    add("specification", "\n".join(spec_parts), metadata={"price": product.price})

    for index, sentence in enumerate(_split_sentences(product.marketing_description)):
        add(
            "feature",
            sentence,
            source_type="official_detail",
            trust_level="official",
            metadata={"sentence_index": index},
        )

    add(
        "marketing",
        product.marketing_description,
        source_type="marketing_copy",
        trust_level="marketing",
    )

    for index, text in enumerate(_split_long_text(product.chunk, max_chars=300)):
        add(
            "description",
            text,
            source_type="official_detail",
            trust_level="official",
            metadata={"part_index": index},
        )

    for index, faq in enumerate(product.faqs):
        question = str(faq.get("question") or faq.get("q") or "").strip()
        answer = str(faq.get("answer") or faq.get("a") or "").strip()
        add(
            "faq",
            f"Q: {question}\nA: {answer}",
            source_type="faq",
            trust_level="official",
            metadata={"faq_index": index},
        )

    for batch_index, batch in enumerate(_batched(product.reviews, size=3)):
        review_lines = []
        for review in batch:
            content = str(review.get("content") or review.get("text") or "").strip()
            rating = review.get("rating")
            if content and rating is not None:
                review_lines.append(f"{content} 评分:{rating}")
            elif content:
                review_lines.append(content)
        add(
            "review",
            "\n".join(review_lines),
            source_type="review_summary",
            trust_level="review_aggregate",
            metadata={"batch_index": batch_index, "review_count": len(batch)},
        )

    return chunks


def _split_sentences(text: str) -> list[str]:
    normalized = _normalize_space(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[。！？!?；;])\s*", normalized)
    return [part.strip() for part in parts if part.strip()]


def _split_long_text(text: str, max_chars: int = 300) -> list[str]:
    normalized = _normalize_space(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        boundary = max(
            normalized.rfind("。", start, end),
            normalized.rfind("！", start, end),
            normalized.rfind("？", start, end),
            normalized.rfind("；", start, end),
        )
        if boundary > start + max_chars // 2:
            end = boundary + 1
        chunks.append(normalized[start:end].strip())
        start = end
    return [chunk for chunk in chunks if chunk]


def _batched(items: list[dict[str, object]], size: int) -> list[list[dict[str, object]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
