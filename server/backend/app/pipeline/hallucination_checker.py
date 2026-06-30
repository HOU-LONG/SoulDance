"""幻觉检测器（兜底层）— 保留价格偏差检测。虚构 ID/名称检测已由 AnchorValidator 覆盖。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import FactContext


@dataclass
class HallucinationReport:
    is_clean: bool = True
    price_mismatches: list[dict] = field(default_factory=list)


class HallucinationChecker:
    """价格偏差检测器（AnchorValidator 的兜底层）。"""

    def __init__(self, price_tolerance: float = 0.1):
        self.price_tolerance = price_tolerance

    def verify(self, response_text: str, fact_ctx: FactContext) -> HallucinationReport:
        """校验文本中的价格是否与 FactContext 一致。"""
        report = HallucinationReport()
        title_to_price = {r.title: r.price for r in fact_ctx.product_index.values()}
        if not title_to_price:
            return report

        price_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*元')
        for match in price_pattern.finditer(response_text):
            mentioned_price = float(match.group(1))
            for title, actual_price in title_to_price.items():
                if title in response_text:
                    if abs(mentioned_price - actual_price) / max(actual_price, 1) > self.price_tolerance:
                        report.price_mismatches.append({
                            "product": title,
                            "mentioned": mentioned_price,
                            "actual": actual_price,
                        })
                        report.is_clean = False
        return report
