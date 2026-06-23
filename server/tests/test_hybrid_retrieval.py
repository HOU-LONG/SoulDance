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
                _chunk("c1", "p1", "beauty", "cleanser", "sensitive gentle cleanser"),
                _chunk("c2", "p2", "electronics", "headphones", "sensitive headphones"),
            ]
        )
        session.commit()

        results = lexical_search_chunks(
            session,
            "sensitive",
            HardConstraints(category="beauty"),
            top_k=5,
        )

    assert [result.product_id for result in results] == ["p1"]
    assert results[0].chunk_id == "c1"
    assert results[0].chunk_type == "official_description"
    assert results[0].trust_level == "official"


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

    assert results[0].product_id == "p1"
    assert results[0].chunk_id == "c1"
    assert results[0].source_type == "official_detail"


def test_hybrid_retriever_maps_chunk_results_to_products():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _insert_product(session, "p1", category="beauty", sub_category="cleanser")
        session.add(_chunk("c1", "p1", "beauty", "cleanser", "sensitive gentle cleanser"))
        session.commit()

    products = [_product("p1")]
    base_retriever = type("BaseRetriever", (), {"products": products, "model": None})()
    plan = RetrievalPlan(
        retrieval_query="sensitive cleanser",
        hard_constraints=HardConstraints(category="beauty"),
    )

    retriever = HybridRetriever(base_retriever, session_factory=lambda: Session(engine))
    results = retriever.search(plan, top_k=3)

    assert [(product.product_id, score) for product, score in results][0][0] == "p1"


def test_hybrid_retriever_search_with_evidence_returns_supporting_chunks():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _insert_product(session, "p1", category="beauty", sub_category="cleanser")
        session.add(_chunk("c1", "p1", "beauty", "cleanser", "sensitive gentle cleanser"))
        session.commit()

    products = [_product("p1")]
    base_retriever = type("BaseRetriever", (), {"products": products, "model": None})()
    plan = RetrievalPlan(
        retrieval_query="sensitive cleanser",
        hard_constraints=HardConstraints(category="beauty"),
    )

    retriever = HybridRetriever(base_retriever, session_factory=lambda: Session(engine))
    results = retriever.search_with_evidence(plan, top_k=3)

    assert results[0].product.product_id == "p1"
    assert results[0].evidence_chunks[0].chunk_id == "c1"
    assert results[0].evidence_chunks[0].chunk_type == "official_description"


def test_hybrid_retriever_prioritizes_official_chunks_over_reviews_by_default():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _insert_product(session, "official", category="beauty", sub_category="cleanser")
        _insert_product(session, "review", category="beauty", sub_category="cleanser")
        session.add(_chunk("c1", "official", "beauty", "cleanser", "sensitive gentle cleanser", chunk_type="specification"))
        session.add(_chunk("c2", "review", "beauty", "cleanser", "sensitive gentle cleanser", chunk_type="review_summary", source_type="review_summary", trust_level="review_aggregate"))
        session.commit()

    products = [_product("official"), _product("review")]
    base_retriever = type("BaseRetriever", (), {"products": products, "model": None})()
    plan = RetrievalPlan(retrieval_query="sensitive gentle cleanser", hard_constraints=HardConstraints(category="beauty"))

    results = HybridRetriever(base_retriever, session_factory=lambda: Session(engine)).search_with_evidence(plan, top_k=2)

    assert [result.product.product_id for result in results][0] == "official"


def test_review_summary_weight_increases_for_chinese_review_intent():
    from backend.app.rag.types import chunk_relevance_weight

    default_weight = chunk_relevance_weight("sensitive skin", "review_summary", "review_summary", "review_aggregate")
    review_weight = chunk_relevance_weight("\u8bc4\u4ef7 sensitive skin", "review_summary", "review_summary", "review_aggregate")

    assert review_weight > default_weight


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
    chunk_type: str = "official_description",
    source_type: str = "official_detail",
    trust_level: str = "official",
) -> ProductChunk:
    return ProductChunk(
        chunk_id=chunk_id,
        product_id=product_id,
        category_id=category,
        sub_category=sub_category,
        chunk_type=chunk_type,
        source_type=source_type,
        trust_level=trust_level,
        document_version=1,
        content=content,
        embedding=embedding,
    )


def _product(product_id: str) -> Product:
    return Product(
        product_id=product_id,
        title=product_id,
        brand="BrandA",
        category="beauty",
        sub_category="cleanser",
        price=99.0,
        image_path="",
        chunk="sensitive gentle cleanser",
        search_text="sensitive gentle cleanser",
    )
