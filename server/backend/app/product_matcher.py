"""统一的商品模糊匹配入口。

用户问"华为 Pura 70 Pro"或"小棕瓶"或"雀巢咖啡"时，调底层 BM25/Hybrid retriever
做模糊匹配；比硬编码 score+阈值的 resolve_named_product 更鲁棒，且与全局检索器
共享同一套分词/打分语义。

边界约定：
- 不替换 SessionContext 上下文相关解析（"刚才那个" / "这个" / "focus_product"）——
  那些由 ReferenceResolver/SessionContext 管。本模块只解决"用户用模糊名字直接提到一款商品"的场景。
- 返回 top-N 候选，让调用方决定：命中明确 → 用 best；候选都不像 → 拿前几个回给 LLM 做二次判断或提示用户。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Product


@dataclass(frozen=True)
class ProductMatchResult:
    best: Product | None
    candidates: list[Product] = field(default_factory=list)
    confidence: float = 0.0
    """top1 的 raw score（已 normalize 到 0~1 区间），方便上层决定是否提示"可能不是你想找的"。"""


class ProductMatcher:
    """用底层 retriever 做模糊商品识别。

    底层 retriever 已经具备 jieba 分词 + BM25 + 可选 dense 融合，
    对长标题"华为HUAWEI Pura 70 Pro 超感光影像曲面屏轻薄旗舰手机 12+256GB"
    匹配用户简称"华为 Pura 70"或"Pura 70 Pro"完全够用。

    Args:
        retriever: 实现了 `search(query: str, top_k: int) -> list[tuple[Product, float]]` 的对象。
                   ShopGuideAgent.retriever 直接可用（BM25OnlyRetriever / EmbeddingRetriever）。
    """

    def __init__(self, retriever, *, products: list[Product] | None = None):
        self.retriever = retriever
        self.product_map = {p.product_id: p for p in (products or [])}

    def match(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_gap: float = 0.15,
    ) -> ProductMatchResult:
        """模糊匹配单个查询字符串到商品。

        底层 retriever 会把分数 normalize 到 [0, 1]，top1 始终是 1.0，因此**单看绝对分数
        无法判断匹配强度**。这里用 top1 与剩余候选的"分差"作为置信度信号：

        - 若 top1 - top2 >= min_gap：top1 显著强于其它候选，视为"明确命中"
        - 否则：候选过于模糊（"小米 17" 同时命中 Max/Ultra/Pro），best=None 但 candidates 仍透传

        Args:
            query: 用户原话提取的商品名片段（"华为 Pura 70 Pro" / "小棕瓶" / "雀巢咖啡"）。
            top_k: 返回候选数量。
            min_gap: top1 与 top2 至少要拉开的归一化分差，才视为明确命中。

        Returns:
            ProductMatchResult: best 在置信度足够时给出，否则为 None；candidates 始终给前 top_k。
                                confidence 取 `top1 - top2` 作为相对置信信号（0=模糊，1=唯一命中）。
        """
        if not query or not query.strip():
            return ProductMatchResult(best=None, candidates=[], confidence=0.0)

        try:
            ranked = self.retriever.search(query.strip(), top_k=top_k)
        except Exception:
            return ProductMatchResult(best=None, candidates=[], confidence=0.0)

        if not ranked:
            return ProductMatchResult(best=None, candidates=[], confidence=0.0)

        top_product, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        gap = max(top_score - second_score, 0.0)

        # 1. 若 top1 raw score 本身 <= 0（query 完全没匹到任何 token），明确未命中
        if top_score <= 0.0:
            return ProductMatchResult(best=None, candidates=[], confidence=0.0)

        # 2. 用 gap 判定是否明确命中
        is_confident = gap >= min_gap
        candidates = [product for product, _ in ranked]

        return ProductMatchResult(
            best=top_product if is_confident else None,
            candidates=candidates,
            confidence=gap,
        )

    def match_many(self, queries: list[str], *, top_k: int = 3, min_gap: float = 0.15) -> list[ProductMatchResult]:
        """批量匹配（对比场景用）。"""
        return [self.match(q, top_k=top_k, min_gap=min_gap) for q in queries]
