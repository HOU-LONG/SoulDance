"""LLM 优先的工具调度器。

设计原则：
- LLM 输出 ToolPlan JSON 决定调什么工具 + 关键参数
- 规则只在 2 处保留：
  1. 极简的 cart 短路（"加入购物车"等强信号 + product_followup 请求）
  2. LLM 调用失败兜底（默认 chitchat）
- 不再前置 rule_semantic_frame / IntentCompiler 那一套规则栈
"""
from __future__ import annotations

import json
import re
from typing import Any

from .models import ChatRequest, SessionContext
from .tool_plan import ToolPlan, ToolPlanArgs


class ToolPlanner:
    """LLM 优先的工具调度入口。"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def plan(self, request: ChatRequest, context: SessionContext) -> ToolPlan:
        # 1. product_followup 类型的 request 直接固定 tool（前端传过来的明确意图）
        if request.type == "product_followup":
            return ToolPlan(
                tool="product_followup",
                args=ToolPlanArgs(),
                confidence=1.0,
            )

        # 2. LLM 主流程
        context_payload = self._context_payload(context)
        try:
            raw = await self.llm_client.plan_tool(request.message or "", context_payload)
            plan = self._parse_plan(raw)
            if plan is not None:
                return plan
        except Exception:
            pass

        # 3. LLM 失败兜底——保守判断（基于关键词）
        return self._rule_fallback(request, context)

    # ----- 内部 -----

    def _context_payload(self, context: SessionContext) -> dict[str, Any]:
        return {
            "has_focus_product": bool(context.focus_product_id),
            "focus_product_id": context.focus_product_id,
            "last_product_ids": context.last_product_ids[-5:] if context.last_product_ids else [],
            "recent_cart_product_id": context.recent_cart_product_id,
        }

    def _parse_plan(self, raw: str) -> ToolPlan | None:
        if not raw or not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        try:
            return ToolPlan.model_validate(data)
        except Exception:
            return None

    def _rule_fallback(self, request: ChatRequest, context: SessionContext) -> ToolPlan:
        """LLM 真挂了：用极简规则决定 tool（保守路线，多走 chitchat 让用户自然收到回复）。"""
        text = (request.message or "").strip()
        if re.search(r"加入购物车|加购|放购物车|结算|下单", text):
            return ToolPlan(
                tool="cart_operation",
                args=ToolPlanArgs(cart_action="add", cart_target="focus_product"),
                confidence=0.5,
            )
        if re.search(r"对比|比较一下", text):
            return ToolPlan(tool="compare_products", args=ToolPlanArgs(), confidence=0.5)
        return ToolPlan(tool="chitchat", args=ToolPlanArgs(), confidence=0.3)
