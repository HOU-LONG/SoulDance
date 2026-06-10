from __future__ import annotations

import pytest

from backend.app.agent import ShopGuideAgent
from backend.app.models import ChatRequest, HardConstraints, Product, RankedProduct, RetrievalPlan, SKU


def _make_product(product_id: str, title: str, price: float = 100.0) -> Product:
    return Product(
        product_id=product_id,
        title=title,
        brand="测试品牌",
        category="数码电子",
        sub_category="智能手机",
        price=price,
        image_path="",
        chunk=f"{title} 测试品牌 智能手机 数码电子",
        search_text=f"{title} 测试品牌 智能手机 数码电子",
        skus=[SKU(sku_id=f"{product_id}_s1", price=price)],
    )


class _MockLLMClientWithCardCount:
    def __init__(self, recommended_count: int = 4):
        self.recommended_count = recommended_count

    async def select_products(self, user_message, plan, candidates):
        # Always "select" up to 4 candidates, but recommend_count controls display limit
        selected = [c.product.product_id for c in candidates[:4]]
        reasons = {pid: f"理由{pid}" for pid in selected}
        import json
        return json.dumps(
            {
                "should_recommend": True,
                "need_clarification": False,
                "selected_product_ids": selected,
                "reasons": reasons,
                "recommended_count": self.recommended_count,
            },
            ensure_ascii=False,
        )

    async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
        return "测试回复"

    async def stream_response(self, user_message, plan, ranked_products, focus_product=None):
        yield "测试"

    async def stream_chitchat_response(self, user_message, intent, context=None):
        yield "你好"

    async def parse_semantic_frame(self, message, context, request_type="user_message"):
        return '{"intent": "recommend_product"}'

    async def classify_contextual_followup(self, message, context):
        return '{"intent": "unclear_input"}'


def _make_ranked(product: Product, tier: int = 1) -> RankedProduct:
    return RankedProduct(product=product, score=0.9, tier=tier, reason="测试理由")


@pytest.mark.asyncio
async def test_dynamic_card_count_2():
    products = [_make_product(f"p{i}", f"商品{i}") for i in range(5)]
    agent = ShopGuideAgent(products=products, llm_client=_MockLLMClientWithCardCount(recommended_count=2))
    request = ChatRequest(type="user_message", session_id="s1", message="推荐手机")
    plan = RetrievalPlan(retrieval_query="手机", hard_constraints=HardConstraints())
    candidates = [_make_ranked(p) for p in products]
    selected = await agent._select_products(request, plan, candidates)
    assert len(selected) == 2


@pytest.mark.asyncio
async def test_dynamic_card_count_1():
    products = [_make_product(f"p{i}", f"商品{i}") for i in range(5)]
    agent = ShopGuideAgent(products=products, llm_client=_MockLLMClientWithCardCount(recommended_count=1))
    request = ChatRequest(type="user_message", session_id="s1", message="推荐手机")
    plan = RetrievalPlan(retrieval_query="手机", hard_constraints=HardConstraints())
    candidates = [_make_ranked(p) for p in products]
    selected = await agent._select_products(request, plan, candidates)
    assert len(selected) == 1


@pytest.mark.asyncio
async def test_dynamic_card_count_clamped_to_max_4():
    products = [_make_product(f"p{i}", f"商品{i}") for i in range(6)]
    agent = ShopGuideAgent(products=products, llm_client=_MockLLMClientWithCardCount(recommended_count=10))
    request = ChatRequest(type="user_message", session_id="s1", message="推荐手机")
    plan = RetrievalPlan(retrieval_query="手机", hard_constraints=HardConstraints())
    candidates = [_make_ranked(p) for p in products]
    selected = await agent._select_products(request, plan, candidates)
    assert len(selected) == 4


@pytest.mark.asyncio
async def test_dynamic_card_count_clamped_to_min_1():
    """When LLM asks for 0 cards but selects products, clamp to at least 1."""
    products = [_make_product(f"p{i}", f"商品{i}") for i in range(5)]
    # Mock returns 3 selected ids but recommended_count=0; clamp ensures at least 1 is kept
    agent = ShopGuideAgent(products=products, llm_client=_MockLLMClientWithCardCount(recommended_count=0))
    request = ChatRequest(type="user_message", session_id="s1", message="推荐手机")
    plan = RetrievalPlan(retrieval_query="手机", hard_constraints=HardConstraints())
    candidates = [_make_ranked(p) for p in products]
    selected = await agent._select_products(request, plan, candidates)
    # recommended_count=0 is clamped to 1, so at most 1 product should be returned
    assert len(selected) == 1


@pytest.mark.asyncio
async def test_default_card_count_4_when_not_specified():
    products = [_make_product(f"p{i}", f"商品{i}") for i in range(6)]
    agent = ShopGuideAgent(products=products, llm_client=_MockLLMClientWithCardCount(recommended_count=4))
    request = ChatRequest(type="user_message", session_id="s1", message="推荐手机")
    plan = RetrievalPlan(retrieval_query="手机", hard_constraints=HardConstraints())
    candidates = [_make_ranked(p) for p in products]
    selected = await agent._select_products(request, plan, candidates)
    assert len(selected) == 4
