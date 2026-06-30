"""跨轮一致性追踪器 — 确保 LLM 回复与历史声明一致。"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models import SessionContext, ClaimRecord, FactContext

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyResult:
    is_consistent: bool = True
    focus_drift_detected: bool = False
    blocked_reason: str | None = None


class ConsistencyTracker:
    """跨轮一致性校验（纯规则，不调 LLM）。

    3 条规则:
    Rule 1 (Denial Cache): 已声明"不存在"的查询 → 后续检索时注入 denied_queries
    Rule 2 (Price Consistency): 同一 product_id 价格与 FactContext 一致（由 AnchorValidator 保证）
    Rule 3 (Focus Drift): confirmed_product_id 不在新推荐中 → 标记漂移
    """

    def check_before_output(
        self,
        session_ctx: SessionContext,
        ranked_product_ids: list[str],
        fact_ctx: FactContext,
    ) -> ConsistencyResult:
        cs = session_ctx.state.consistency

        # Rule 3: Focus drift
        if cs.confirmed_product_id and cs.confirmed_product_id not in ranked_product_ids:
            return ConsistencyResult(
                is_consistent=False,
                focus_drift_detected=True,
                blocked_reason=(
                    f"用户已确认关注 {cs.confirmed_product_id}，"
                    f"但新推荐未包含该商品"
                ),
            )

        return ConsistencyResult(is_consistent=True)

    def get_denied_queries(self, session_ctx: SessionContext) -> list[str]:
        """获取当前 session 的 denial cache。"""
        return list(session_ctx.state.consistency.denied_product_queries)

    def record_denial(self, ctx: SessionContext, query: str, turn: int) -> None:
        """记录一条「商品不存在」的声明。"""
        cs = ctx.state.consistency
        if query not in cs.denied_product_queries:
            cs.denied_product_queries.append(query)
        cs.claims.append(ClaimRecord(
            turn=turn, product_id="", claim_type="not_exists",
            claim_value=f"查询「{query}」不在商品库中",
        ))

    def record_claim(self, ctx: SessionContext, product_id: str,
                     claim_type: str, claim_value: str, turn: int) -> None:
        """记录一条商品相关的声明。"""
        ctx.state.consistency.claims.append(ClaimRecord(
            turn=turn, product_id=product_id,
            claim_type=claim_type, claim_value=claim_value,
        ))

    def set_confirmed_product(self, ctx: SessionContext, product_id: str) -> None:
        """设置用户确认的目标商品。"""
        ctx.state.consistency.confirmed_product_id = product_id
