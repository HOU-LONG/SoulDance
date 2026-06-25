"""
自适应检索器 — 渐进式约束放松与多轮检索策略。

===== 领域概念扫盲 =====

"约束放松"（Constraint Relaxation）：
用户说"我要 500 元以内的轻薄拍照手机"，但数据库里可能没有同时满足这三个
条件的商品。如果直接返回空结果（"没找到"），用户体验很差。
自适应检索器的做法是：先用完整约束搜索，如果结果不够（< min_candidates），
就按预定顺序逐步放松约束——比如先去掉"拍照"偏好，再去掉"轻薄"偏好，
最后甚至放宽价格上限——直到返回足够的候选商品。

"relaxation_order"（放松顺序）：
[soft_preferences, price_range, category_fallback] 三步策略：
1. soft_preferences：去掉所有软偏好（拍照/轻薄/送礼等），只保留硬约束（价格/品类/排除项）
2. price_range：再放宽价格上下限（硬约束级别）
3. category_fallback：最后放宽子品类限制，只保留大类

这个顺序是根据业务影响排的——软偏好对结果准确性影响最小（可先去），
品类是最核心的用户意图（最后才放弃）。

"证据收集"（last_evidence_by_product）：
HybridRetriever 返回的每个商品都带有 evidence_chunks（从哪些 chunk 检索到的），
adaptive_retriever 将 chunks 格式化为可读文本并保存在 last_evidence_by_product 中，
后续 agent 用这些证据帮助 LLM 解释"为什么推荐这个商品"。

"Hybrid 优先 + 基础回退"（search_async）：
第一轮优先走 HybridRetriever（BM25 + 向量 + RRF 融合 + Reranker 重排），
如果返回非空结果直接结束。只有 hybrid 失败或返回空时，才回退到基础 retriever
的渐进放松循环。这样可以同时获得高质量结果（hybrid）和鲁棒性（fallback）。

===== 与其它模块协作 =====

- agent.py：ShopGuideAgent 调用 search_async() 获取检索结果和证据
- rag/reranker.py / rag/reranker_scenarios.py：重排场景检测和 Reranker 调用
- rag/fusion.py：HybridRetriever.search_with_evidence()
- ranker.py：rank_products() 基础排序（BM25/向量单路检索的回退排序）
"""

from __future__ import annotations

from copy import deepcopy

from .models import HardConstraints, Product, RankedProduct, RetrievalPlan
from .ranker import rank_products


class RelaxationPolicy:
    """定义自适应检索的约束放松策略。

    当严格检索无法返回足够候选商品时，按预定顺序逐步放宽约束，
    以在召回率（能找到多少相关商品）和精确度（结果有多匹配用户意图）之间取得平衡。

    relaxation_order 中的每一步代表解除一类约束：
    - "soft_preferences"：丢弃所有软偏好（拍照/送礼/轻薄等），只保留硬约束
    - "price_range"：去掉价格上下限（硬约束级别放松）
    - "category_fallback"：去掉子品类限制，回退到父类

    min_candidates=5：至少需要 5 个候选才停止放松。太少则 LLM 选择余地不足。
    max_rounds=3：最多跑 3 轮（含第 0 轮严格检索），防止无限循环。
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

    可选注入 hybrid_retriever：如果传入，第一轮优先走 hybrid 融合检索；
    失败或返回空时回退到 base retriever 的渐进放松循环。
    """

    def __init__(
        self,
        retriever,
        policy: RelaxationPolicy | None = None,
        metrics=None,
        *,
        hybrid_retriever=None,
        reranker=None,
    ):
        self.retriever = retriever
        self.policy = policy or RelaxationPolicy()
        self.metrics = metrics
        self.last_evidence_by_product: dict[str, list[str]] = {}
        self.hybrid_retriever = hybrid_retriever
        self.reranker = reranker

    async def search_async(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        """Async path: hybrid retrieval → optional reranker → fallback to sync search if hybrid fails."""
        self.last_evidence_by_product = {}
        if self.hybrid_retriever is not None:
            try:
                from .rag.types import format_chunk_evidence

                if hasattr(self.hybrid_retriever, "search_with_evidence"):
                    hybrid_results = self.hybrid_retriever.search_with_evidence(plan, top_k=top_k)
                else:
                    raw_results = self.hybrid_retriever.search(plan, top_k=top_k)
                    if raw_results:
                        if self.metrics is not None:
                            self.metrics.increment("retrieval.hybrid.success")
                        return raw_results
                    hybrid_results = []
                if hybrid_results:
                    if self.reranker is not None:
                        from .rag.reranker_scenarios import detect_pre_scenario
                        pre_scenario = detect_pre_scenario(plan)
                        hybrid_results = await self.reranker.rerank(
                            plan.retrieval_query or "",
                            hybrid_results,
                            top_k=top_k,
                            scenario=pre_scenario,
                        )
                    self.last_evidence_by_product = {
                        result.product.product_id: [
                            text
                            for text in (format_chunk_evidence(chunk) for chunk in result.evidence_chunks)
                            if text
                        ]
                        for result in hybrid_results
                    }
                    if self.metrics is not None:
                        self.metrics.increment("retrieval.hybrid.success")
                    return [(result.product, result.score) for result in hybrid_results]
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
            except Exception:
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
                pass

        # Fallback: identical sync logic from search()
        return self.search(plan, top_k=top_k)

    def search(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        """Sync path: hybrid retrieval without reranker. Kept for backward compat;
        async path (search_async) is the canonical entry for reranker usage."""
        self.last_evidence_by_product = {}
        if self.hybrid_retriever is not None:
            try:
                from .rag.types import format_chunk_evidence

                if hasattr(self.hybrid_retriever, "search_with_evidence"):
                    hybrid_results = self.hybrid_retriever.search_with_evidence(plan, top_k=top_k)
                else:
                    raw_results = self.hybrid_retriever.search(plan, top_k=top_k)
                    if raw_results:
                        if self.metrics is not None:
                            self.metrics.increment("retrieval.hybrid.success")
                        return raw_results
                    hybrid_results = []
                if hybrid_results:
                    self.last_evidence_by_product = {
                        result.product.product_id: [
                            text
                            for text in (format_chunk_evidence(chunk) for chunk in result.evidence_chunks)
                            if text
                        ]
                        for result in hybrid_results
                    }
                    if self.metrics is not None:
                        self.metrics.increment("retrieval.hybrid.success")
                    return [(result.product, result.score) for result in hybrid_results]
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
            except Exception:
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
                # retrieval_error: preserve fallback to base rank_products below
                pass

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
        """根据当前轮次构建放松后的检索计划。

        round_index=0：返回原始 plan（不做任何放松）。
        round_index=1：应用 relaxation_order[0]，即去掉 soft_preferences。
        round_index=2：应用 relaxation_order[0:2]，即 soft_preferences + price_range。
        以此类推，最多到 max_rounds。

        ===== 查询重建策略 =====
        放松后原 retrieval_query 可能不再适用（比如原 query 包含了已去掉的偏好词），
        因此重新构建查询字符串，优先级：
        1. hard.sub_category（最精确）→ 2. hard.category → 3. include_brands → 4. soft 剩余值
        全部为空时回退到原 query，保证不会空查询。

        ===== 每步放松对 HardConstraints 的具体影响 =====
        - soft_preferences：清空 soft 字典（不碰 hard）
        - price_range：hard.price_min/price_max 置 None
        - category_fallback：hard.sub_category 置 None（保留 hard.category）
        """
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
