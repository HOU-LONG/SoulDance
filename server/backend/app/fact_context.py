"""事实上下文构建器 — 将检索排序结果组装为 LLM 唯一事实来源。"""
from __future__ import annotations

import re

from .models import RankedProduct, FactContext, FactRecord


class FactContextBuilder:
    """将检索排序结果组装为 FactContext。

    prompt_block 注入 LLM system prompt 末尾，要求 LLM 用 [[product_id]] 锚点
    格式引用商品。product_index 供 AnchorValidator 流式校验；brand_index 供
    ConsistencyTracker 使用。
    """

    def build(self, ranked: list[RankedProduct], *,
              denied_queries: list[str] | None = None) -> FactContext:
        if not ranked:
            return FactContext(denied_queries=list(denied_queries or []))

        records: list[FactRecord] = []
        for item in ranked:
            product = item.product
            records.append(FactRecord(
                product_id=product.product_id,
                title=product.title,
                brand=product.brand,
                price=product.price,
                category=product.category,
                sub_category=product.sub_category,
                key_specs=self._extract_key_specs(product),
            ))

        product_index = {r.product_id: r for r in records}
        brand_index: dict[str, list[str]] = {}
        for r in records:
            brand_index.setdefault(r.brand, []).append(r.product_id)

        return FactContext(
            prompt_block=self._render_prompt_block(records),
            product_index=product_index,
            brand_index=brand_index,
            denied_queries=list(denied_queries or []),
        )

    def _extract_key_specs(self, product) -> list[str]:
        keywords: list[str] = []
        desc = (product.marketing_description or "").strip()
        if desc:
            parts = re.split(r"[，,、\s]+", desc)
            keywords.extend(p.strip() for p in parts[:3] if 2 <= len(p.strip()) <= 20)
        for review in (product.reviews or [])[:3]:
            text = str(review.get("content", ""))
            if text and len(text) < 30:
                keywords.append(text.strip())
        seen: set[str] = set()
        result: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                result.append(kw)
                if len(result) >= 5:
                    break
        return result

    def _render_prompt_block(self, records: list[FactRecord]) -> str:
        lines = [
            "[可用商品事实库] — 以下是你唯一可以引用的商品信息。",
            "引用时必须使用 [[product_id]] 锚点格式。",
            "任何未列在此库中的商品名称、型号、价格均视为不存在，禁止提及。",
            "",
        ]
        for i, r in enumerate(records, 1):
            specs_str = " | ".join(r.key_specs) if r.key_specs else "暂无详细规格"
            lines.append(
                f"{i}. [[{r.product_id}]]\n"
                f"   名称: {r.title}\n"
                f"   品牌: {r.brand} | 价格: ¥{r.price:.0f}\n"
                f"   核心卖点: {specs_str}\n"
            )
        lines.extend([
            "规则：",
            "- 推荐或提及任何商品时，必须使用准确的 [[product_id]] 锚点",
            "- 如果要比较价格/参数，只能使用上面列出的数值",
            "- 如果用户问的商品不在库中，直接说「库中暂无此商品，请确认型号」",
            "- 不要编造任何商品名称、型号或价格",
        ])
        return "\n".join(lines)
