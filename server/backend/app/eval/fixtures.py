"""评测层 fault injection。

apply_fault(app, name) 返回一个 cleanup 函数，runner 在 scenario 结束后调用恢复现场。

支持的 fault 类型：
- llm_timeout: 把 app.state.agent.llm_client 替换为延迟超长的子类，触发 generate_response 的超时降级路径
- stt_unavailable: 把 app.state.agent.stt 替换为抛 RuntimeError 的桩
- websocket_closed: 占位，无副作用（websocket_disconnect 由 runner 直接控制）
- llm_hallucination: 让 llm 返回不存在的 product_id，断言 hallucination_checker 拦截

复用：
- llm_client.FakeLLMClient 是所有 fault LLM 的基类
- tests/test_timeout_degradation.py 中 TimeoutStreamLLM 的延迟模式提取到这里共用
"""

from __future__ import annotations

import asyncio
from typing import Callable

from fastapi import FastAPI

from ..llm_client import FakeLLMClient


class _TimeoutStreamLLM(FakeLLMClient):
    """Generate 流式 response 时人为长时间挂起，触发 first-chunk timeout 降级。

    保持其他方法（json_completion 等）走 FakeLLMClient 默认实现，避免影响 planner / cart 意图识别。
    """

    async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
        await asyncio.sleep(60)  # 远超 DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS
        return "这条回复不会被使用，前端应已收到降级提示"

    async def stream_response(self, user_message, plan, ranked_products, focus_product=None):
        await asyncio.sleep(60)
        if False:
            yield ""


class _STTUnavailableAdapter:
    """模拟 STT 服务不可用。"""

    async def transcribe(self, *_args, **_kwargs):
        raise RuntimeError("语音识别服务不可用")


class _HallucinationLLM(FakeLLMClient):
    """让 LLM 引用一个不存在的 product_id，便于断言 hallucination_checker 拦截。"""

    async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
        return "我推荐 p_phantom_nonexistent，价格便宜功能强大。"


def apply_fault(app: FastAPI, fault_name: str) -> Callable[[], None]:
    """注入指定 fault，返回 cleanup 函数恢复现场。

    cleanup 函数应该是幂等的，runner 在 scenario 结束的 finally 中调用。
    """
    agent = getattr(app.state, "agent", None)
    if agent is None:
        return lambda: None

    if fault_name == "llm_timeout":
        original = agent.llm_client
        agent.llm_client = _TimeoutStreamLLM()

        def _cleanup() -> None:
            agent.llm_client = original

        return _cleanup

    if fault_name == "stt_unavailable":
        # STT 在 agent 上挂作 stt（部分实现）或在 app.state 上挂；按存在性兼容
        original_agent_stt = getattr(agent, "stt", None)
        original_app_stt = getattr(app.state, "stt_adapter", None)
        stub = _STTUnavailableAdapter()
        if original_agent_stt is not None:
            agent.stt = stub  # type: ignore[attr-defined]
        if original_app_stt is not None:
            app.state.stt_adapter = stub

        def _cleanup() -> None:
            if original_agent_stt is not None:
                agent.stt = original_agent_stt  # type: ignore[attr-defined]
            if original_app_stt is not None:
                app.state.stt_adapter = original_app_stt

        return _cleanup

    if fault_name == "llm_hallucination":
        original = agent.llm_client
        agent.llm_client = _HallucinationLLM()

        def _cleanup() -> None:
            agent.llm_client = original

        return _cleanup

    if fault_name == "websocket_closed":
        # 主动断线由 runner 在 step 内驱动，这里没有副作用要恢复
        return lambda: None

    # 未知 fault：不注入，让 runner 报错出来
    raise ValueError(f"unknown fault: {fault_name}")
