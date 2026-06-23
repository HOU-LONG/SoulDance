from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvalExpectation(BaseModel):
    min_product_items: int = 0
    expected_product_ids: list[str] = Field(default_factory=list)
    gold_product_ids: list[str] = Field(default_factory=list)
    gold_primary_ids: list[str] = Field(default_factory=list)
    forbidden_product_ids: list[str] = Field(default_factory=list)
    forbid_terms: list[str] = Field(default_factory=list)
    price_max: float | None = None
    event_types: list[str] = Field(default_factory=list)
    expected_gate: str | None = None
    require_cart_success: bool = False
    require_order_completed: bool = False


class EvalScenario(BaseModel):
    id: str
    message: str
    session_id: str
    type: str = "user_message"
    expect: EvalExpectation = Field(default_factory=EvalExpectation)


class EvalScenarioResult(BaseModel):
    id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    event_count: int = 0
    product_ids: list[str] = Field(default_factory=list)
    planner_ok: bool | None = None
    clarification_blocked: bool = False
    retrieval_query: str | None = None
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    gold_ids: list[str] = Field(default_factory=list)
    gold_primary_ids: list[str] = Field(default_factory=list)
    pre_filter_top20: list[str] = Field(default_factory=list)
    post_filter_top20: list[str] = Field(default_factory=list)
    final_top5: list[str] = Field(default_factory=list)
    miss_reason: str | None = None


class EvalAttributionSummary(BaseModel):
    attribution_n: int = 0
    planner_pass_rate: float | None = None
    clarification_block_rate: float | None = None
    pre_filter_recall_at_20: float | None = None
    post_filter_recall_at_20: float | None = None
    final_recall_at_5: float | None = None
    primary_hit_at_1: float | None = None


class EvalReport(BaseModel):
    total: int
    passed: int
    failed: int
    results: list[EvalScenarioResult]
    attribution_summary: EvalAttributionSummary | None = None
