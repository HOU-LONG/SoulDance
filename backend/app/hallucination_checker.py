from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import RankedProduct


@dataclass
class HallucinationReport:
    is_clean: bool = True
    fabricated_product_ids: list[str] = field(default_factory=list)
    price_mismatches: list[dict] = field(default_factory=list)
    fabricated_attributes: list[str] = field(default_factory=list)


class HallucinationChecker:
    """检测 LLM 回复中的幻觉信息。"""

    def __init__(self, price_tolerance: float = 0.1):
        self.price_tolerance = price_tolerance

    def verify(
        self,
        response_text: str,
        allowed_products: list[RankedProduct],
    ) -> HallucinationReport:
        report = HallucinationReport()
        allowed_ids = {item.product.product_id for item in allowed_products}
        allowed_titles = {item.product.title for item in allowed_products}
        title_to_price = {item.product.title: item.product.price for item in allowed_products}

        # 1. 检测虚构 product_id
        id_pattern = re.compile(r'product_id[:\s]*["\']?(\w+)')
        for match in id_pattern.finditer(response_text):
            pid = match.group(1)
            if pid not in allowed_ids:
                report.fabricated_product_ids.append(pid)
                report.is_clean = False

        # 2. 检测价格偏差
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

        # 3. 检测虚构商品名
        for match in re.finditer(r'「([^」]+)」', response_text):
            name = match.group(1)
            if name not in allowed_titles and not any(
                name in title or title in name for title in allowed_titles
            ):
                report.fabricated_attributes.append(name)
                report.is_clean = False

        return report
