from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import ProductChunk, SKU as SkuOrm
from backend.app.db.seed import seed_products
from backend.app.models import Product, SKU


def test_seed_writes_sqlite_product_chunks():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    products = [
        Product(
            product_id="p1",
            title="Test Cleanser",
            brand="BrandA",
            category="beauty",
            sub_category="cleanser",
            price=99.0,
            image_path="",
            chunk="Gentle cleanser for sensitive skin.",
            marketing_description="Gentle clean. Hydrating finish.",
            search_text="sensitive gentle hydrating",
        )
    ]
    with Session(engine) as session:
        seed_products(products, session, embedder=None)
        chunks = session.query(ProductChunk).filter_by(product_id="p1", is_active=True).all()

    assert chunks
    assert chunks[0].content
    assert chunks[0].embedding is None
    assert all(chunk.metadata_json.get("content_hash") for chunk in chunks)


def test_seed_products_reindexes_same_product_without_duplicate_active_chunks():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    product = _product("p1", chunk="Gentle cleanser for sensitive skin.")

    with Session(engine) as session:
        seed_products([product], session, embedder=None)
        first_active = session.query(ProductChunk).filter_by(product_id="p1", is_active=True).count()
        seed_products([product], session, embedder=None)
        second_active = session.query(ProductChunk).filter_by(product_id="p1", is_active=True).count()
        total_chunks = session.query(ProductChunk).filter_by(product_id="p1").count()

    assert second_active == first_active
    assert total_chunks == first_active


def test_seed_products_marks_old_chunks_inactive_when_product_content_changes():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        seed_products([_product("p1", chunk="Old description for sensitive skin.")], session, embedder=None)
        seed_products([_product("p1", chunk="New description for sensitive and oily skin.")], session, embedder=None)
        active_chunks = session.query(ProductChunk).filter_by(product_id="p1", is_active=True).all()
        inactive_chunks = session.query(ProductChunk).filter_by(product_id="p1", is_active=False).all()

    assert active_chunks
    assert inactive_chunks
    assert max(chunk.document_version for chunk in active_chunks) == 2
    assert any("Old description" in chunk.content for chunk in inactive_chunks)
    assert any("New description" in chunk.content for chunk in active_chunks)


def test_seed_products_marks_removed_sku_chunk_inactive_and_removes_sku_row():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with_sku = _product(
        "p1",
        skus=[SKU(sku_id="sku-p1-red", properties={"color": "red"}, price=119.0)],
    )
    without_sku = _product("p1", skus=[])

    with Session(engine) as session:
        seed_products([with_sku], session, embedder=None)
        seed_products([without_sku], session, embedder=None)
        active_sku_chunks = session.query(ProductChunk).filter_by(
            product_id="p1", chunk_type="sku", is_active=True
        ).all()
        inactive_sku_chunks = session.query(ProductChunk).filter_by(
            product_id="p1", chunk_type="sku", is_active=False
        ).all()
        sku_rows = session.query(SkuOrm).filter_by(product_id="p1").all()

    assert active_sku_chunks == []
    assert inactive_sku_chunks
    assert sku_rows == []


def test_seed_products_reset_path_clears_catalog():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        seed_products([_product("p1")], session, embedder=None)
        seed_products([_product("p2")], session, embedder=None, reset=True)
        product_ids = {chunk.product_id for chunk in session.query(ProductChunk).all()}

    assert product_ids == {"p2"}


def _product(product_id: str, chunk: str = "Gentle cleanser.", skus: list[SKU] | None = None) -> Product:
    return Product(
        product_id=product_id,
        title="Test Cleanser",
        brand="BrandA",
        category="beauty",
        sub_category="cleanser",
        price=99.0,
        image_path="",
        chunk=chunk,
        marketing_description="Gentle clean. Hydrating finish.",
        search_text="sensitive gentle hydrating",
        skus=skus or [],
    )
