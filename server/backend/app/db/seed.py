from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..data_loader import load_products
from ..retrieval.embedding_retriever import EmbeddingRetriever
from ..models import Product
from ..rag.chunking import ChunkMeta, chunk_product
from .base import Base
from .engine import get_engine
from .models import Product as ProductOrm, ProductChunk, SKU as SkuOrm


def seed_products(
    products: list[Product],
    session: Session,
    embedder: EmbeddingRetriever | None = None,
    reset: bool = False,
):
    if reset:
        session.execute(delete(ProductChunk))
        session.execute(delete(SkuOrm))
        session.execute(delete(ProductOrm))
        session.flush()
    for product in products:
        index_product(product, session, embedder=embedder)
    session.commit()


def index_product(
    product: Product,
    session: Session,
    embedder: EmbeddingRetriever | None = None,
) -> None:
    _upsert_product(product, session, embedder)
    session.flush()
    _sync_skus(product, session)
    _sync_product_chunks(product, session, embedder)


def _upsert_product(product: Product, session: Session, embedder: EmbeddingRetriever | None) -> ProductOrm:
    orm = session.query(ProductOrm).filter_by(product_id=product.product_id).one_or_none()
    if orm is None:
        orm = ProductOrm(product_id=product.product_id)
        session.add(orm)
    chunk_text = product.chunk or f"{product.title} {product.marketing_description} {product.search_text}".strip()
    orm.title = product.title
    orm.brand = product.brand
    orm.category = product.category
    orm.sub_category = product.sub_category
    orm.price = product.price
    orm.image_path = product.image_path
    orm.brand_region = product.brand_region
    orm.review_rating = product.review_rating
    orm.marketing_description = product.marketing_description
    orm.search_text = product.search_text
    orm.extracted_terms = list(product.extracted_terms)
    orm.chunk = product.chunk
    orm.embedding = _encode_text(embedder, chunk_text)
    return orm


def _sync_skus(product: Product, session: Session) -> None:
    existing = {
        row.sku_id: row
        for row in session.query(SkuOrm).filter_by(product_id=product.product_id).all()
    }
    incoming_ids = {sku.sku_id for sku in product.skus}
    for sku_id, row in existing.items():
        if sku_id not in incoming_ids:
            session.delete(row)
    for sku in product.skus:
        row = existing.get(sku.sku_id)
        if row is None:
            row = SkuOrm(sku_id=sku.sku_id, product_id=product.product_id)
            session.add(row)
        row.properties = dict(sku.properties)
        row.price = sku.price


def _sync_product_chunks(
    product: Product,
    session: Session,
    embedder: EmbeddingRetriever | None,
) -> None:
    active_chunks = session.query(ProductChunk).filter_by(
        product_id=product.product_id,
        is_active=True,
    ).all()
    existing_chunks = session.query(ProductChunk).filter_by(product_id=product.product_id).all()
    active_by_hash = {
        _metadata_content_hash(chunk.metadata_json): chunk
        for chunk in active_chunks
        if _metadata_content_hash(chunk.metadata_json)
    }
    desired = []
    for position, chunk in enumerate(chunk_product(product), start=1):
        content_hash = chunk_content_hash(chunk)
        metadata = dict(chunk.metadata)
        metadata["content_hash"] = content_hash
        metadata["canonical_chunk_type"] = chunk.chunk_type
        desired.append((position, chunk, metadata, content_hash))

    desired_hashes = {content_hash for _, _, _, content_hash in desired}
    for chunk in active_chunks:
        if _metadata_content_hash(chunk.metadata_json) not in desired_hashes:
            chunk.is_active = False

    new_chunks = [item for item in desired if item[3] not in active_by_hash]
    if not new_chunks:
        return
    next_version = _next_document_version(existing_chunks)
    for position, chunk, metadata, content_hash in new_chunks:
        session.add(
            ProductChunk(
                chunk_id=_chunk_id(product.product_id, next_version, position, content_hash),
                product_id=chunk.product_id,
                sku_id=chunk.sku_id,
                category_id=chunk.category_id,
                sub_category=chunk.sub_category,
                chunk_type=chunk.chunk_type,
                source_type=chunk.source_type,
                trust_level=chunk.trust_level,
                document_version=next_version,
                content=chunk.content,
                embedding=_encode_text(embedder, chunk.content),
                metadata_json=metadata,
                is_active=True,
            )
        )


def chunk_content_hash(chunk: ChunkMeta) -> str:
    payload = {
        "product_id": chunk.product_id,
        "sku_id": chunk.sku_id,
        "category_id": chunk.category_id,
        "sub_category": chunk.sub_category,
        "chunk_type": chunk.chunk_type,
        "source_type": chunk.source_type,
        "trust_level": chunk.trust_level,
        "content": chunk.content,
        "metadata": chunk.metadata,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _chunk_id(product_id: str, version: int, position: int, content_hash: str) -> str:
    product_digest = hashlib.sha1(product_id.encode("utf-8")).hexdigest()[:8]
    return f"chunk_{product_digest}_{version:04d}_{position:03d}_{content_hash[:12]}"


def _metadata_content_hash(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("content_hash")
    return str(value) if value else None


def _next_document_version(chunks: list[ProductChunk]) -> int:
    if not chunks:
        return 1
    return max(chunk.document_version for chunk in chunks) + 1


def _encode_text(embedder: EmbeddingRetriever | None, text: str) -> list[float] | None:
    model = getattr(embedder, "model", None)
    if model is None or not text:
        return None
    return model.encode([text], normalize_embeddings=True).tolist()[0]


def seed_database(settings=None, products: list[Product] | None = None, reset: bool = False):
    from ..config import get_settings
    settings = settings or get_settings()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    if products is None:
        products = load_products(settings.dataset_path)
    from ..retrieval.embedding_retriever import EmbeddingRetriever
    device = settings.embedding_device
    import torch
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
    embedder = EmbeddingRetriever(products, settings.embedding_path, device, settings.use_embedding)
    with Session(engine) as session:
        seed_products(products, session, embedder, reset=reset)


if __name__ == "__main__":
    seed_database()
