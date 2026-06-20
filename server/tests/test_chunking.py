from backend.app.models import Product
from backend.app.rag.chunking import chunk_product


def test_chunk_product_emits_expected_chunk_types():
    product = Product(
        product_id="p1",
        title="Gentle Cleanser",
        brand="BrandA",
        category="beauty",
        sub_category="cleanser",
        price=99.0,
        image_path="",
        marketing_description="温和清洁。保湿不紧绷。",
        faqs=[{"question": "敏感肌能用吗", "answer": "可以，建议先局部测试。"}],
        reviews=[
            {"content": "洗完不紧绷"},
            {"content": "敏感肌用着舒服"},
            {"content": "泡沫细腻"},
        ],
        chunk="适合日常洁面。",
        search_text="敏感肌 温和 保湿",
        extracted_terms=["敏感肌", "保湿"],
    )

    chunks = chunk_product(product)
    types = {chunk.chunk_type for chunk in chunks}

    assert {"specification", "feature", "marketing", "review", "faq", "description"} <= types
    assert all(chunk.product_id == "p1" for chunk in chunks)
    assert all(chunk.category_id == "beauty" for chunk in chunks)
    assert all(chunk.document_version == 1 for chunk in chunks)
    assert all(chunk.content.strip() for chunk in chunks)


def test_chunk_product_splits_long_description():
    long_text = "敏感肌可用。" * 80
    product = Product(
        product_id="p2",
        title="Long Detail Product",
        brand="BrandB",
        category="beauty",
        sub_category="serum",
        price=199.0,
        image_path="",
        chunk=long_text,
    )

    chunks = chunk_product(product)
    description_chunks = [chunk for chunk in chunks if chunk.chunk_type == "description"]

    assert len(description_chunks) > 1
    assert all(len(chunk.content) <= 360 for chunk in description_chunks)
