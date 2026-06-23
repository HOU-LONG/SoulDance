"""评测 DSL 模型。

为答辩级场景库（20 类）准备扩展能力：
- EvalStep 支持多轮对话：一个 scenario 可以包含若干步，每步独立断言
- EvalExpectation 扩展断言字段：品牌过滤 / 价格区间 / clarification / no_match /
  comparison / order_status / cart_quantity / error_kind / 解释文本禁用词等
- 占位符通过 bind 字段在 step 间传递（${var_name} 形式）

向后兼容：旧 scenario 只用顶层 message + expect 仍然能跑（自动包成单 step）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EvalExpectation(BaseModel):
    # ---- 基础断言（旧版兼容） ----
    min_product_items: int = 0
    expected_product_ids: list[str] = Field(default_factory=list)
    forbidden_product_ids: list[str] = Field(default_factory=list)
    forbid_terms: list[str] = Field(default_factory=list)
    price_max: float | None = None
    event_types: list[str] = Field(default_factory=list)
    require_cart_success: bool = False
    require_order_completed: bool = False

    # ---- Phase 2 扩展字段 ----
    price_min: float | None = None
    expected_brands: list[str] = Field(default_factory=list)
    forbidden_brands: list[str] = Field(default_factory=list)
    expect_clarification: bool = False
    expect_no_match: bool = False
    expect_comparison: bool = False
    expect_order_status: str | None = None
    expect_cart_quantity: dict[str, int] = Field(default_factory=dict)
    expect_error_kind: str | None = None
    expect_product_ids_subset_of: list[str] = Field(default_factory=list)
    forbidden_terms_in_explanation: list[str] = Field(default_factory=list)
    expected_focus_product: str | None = None


class EvalStep(BaseModel):
    """单步：一次用户消息或一次工具调用 + 局部断言 + 可选变量绑定。

    action 决定 runner 如何与系统交互：
    - user_message: WebSocket 推 user_message
    - cart_action: WebSocket 推 cart_action（payload 提供 product_id/action/quantity）
    - order_action: 走 /api/order/* HTTP 接口（payload.kind=initiate/select_address/confirm）
    - websocket_disconnect: 主动关闭并立即重连，验证 session 状态恢复
    - wait: 不发消息，仅给 runner 时间清理事件流（用于占位）

    bind: 把本步执行结果中的某个值（如 product_ids[0]）存入 scenario_vars，
    后续 step 的 expect 字段可以用 ${var_name} 引用。
    """

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
    # 顶层 message / expect / type 是单步快捷写法，runner 自动包成 steps[0]
    message: str = ""
    type: str = "user_message"
    expect: EvalExpectation = Field(default_factory=EvalExpectation)
    steps: list[EvalStep] = Field(default_factory=list)
    # fault: 在 scenario 开始前注入指定故障（llm_timeout / stt_unavailable / ...）
    fault: str | None = None
    # tags: 自由标签，便于 ablation 脚本筛选（如 "recommend" / "edge"）
    tags: list[str] = Field(default_factory=list)
    # golden_id: 指向 data/eval/golden_products.json 中的 key，用于 ablation 算 Recall/NDCG。
    # 未设置时 ablation 跳过 IR 指标计算（如多轮 / cart / failure 类场景）。
    golden_id: str | None = None

    @model_validator(mode="after")
    def _expand_legacy_shortcut(self) -> "EvalScenario":
        """旧 scenario 只填顶层 message / type / expect 时自动展开为 steps[0]。"""
        if self.steps:
            return self
        # 旧 cart_action / order_flow 也保留为 steps 的特殊 action，
        # 真正的执行逻辑由 runner 内部映射
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
    """单步执行结果。"""

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
    # Phase 2 扩展：分步结果 + 聚合指标
    steps: list[EvalStepResult] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class EvalReport(BaseModel):
    total: int
    passed: int
    failed: int
    results: list[EvalScenarioResult]
