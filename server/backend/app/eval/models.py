from __future__ import annotations

from pydantic import BaseModel, Field


class EvalExpectation(BaseModel):
    min_product_items: int = 0
    expected_product_ids: list[str] = Field(default_factory=list)
    forbidden_product_ids: list[str] = Field(default_factory=list)
    forbid_terms: list[str] = Field(default_factory=list)
    price_max: float | None = None
    event_types: list[str] = Field(default_factory=list)
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


class EvalReport(BaseModel):
    total: int
    passed: int
    failed: int
    results: list[EvalScenarioResult]
