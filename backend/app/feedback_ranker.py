from __future__ import annotations

from .feedback_aggregator import FeedbackAggregator
from .models import RankedProduct


class FeedbackAwareRanker:
    """在已有排序结果上叠加反馈信号权重。

    不修改原始 rank_products() 逻辑，仅在其输出上做增量调整。
    """

    def __init__(self, aggregator: FeedbackAggregator):
        self._aggregator = aggregator

    def apply(self, ranked: list[RankedProduct], session_id: str) -> list[RankedProduct]:
        """注入反馈权重后重新排序。无反馈信号时原样返回。"""
        if not ranked:
            return ranked

        signal = self._aggregator.aggregate(session_id)
        if not _has_signal(signal):
            return ranked

        for item in ranked:
            pid = item.product.product_id
            brand = item.product.brand
            price = item.product.price

            # 商品级 boost
            item.score += signal.product_boosts.get(pid, 0.0)

            # 品牌级 weight
            item.score += signal.brand_weights.get(brand, 0.0)

            # 价格偏好
            if signal.price_preference == "更便宜":
                item.score += 2.0 / max(price, 1.0)
            elif signal.price_preference == "更贵":
                item.score += price / 1000.0

            # 标签偏好
            for tag in signal.preference_tags:
                if tag in item.product.search_text:
                    item.score += 1.0

        ranked.sort(key=lambda x: (x.tier == 1, x.tier == 2, x.score), reverse=True)
        return ranked


def _has_signal(signal) -> bool:
    return bool(
        signal.product_boosts
        or signal.brand_weights
        or signal.price_preference
        or signal.preference_tags
    )
