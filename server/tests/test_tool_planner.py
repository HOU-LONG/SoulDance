"""ToolPlanner 单元测试。

覆盖：
- LLM 主流程：FakeLLMClient.plan_tool 根据关键词路由到正确 tool
- product_followup 直接 short-circuit（来自前端的 request.type）
- LLM 失败兜底走 chitchat
"""
from __future__ import annotations

import asyncio

import pytest

from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest, SessionContext
from backend.app.tool_plan import ToolPlan
from backend.app.tool_planner import ToolPlanner


@pytest.fixture()
def planner() -> ToolPlanner:
    return ToolPlanner(FakeLLMClient())


def _ctx(session_id: str = "test_session", focus_product_id: str | None = None) -> SessionContext:
    ctx = SessionContext(session_id=session_id)
    if focus_product_id:
        ctx.focus_product_id = focus_product_id
    return ctx


def _req(message: str, *, request_type: str = "user_message") -> ChatRequest:
    return ChatRequest(type=request_type, session_id="test_session", message=message)


def test_product_followup_request_type_short_circuits(planner: ToolPlanner):
    """前端发 product_followup 类型时直接固定 tool=product_followup。"""
    plan = asyncio.run(planner.plan(
        _req("换一个", request_type="product_followup"),
        _ctx(),
    ))
    assert plan.tool == "product_followup"


def test_cart_keywords_route_to_cart_operation(planner: ToolPlanner):
    """'加入购物车'等强信号 → cart_operation。"""
    plan = asyncio.run(planner.plan(_req("把这个加入购物车"), _ctx()))
    assert plan.tool == "cart_operation"
    assert plan.args.cart_action == "add"


def test_compare_keywords_route_to_compare(planner: ToolPlanner):
    plan = asyncio.run(planner.plan(_req("对比一下华为 P70 和 iPhone 15"), _ctx()))
    assert plan.tool == "compare_products"


def test_product_with_specific_model_routes_to_analysis(planner: ToolPlanner):
    """'华为 Pura 90 Pro 价格' → product_analysis。"""
    plan = asyncio.run(planner.plan(_req("华为 Pura 90 Pro 的价格是多少"), _ctx()))
    assert plan.tool == "product_analysis"
    assert plan.args.target_product_query, "应抽取用户原话商品名片段"
    assert plan.args.analysis_aspect == "price"


def test_recommendation_intent_with_category(planner: ToolPlanner):
    """'推荐一款防晒霜' → recommend_product。"""
    plan = asyncio.run(planner.plan(_req("推荐一款防晒霜"), _ctx()))
    assert plan.tool == "recommend_product"


def test_followup_kind_inferred_when_focus_present(planner: ToolPlanner):
    """已有焦点商品时'换个更便宜的' → product_followup, kind=cheaper。"""
    plan = asyncio.run(planner.plan(
        _req("换个更便宜的"),
        _ctx(focus_product_id="p_xyz"),
    ))
    assert plan.tool == "product_followup"
    assert plan.args.followup_kind == "cheaper"


def test_pure_greeting_routes_to_chitchat(planner: ToolPlanner):
    plan = asyncio.run(planner.plan(_req("你好"), _ctx()))
    assert plan.tool == "chitchat"


def test_weather_chitchat(planner: ToolPlanner):
    plan = asyncio.run(planner.plan(_req("今天天气真好"), _ctx()))
    assert plan.tool == "chitchat"


def test_scenario_bundle_route(planner: ToolPlanner):
    plan = asyncio.run(planner.plan(_req("去三亚度假带什么搭配"), _ctx()))
    assert plan.tool == "scenario_bundle"


def test_planner_handles_empty_message(planner: ToolPlanner):
    plan = asyncio.run(planner.plan(_req(""), _ctx()))
    assert isinstance(plan, ToolPlan)


def test_llm_failure_falls_back_to_chitchat():
    """LLM 抛异常时兜底走 chitchat（非加购非对比关键词）。"""
    class BrokenLLM:
        async def plan_tool(self, message, context):
            raise RuntimeError("LLM down")

    planner = ToolPlanner(BrokenLLM())
    plan = asyncio.run(planner.plan(_req("随便说点什么"), _ctx()))
    assert plan.tool == "chitchat"


def test_llm_failure_falls_back_to_cart_on_strong_signal():
    """LLM 挂时'加入购物车'强信号仍能保留 cart 行为。"""
    class BrokenLLM:
        async def plan_tool(self, message, context):
            raise RuntimeError("LLM down")

    planner = ToolPlanner(BrokenLLM())
    plan = asyncio.run(planner.plan(_req("加入购物车"), _ctx()))
    assert plan.tool == "cart_operation"


def test_invalid_json_falls_back_to_chitchat():
    """LLM 返回非 JSON 字符串时兜底走 chitchat。"""
    class BadJsonLLM:
        async def plan_tool(self, message, context):
            return "这不是合法的 JSON"

    planner = ToolPlanner(BadJsonLLM())
    plan = asyncio.run(planner.plan(_req("你好"), _ctx()))
    assert plan.tool == "chitchat"
