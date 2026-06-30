"""降级提示 — 上下文感知的 fallback 文案。"""
from __future__ import annotations


def fallback_text_for_failure(reason: str, plan=None, context=None) -> str:
    last_query = ""
    last_product_names: list[str] = []
    if context is not None:
        turns = getattr(context, 'dialog_turns', []) or []
        if turns:
            last_msg = turns[-1].get("content", "") if isinstance(turns[-1], dict) else ""
            last_query = (last_msg or "")[:50]
        for pid in (getattr(context, 'last_product_ids', []) or [])[:3]:
            recs = getattr(context, 'last_recommendations', []) or []
            for rec in recs:
                if isinstance(rec, dict) and rec.get("product_id") == pid:
                    last_product_names.append(str(rec.get("title", pid)))
                    break

    product_hint = ""
    if last_product_names:
        names = "、".join(last_product_names)
        product_hint = f" 你之前关注的商品：{names}。"

    if reason == "llm_timeout":
        if last_product_names:
            return f"我找到了候选商品（含 {names}），但生成详细解释超时了。你可以直接查看商品卡片，或说「详细说说第一款」让我继续。"
        return "我正在检索相关商品，但生成解释超时了。请稍等片刻再试。"

    if reason == "retrieval_error":
        if last_product_names:
            return f"检索服务暂时不稳定，但我还记得你之前关注的商品（{names}）。你可以继续围绕它们提问。"
        return "检索服务暂时不稳定，我先按当前商品库的基础信息给出保守结果。"

    if reason == "llm_error":
        query = f"关于「{last_query}」" if last_query else ""
        return f"{query}LLM 服务调用失败了，我暂时无法生成新的回复。你可以稍后再试。{product_hint}".strip()

    if reason == "hallucination_detected":
        query = f"关于「{last_query}」" if last_query else ""
        return f"{query}我生成的内容存在不准确之处，已触发保护机制。请重新描述你的需求。{product_hint}".strip()

    if reason == "contradiction_blocked":
        return f"当前回复与之前的分析存在矛盾，已被拦截。请换一种方式提问。{product_hint}".strip()

    if reason == "internal_error":
        return "服务暂时不可用，请稍后再试。你的对话记录已保存，不会丢失。"

    return "当前服务暂时不稳定。请稍后重试。"
