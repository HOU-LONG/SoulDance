from __future__ import annotations

import json
import logging

from ..models import ComparisonResult, DimensionScore, Product

logger = logging.getLogger(__name__)


COMPARISON_SYSTEM_PROMPT = """你是电商导购后端的商品对比分析器。只输出 JSON。
根据提供的商品信息和用户需求，自动提取最关键的对比维度（3-5个），
每个维度给出各商品的得分和胜者。
最终给出综合推荐和各商品适用场景。"""


class ComparisonEngine:
    def __init__(self, llm_client):
        self._llm = llm_client

    async def compare(self, products: list[Product], user_message: str) -> ComparisonResult:
        if not hasattr(self._llm, "_json_completion"):
            return self._fallback_compare(products, user_message)
        try:
            raw = await self._llm._json_completion([
                {"role": "system", "content": COMPARISON_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({
                    "user_message": user_message,
                    "products": [
                        {
                            "product_id": p.product_id,
                            "title": p.title,
                            "brand": p.brand,
                            "price": p.price,
                            "category": p.category,
                            "sub_category": p.sub_category,
                            "key_features": p.extracted_terms,
                            "rating": p.review_rating,
                            "search_text": p.search_text[:500],
                        }
                        for p in products
                    ],
                }, ensure_ascii=False)},
            ], temperature=0)
            data = json.loads(raw)
            if not data:
                # 熔断 fallback 或 LLM 主动返回空 JSON：直接走 rule-based，不打 stack trace
                logger.info("LLM comparison returned empty JSON, using rule-based fallback")
                return self._fallback_compare(products, user_message)
            return ComparisonResult.model_validate(data)
        except Exception:
            logger.warning("LLM comparison failed, falling back to rule-based comparison", exc_info=True)
            return self._fallback_compare(products, user_message)

    def _fallback_compare(self, products: list[Product], user_message: str) -> ComparisonResult:
        dimensions = [
            DimensionScore(
                dimension="价格",
                winner_product_id=min(products, key=lambda p: p.price).product_id,
                scores={p.product_id: float(p.price) for p in products},
                explanation="价格越低越有竞争力",
            ),
            DimensionScore(
                dimension="品牌",
                winner_product_id=products[0].product_id,
                scores={p.product_id: 1.0 for p in products},
                explanation="品牌各有特色",
            ),
            DimensionScore(
                dimension="类目",
                winner_product_id=products[0].product_id,
                scores={p.product_id: 1.0 for p in products},
                explanation="类目匹配",
            ),
            DimensionScore(
                dimension="用户关心点",
                winner_product_id=products[0].product_id,
                scores={p.product_id: 1.0 for p in products},
                explanation="与需求相关",
            ),
        ]
        if any(product.review_rating for product in products):
            dimensions.append(
                DimensionScore(
                    dimension="口碑",
                    winner_product_id=max(products, key=lambda p: p.review_rating).product_id,
                    scores={p.product_id: p.review_rating for p in products},
                    explanation="评分越高越好",
                )
            )
        return ComparisonResult(
            product_ids=[p.product_id for p in products],
            dimensions=dimensions,
            overall_winner=dimensions[0].winner_product_id,
            overall_reason="综合价格、品牌和类目维度",
        )
