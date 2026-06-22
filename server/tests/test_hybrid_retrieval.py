import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import Product as ProductOrm, ProductChunk
from backend.app.models import HardConstraints, Product, RetrievalPlan
from backend.app.rag.fusion import HybridRetriever, rrf_fuse
from backend.app.rag.lexical_search import lexical_search_chunks
from backend.app.rag.vector_search import vector_search_chunks


def test_rrf_uses_two_independent_ranked_lists():
    lexical = [("p1", 10.0), ("p2", 8.0), ("p3", 1.0)]
    vector = [("p2", 0.9), ("p4", 0.8), ("p1", 0.1)]

    fused = rrf_fuse(lexical, vector, top_k=4)

    assert [pid for pid, _ in fused][:2] == ["p2", "p1"]


def test_lexical_search_chunks_matches_text_and_applies_category_filter():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _insert_product(session, "p1", category="beauty", sub_category="cleanser")
        _insert_product(session, "p2", category="electronics", sub_category="headphones")
        session.add_all(
            [
                _chunk("c1", "p1", "beauty", "cleanser", "敏感肌 温和 洁面"),
                _chunk("c2", "p2", "electronics", "headphones", "敏感肌 头戴耳机"),
            ]
        )
        session.commit()

        results = lexical_search_chunks(
            session,
            "敏感肌",
            HardConstraints(category="beauty"),
            top_k=5,
        )

    assert [product_id for product_id, _ in results] == ["p1"]


def test_vector_search_chunks_uses_json_embedding_similarity():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _insert_product(session, "p1")
        _insert_product(session, "p2")
        session.add_all(
            [
                _chunk("c1", "p1", embedding=[1.0, 0.0]),
                _chunk("c2", "p2", embedding=[0.0, 1.0]),
            ]
        )
        session.commit()

        results = vector_search_chunks(
            session,
            np.asarray([0.9, 0.1], dtype=float),
            HardConstraints(),
            top_k=2,
        )

    assert results[0][0] == "p1"


def test_hybrid_retriever_maps_chunk_results_to_products():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _insert_product(session, "p1", category="beauty", sub_category="cleanser")
        session.add(_chunk("c1", "p1", "beauty", "cleanser", "敏感肌 温和 洁面"))
        session.commit()

    products = [
        Product(
            product_id="p1",
            title="Gentle Cleanser",
            brand="BrandA",
            category="beauty",
            sub_category="cleanser",
            price=99.0,
            image_path="",
            chunk="敏感肌 温和 洁面",
            search_text="敏感肌 温和 洁面",
        )
    ]
    base_retriever = type("BaseRetriever", (), {"products": products, "model": None})()
    plan = RetrievalPlan(
        retrieval_query="敏感肌洁面",
        hard_constraints=HardConstraints(category="beauty"),
    )

    retriever = HybridRetriever(base_retriever, session_factory=lambda: Session(engine))
    results = retriever.search(plan, top_k=3)

    assert [(product.product_id, score) for product, score in results][0][0] == "p1"


def _insert_product(
    session: Session,
    product_id: str,
    category: str = "beauty",
    sub_category: str = "cleanser",
) -> None:
    session.add(
        ProductOrm(
            product_id=product_id,
            title=product_id,
            brand="BrandA",
            category=category,
            sub_category=sub_category,
            price=99.0,
            image_path="",
            chunk="",
            search_text="",
        )
    )


def _chunk(
    chunk_id: str,
    product_id: str,
    category: str = "beauty",
    sub_category: str = "cleanser",
    content: str = "content",
    embedding: list[float] | None = None,
) -> ProductChunk:
    return ProductChunk(
        chunk_id=chunk_id,
        product_id=product_id,
        category_id=category,
        sub_category=sub_category,
        chunk_type="description",
        source_type="fixture",
        trust_level="official",
        document_version=1,
        content=content,
        embedding=embedding,
    )
