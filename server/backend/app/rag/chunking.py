from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import Product


CHUNK_TYPE_ALIASES = {
    "description": "official_description",
    "feature": "official_description",
    "marketing": "official_description",
    "review": "review_summary",
}


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


def canonical_chunk_type(chunk_type: str) -> str:
    normalized = (chunk_type or "").strip()
    return CHUNK_TYPE_ALIASES.get(normalized, normalized)


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
                chunk_type=canonical_chunk_type(chunk_type),
                source_type=source_type,
                trust_level=trust_level,
                document_version=version,
                content=normalized,
                metadata=metadata or {},
            )
        )

    spec_parts = [
        f"title: {product.title}",
        f"brand: {product.brand}",
        f"category: {product.category}",
        f"sub_category: {product.sub_category}",
        f"price: {product.price}",
    ]
    if product.extracted_terms:
        spec_parts.append("terms: " + " ".join(product.extracted_terms))
    if product.skus:
        sku_text = []
        for sku in product.skus:
            properties = " ".join(f"{key}:{value}" for key, value in sku.properties.items())
            sku_text.append(f"{sku.sku_id} {properties} price:{sku.price}")
        spec_parts.append("SKU: " + ";".join(sku_text))
    add("specification", "\n".join(spec_parts), metadata={"price": product.price})

    for index, sku in enumerate(product.skus):
        properties = " ".join(f"{key}:{value}" for key, value in sku.properties.items())
        add(
            "sku",
            f"SKU: {sku.sku_id}\nproperties: {properties}\nprice: {sku.price}",
            sku_id=sku.sku_id,
            metadata={"sku_index": index, "sku_properties": dict(sku.properties), "sku_price": sku.price},
        )

    for index, sentence in enumerate(_split_sentences(product.marketing_description)):
        add(
            "official_description",
            sentence,
            source_type="marketing_copy",
            trust_level="marketing",
            metadata={"section": "marketing", "sentence_index": index},
        )

    for index, text in enumerate(_split_long_text(product.chunk, max_chars=300)):
        add(
            "official_description",
            text,
            source_type="official_detail",
            trust_level="official",
            metadata={"section": "detail", "part_index": index},
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
                review_lines.append(f"{content} rating:{rating}")
            elif content:
                review_lines.append(content)
        add(
            "review_summary",
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
    parts = re.split(r"(?<=[\u3002\uff01\uff1f\uff1b!?;\.])\s*", normalized)
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
            normalized.rfind("\u3002", start, end),
            normalized.rfind("\uff01", start, end),
            normalized.rfind("\uff1f", start, end),
            normalized.rfind("\uff1b", start, end),
            normalized.rfind(".", start, end),
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
