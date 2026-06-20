from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import ProductChunk
from backend.app.db.seed import seed_products
from backend.app.models import Product


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
            chunk="温和洁面，适合敏感肌。",
            marketing_description="温和清洁。保湿不紧绷。",
            search_text="敏感肌 温和 保湿",
        )
    ]
    with Session(engine) as session:
        seed_products(products, session, embedder=None)
        chunks = session.query(ProductChunk).filter_by(product_id="p1").all()

    assert chunks
    assert chunks[0].content
    assert chunks[0].embedding is None
