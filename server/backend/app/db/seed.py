from __future__ import annotations

from sqlalchemy.orm import Session

from ..data_loader import load_products
from ..embedding_retriever import EmbeddingRetriever
from ..models import Product
from .base import Base
from .engine import get_engine
from .models import Product as ProductOrm, ProductChunk, SKU as SkuOrm


def seed_products(products: list[Product], session: Session, embedder: EmbeddingRetriever | None = None):
    # 清空旧数据以支持重入
    from sqlalchemy import delete
    session.execute(delete(ProductChunk))
    session.execute(delete(SkuOrm))
    session.execute(delete(ProductOrm))
    session.flush()
    for p in products:
        chunk_text = p.chunk or f"{p.title} {p.marketing_description} {p.search_text}".strip()
        embedding = None
        if embedder and embedder.model is not None:
            embedding = embedder.model.encode([chunk_text], normalize_embeddings=True).tolist()[0]
        orm = ProductOrm(
            product_id=p.product_id,
            title=p.title,
            brand=p.brand,
            category=p.category,
            sub_category=p.sub_category,
            price=p.price,
            image_path=p.image_path,
            brand_region=p.brand_region,
            review_rating=p.review_rating,
            marketing_description=p.marketing_description,
            search_text=p.search_text,
            extracted_terms=p.extracted_terms,
            chunk=p.chunk,
            embedding=embedding,
        )
        session.add(orm)
        session.add(ProductChunk(
            chunk_id=f"chunk_{p.product_id}",
            product_id=p.product_id,
            category_id=p.category,
            sub_category=p.sub_category,
            chunk_type="description",
            source_type="fixture",
            trust_level="official",
            document_version=1,
            content=chunk_text,
            embedding=embedding,
        ))
        for sku in p.skus:
            session.add(SkuOrm(
                sku_id=sku.sku_id,
                product_id=p.product_id,
                properties=sku.properties,
                price=sku.price,
            ))
    session.commit()


def seed_database(settings=None, products: list[Product] | None = None):
    from ..config import get_settings
    settings = settings or get_settings()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    if products is None:
        products = load_products(settings.dataset_path)
    from ..embedding_retriever import EmbeddingRetriever
    # 若 CUDA 不可用则自动回退到 CPU，避免 embedding 模型加载失败
    device = settings.embedding_device
    import torch
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
    embedder = EmbeddingRetriever(products, settings.embedding_path, device, settings.use_embedding)
    with Session(engine) as session:
        seed_products(products, session, embedder)


if __name__ == "__main__":
    seed_database()
