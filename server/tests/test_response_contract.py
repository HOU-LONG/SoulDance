from __future__ import annotations

import asyncio

from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.memory_cache import _short_response_summary
from backend.app.models import HardConstraints, RankedProduct, RetrievalPlan
from backend.app.response_contract import (
    action_message,
    compose_markdown_sections,
    recommendation_contract_text,
)


def test_compose_markdown_sections_preserves_order_and_blank_lines():
    text = compose_markdown_sections(
        [
            ("理解", "你想要一款预算内的防晒。"),
            ("结论", "优先看「清爽防晒」。"),
            ("主推", "它贴合预算和清爽偏好。"),
            ("下一步", "可以继续说要更便宜。"),
        ]
    )

    assert text == (
        "**理解：** 你想要一款预算内的防晒。\n\n"
        "**结论：** 优先看「清爽防晒」。\n\n"
        "**主推：** 它贴合预算和清爽偏好。\n\n"
        "**下一步：** 可以继续说要更便宜。"
    )


def test_recommendation_contract_text_includes_required_sections():
    text = recommendation_contract_text(
        understanding="我按预算 100 元以内和清爽肤感来筛。",
        conclusion="优先看「清爽防晒」。",
        primary_reason="它更贴合你的预算和肤感偏好。",
        next_step="如果想避开某个品牌，可以继续说。",
    )

    assert text.startswith("**理解：**")
    assert "**结论：**" in text
    assert "**主推：**" in text
    assert "**下一步：**" in text
    assert text.index("**理解：**") < text.index("**结论：**") < text.index("**主推：**")


def test_action_message_keeps_short_messages_plain_text():
    text = action_message("已把 清爽防晒 加入购物车。")

    assert text == "已把 清爽防晒 加入购物车。"
    assert "**" not in text
    assert "\n\n" not in text


def test_fake_llm_recommendation_uses_response_contract_sections():
    products = load_products("ecommerce_agent_dataset")
    ranked = [
        RankedProduct(product=products[0], score=1.0, reason="类目精确匹配", evidence=[], tier=1),
        RankedProduct(product=products[1], score=0.8, reason="价格更低", evidence=[], tier=1),
    ]
    plan = RetrievalPlan(
        retrieval_query="推荐防晒",
        hard_constraints=HardConstraints(price_max=100),
    )

    text = asyncio.run(FakeLLMClient().generate_response("推荐防晒", plan, ranked))

    assert_contract_order(text)
    assert products[0].title in text


def test_memory_summary_uses_response_contract_sections():
    products = load_products("ecommerce_agent_dataset")
    ranked = [
        RankedProduct(product=products[0], score=1.0, reason="类目精确匹配", evidence=[], tier=1),
        RankedProduct(product=products[1], score=0.8, reason="价格更低", evidence=[], tier=1),
    ]
    plan = RetrievalPlan(
        retrieval_query="推荐防晒",
        hard_constraints=HardConstraints(price_max=100),
    )

    text = _short_response_summary(plan, ranked)

    assert_contract_order(text)
    assert "复用了已验证的推荐结果" in text


def assert_contract_order(text: str):
    required = ["**理解：**", "**结论：**", "**主推：**", "**下一步：**"]
    for label in required:
        assert label in text
    assert [text.index(label) for label in required] == sorted(text.index(label) for label in required)
