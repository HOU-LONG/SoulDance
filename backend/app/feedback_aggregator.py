from __future__ import annotations

from .feedback_store import FeedbackStore
from .models import FeedbackEvent, FeedbackSignal


class FeedbackAggregator:
    """将原始 FeedbackEvent 聚合为可用的 FeedbackSignal 权重。

    权重规则（可调）:
      - 显式 👍: 商品 +0.5, 同品牌 +0.2
      - 显式 👎: 商品 -1.0, 同品牌 -0.8
      - 加购:     商品 +1.0
      - 下单:     商品 +2.0
      - "不要Brand": 品牌 -2.0
      - "更便宜":   价格偏好标记
      - "更贵":     价格偏好标记
    """

    def __init__(self, feedback_store: FeedbackStore):
        self._store = feedback_store

    def aggregate(self, session_id: str) -> FeedbackSignal:
        """聚合当前 session 的全部反馈。"""
        events = self._store.get_all_events(session_id)
        signal = FeedbackSignal()
        seen_price_pref: set[str] = set()

        for event in events:
            pid = event.product_id
            stype = event.signal_type

            if stype == "explicit_rating" and pid:
                if event.rating == 1:
                    signal.product_boosts[pid] = signal.product_boosts.get(pid, 0.0) + 0.5
                elif event.rating == -1:
                    signal.product_boosts[pid] = signal.product_boosts.get(pid, 0.0) - 1.0
                if event.context:
                    brand = str(event.context.get("brand", ""))
                    if brand:
                        delta = 0.2 if event.rating == 1 else -0.8
                        signal.brand_weights[brand] = signal.brand_weights.get(brand, 0.0) + delta

            elif stype == "quick_action":
                label = event.action_label or ""
                if "不要" in label:
                    brand = label.replace("不要", "").strip()
                    signal.brand_weights[brand] = signal.brand_weights.get(brand, 0.0) - 2.0
                if "更便宜" in label:
                    signal.price_preference = "更便宜"
                    seen_price_pref.add("cheaper")
                if "更贵" in label:
                    signal.price_preference = "更贵"
                    seen_price_pref.add("expensive")
                # 提取偏好标签
                for tag in ["户外", "拍照", "续航", "性能", "轻薄", "清爽", "温和", "保湿"]:
                    if tag in label:
                        signal.preference_tags.append(tag)

            elif stype == "add_to_cart" and pid:
                signal.product_boosts[pid] = signal.product_boosts.get(pid, 0.0) + 1.0

            elif stype == "checkout" and pid:
                signal.product_boosts[pid] = signal.product_boosts.get(pid, 0.0) + 2.0

            elif stype == "followup":
                label = event.action_label or ""
                if "更便宜" in label or "便宜" in label:
                    signal.price_preference = "更便宜"
                    seen_price_pref.add("cheaper")

        # 冲突时以最后一次为准（不去重，keep last assignment）
        return signal
