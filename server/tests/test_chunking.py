from backend.app.models import Product, SKU
from backend.app.rag.chunking import canonical_chunk_type, chunk_product


def test_chunk_product_emits_expected_chunk_types():
    product = Product(
        product_id="p1",
        title="Gentle Cleanser",
        brand="BrandA",
        category="beauty",
        sub_category="cleanser",
        price=99.0,
        skus=[SKU(sku_id="sku-p1-blue", properties={"color": "blue", "size": "200ml"}, price=109.0)],
        image_path="",
        marketing_description="Gentle clean. Hydrating finish.",
        faqs=[{"question": "Can sensitive skin use it?", "answer": "Yes, patch test first."}],
        reviews=[
            {"content": "not tight after washing"},
            {"content": "comfortable for sensitive skin"},
            {"content": "fine foam"},
        ],
        chunk="Suitable for daily cleansing.",
        search_text="sensitive gentle hydrating",
        extracted_terms=["sensitive", "hydrating"],
    )

    chunks = chunk_product(product)
    types = {chunk.chunk_type for chunk in chunks}

    assert {"specification", "official_description", "review_summary", "faq", "sku"} <= types
    review_chunks = [chunk for chunk in chunks if chunk.chunk_type == "review_summary"]
    assert review_chunks
    assert all(chunk.source_type == "review_summary" for chunk in review_chunks)
    assert all(chunk.trust_level == "review_aggregate" for chunk in review_chunks)
    sku_chunks = [chunk for chunk in chunks if chunk.chunk_type == "sku"]
    assert any(
        chunk.sku_id == "sku-p1-blue" and "blue" in chunk.content and "109.0" in chunk.content
        for chunk in sku_chunks
    )
    assert all(chunk.product_id == "p1" for chunk in chunks)
    assert all(chunk.category_id == "beauty" for chunk in chunks)
    assert all(chunk.document_version == 1 for chunk in chunks)
    assert all(chunk.content.strip() for chunk in chunks)


def test_chunk_product_splits_long_description():
    long_text = "Sensitive skin friendly. " * 80
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
    description_chunks = [
        chunk
        for chunk in chunks
        if chunk.chunk_type == "official_description" and chunk.metadata.get("section") == "detail"
    ]

    assert len(description_chunks) > 1
    assert all(len(chunk.content) <= 360 for chunk in description_chunks)


def test_legacy_chunk_type_aliases_map_to_canonical_contract():
    assert canonical_chunk_type("description") == "official_description"
    assert canonical_chunk_type("feature") == "official_description"
    assert canonical_chunk_type("marketing") == "official_description"
    assert canonical_chunk_type("review") == "review_summary"
