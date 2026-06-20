from __future__ import annotations

from copy import deepcopy

from .models import HardConstraints, Product, RankedProduct, RetrievalPlan
from .ranker import rank_products


class RelaxationPolicy:
    """定义自适应检索的约束放松策略。

    当严格检索无法返回足够候选商品时，按预定顺序逐步放宽约束，
    以在召回率和精确度之间取得平衡。
    """

    def __init__(
        self,
        min_candidates: int = 5,
        max_rounds: int = 3,
        relaxation_order: list[str] | None = None,
    ):
        self.min_candidates = min_candidates
        self.max_rounds = max_rounds
        self.relaxation_order = relaxation_order or [
            "soft_preferences",
            "price_range",
            "category_fallback",
        ]


class AdaptiveRetriever:
    """自适应多轮检索器。

    通过渐进式放松约束条件，执行多轮检索并合并结果，
    确保在严格条件无匹配时仍能召回相关商品。
    """

    def __init__(
        self,
        retriever,
        policy: RelaxationPolicy | None = None,
    ):
        self.retriever = retriever
        self.policy = policy or RelaxationPolicy()

    def search(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        """执行多轮自适应检索，返回合并后的候选商品及其分数。

        检索轮次：
        - Round 1: 使用原始 plan 的完整约束进行严格检索。
        - Round 2: 移除 soft_preferences，仅基于 hard constraints 重建查询。
        - Round 3: 进一步移除 price bounds，仅保留类目和品牌等核心约束。

        每轮结果按 product_id 合并，保留最高分数。当累计唯一商品数
        达到 min_candidates 时提前终止。
        """
        merged: dict[str, tuple[Product, float]] = {}

        for round_index in range(self.policy.max_rounds):
            relaxed_plan = self._build_relaxed_plan(plan, round_index)
            retrieved = self.retriever.search(relaxed_plan.retrieval_query, top_k=top_k)

            for product, score in retrieved:
                if product.product_id in merged:
                    existing_product, existing_score = merged[product.product_id]
                    merged[product.product_id] = (existing_product, max(existing_score, score))
                else:
                    merged[product.product_id] = (product, score)

            if len(merged) >= self.policy.min_candidates:
                break

        return sorted(merged.values(), key=lambda item: item[1], reverse=True)[:top_k]

    def rerank_by_price(
        self,
        candidates: list[RankedProduct],
        direction: str,
    ) -> list[RankedProduct]:
        """按价格方向对候选商品重新排序。

        Args:
            candidates: 已排序的候选商品列表。
            direction: "cheaper" 按价格升序，"expensive" 按价格降序。

        Returns:
            按指定价格方向重新排序后的候选商品列表。
        """
        if direction == "cheaper":
            return sorted(candidates, key=lambda item: item.product.price)
        if direction == "expensive":
            return sorted(candidates, key=lambda item: item.product.price, reverse=True)
        return candidates

    def _build_relaxed_plan(self, plan: RetrievalPlan, round_index: int) -> RetrievalPlan:
        """根据当前轮次构建放松后的检索计划。"""
        if round_index == 0:
            return plan

        hard = plan.hard_constraints.model_copy(deep=True)
        soft = dict(plan.soft_preferences)
        query_terms = [plan.retrieval_query]

        # Round 1+ 已处理：按 relaxation_order 逐步放松
        steps_to_apply = self.policy.relaxation_order[: round_index]

        for step in steps_to_apply:
            if step == "soft_preferences":
                soft = {}
            elif step == "price_range":
                hard.price_min = None
                hard.price_max = None
            elif step == "category_fallback":
                hard.sub_category = None

        # 重建查询：优先使用 hard constraints 中的核心信息
        query_parts = []
        if hard.sub_category:
            query_parts.append(hard.sub_category)
        elif hard.category:
            query_parts.append(hard.category)
        if hard.include_brands:
            query_parts.extend(hard.include_brands)
        if soft:
            query_parts.extend(soft.values())
        if not query_parts:
            query_parts = [plan.retrieval_query]

        return RetrievalPlan(
            intent=plan.intent,
            retrieval_mode=plan.retrieval_mode,
            category=plan.category,
            hard_constraints=hard,
            soft_preferences=soft,
            retrieval_query=" ".join(query_parts),
            need_clarification=plan.need_clarification,
            clarification_question=plan.clarification_question,
        )
