import asyncio

from backend.app.degradation import fallback_text_for_failure
from backend.app.models import HardConstraints, RetrievalPlan
from backend.app.timeout_policy import TimeoutBudget, run_with_timeout


async def _slow():
    await asyncio.sleep(0.2)
    return "done"


def test_run_with_timeout_returns_fallback_on_timeout():
    result = asyncio.run(
        run_with_timeout(_slow(), timeout_seconds=0.01, fallback="fallback")
    )
    assert result == "fallback"

def test_fallback_text_mentions_degraded_state_without_claiming_fake_success():
    plan = RetrievalPlan(
        retrieval_query="防晒",
        hard_constraints=HardConstraints(category="beauty"),
    )
    text = fallback_text_for_failure("llm_timeout", plan)
    assert "暂时" in text
    assert "**" not in text
    assert "\n\n" not in text
    assert "已下单" not in text
    assert "已加购" not in text

from backend.app.agent import ShopGuideAgent
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest


class TimeoutStreamLLM(FakeLLMClient):
    async def stream_response(self, user_message, plan, ranked_products, focus_product=None):
        await asyncio.sleep(0.2)
        yield "too late"


def test_agent_stream_returns_fallback_text_when_llm_stream_times_out(monkeypatch):
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, TimeoutStreamLLM())
    monkeypatch.setattr("backend.app.agent.DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS", 0.01, raising=False)

    events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="timeout_demo", message="推荐防晒霜"))
    )

    texts = [event.get("text", "") for event in events if event.get("type") == "text_delta"]
    assert any("超时" in text or "暂时" in text for text in texts)
    assert events[-1]["type"] in {"done", "audio_done"}
