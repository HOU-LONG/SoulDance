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
class ToolPlanner:
    """LLM 优先的工具调度入口。"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def plan(self, request: ChatRequest, context: SessionContext):
        """返回 UnifiedPlan（Stage 2 迁移后统一载体）。"""
        from .models import UnifiedPlan

        # 1. product_followup 类型的 request 直接固定 tool
        if request.type == "product_followup":
            return UnifiedPlan(tool="product_followup", confidence=1.0)

        # 2. LLM 主流程
        context_payload = self._context_payload(context)
        try:
            raw = await self.llm_client.plan_tool(request.message or "", context_payload)
            plan = self._parse_plan(raw)
            if plan is not None:
                return plan
        except Exception:
            pass

        # 3. LLM 失败兜底
        result = self._rule_fallback(request, context)
        print(f"[DEBUG_TP] rule_fallback tool={result.tool}", file=sys.stderr, flush=True)
        return result

    # ----- 内部 -----

    def _context_payload(self, context: SessionContext) -> dict[str, Any]:
        return {
            "has_focus_product": bool(context.focus_product_id),
            "focus_product_id": context.focus_product_id,
            "last_product_ids": context.last_product_ids[-5:] if context.last_product_ids else [],
            "recent_cart_product_id": context.recent_cart_product_id,
        }

    def _parse_plan(self, raw: str):
        if not raw or not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        try:
            from .models import UnifiedPlan
            return UnifiedPlan.model_validate(data)
        except Exception:
            return None

    def _rule_fallback(self, request: ChatRequest, context: SessionContext):
        """LLM 挂了——规则兜底返回 UnifiedPlan。"""
        from .models import UnifiedPlan
        text = (request.message or "").strip()
        if re.search(r"加入购物车|加购|放购物车|结算|下单", text):
            return UnifiedPlan(tool="cart_operation", cart_action="add", confidence=0.5)
        if re.search(r"对比|比较一下", text):
            return UnifiedPlan(tool="compare_products", confidence=0.5)
        return UnifiedPlan(tool="chitchat", confidence=0.3)
