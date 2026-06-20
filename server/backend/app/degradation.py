from __future__ import annotations

from .models import RetrievalPlan


def fallback_text_for_failure(reason: str, plan: RetrievalPlan | None = None) -> str:
    if reason == "llm_timeout":
        return "我已经找到候选商品，但生成详细解释暂时超时了。你可以先查看商品卡片，或者稍后让我继续解释。"
    if reason == "retrieval_error":
        return "检索服务暂时不稳定，我先按当前商品库的基础信息给出保守结果。"
    return "当前服务暂时不稳定，我没有执行任何购物车或订单写操作。请稍后重试。"
