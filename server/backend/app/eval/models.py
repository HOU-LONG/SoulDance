"""Evaluation DSL models.

Supports legacy single-message scenarios, multi-step scenarios, and attribution diagnostics.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EvalExpectation(BaseModel):
    # ---- Legacy-compatible assertions ----
    min_product_items: int = 0
    expected_product_ids: list[str] = Field(default_factory=list)
    gold_product_ids: list[str] = Field(default_factory=list)
    gold_primary_ids: list[str] = Field(default_factory=list)
    forbidden_product_ids: list[str] = Field(default_factory=list)
    forbid_terms: list[str] = Field(default_factory=list)
    price_max: float | None = None
    price_min: float | None = None
    event_types: list[str] = Field(default_factory=list)
    expected_brands: list[str] = Field(default_factory=list)
    forbidden_brands: list[str] = Field(default_factory=list)
    expect_clarification: bool = False
    expect_product_ids_subset_of: list[str] = Field(default_factory=list)
    expected_gate: str | None = None
    require_cart_success: bool = False
    require_order_completed: bool = False

    # ---- Phase 2 assertions ----
    expect_no_match: bool = False
    expect_comparison: bool = False
    expect_order_status: str | None = None
    expect_cart_quantity: dict[str, int] = Field(default_factory=dict)
    expect_error_kind: str | None = None
    forbidden_terms_in_explanation: list[str] = Field(default_factory=list)
    expected_focus_product: str | None = None


class EvalStep(BaseModel):
    """One scenario step with an action, assertions, and optional bindings."""

    message: str = ""
    action: Literal[
        "user_message",
        "cart_action",
        "order_action",
        "websocket_disconnect",
        "wait",
    ] = "user_message"
    payload: dict[str, Any] = Field(default_factory=dict)
    expect: EvalExpectation = Field(default_factory=EvalExpectation)
    bind: dict[str, str] = Field(default_factory=dict)


class EvalScenario(BaseModel):
    id: str
    session_id: str
    # Top-level message / expect / type is expanded into steps[0].
    message: str = ""
    type: str = "user_message"
    expect: EvalExpectation = Field(default_factory=EvalExpectation)
    steps: list[EvalStep] = Field(default_factory=list)
    # Optional fault injection before a scenario starts.
    fault: str | None = None
    # Free-form tags for filtering and ablation runs.
    tags: list[str] = Field(default_factory=list)
    # golden_id points to data/eval/golden_products.json for Recall/NDCG.
    # Scenarios without golden_id are skipped for IR metrics.
    golden_id: str | None = None

    @model_validator(mode="after")
    def _expand_legacy_shortcut(self) -> "EvalScenario":
        """Expand legacy message / type / expect fields into steps[0]."""
        if self.steps:
            return self
        if self.type == "cart_action":
            action = "cart_action"
        elif self.type == "order_flow":
            action = "order_action"
        else:
            action = "user_message"
        self.steps = [
            EvalStep(
                message=self.message,
                action=action,
                expect=self.expect,
                payload={"legacy_type": self.type},
            )
        ]
        return self


class EvalStepResult(BaseModel):
    """Per-step execution result."""

    step_index: int
    passed: bool
    failures: list[str] = Field(default_factory=list)
    event_count: int = 0
    product_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class EvalScenarioResult(BaseModel):
    id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    event_count: int = 0
    product_ids: list[str] = Field(default_factory=list)
    # Phase 2 step results and aggregate metrics.
    steps: list[EvalStepResult] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    # attribution diagnostics
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
