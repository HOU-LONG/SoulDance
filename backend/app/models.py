from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class SKU(BaseModel):
    sku_id: str
    properties: dict[str, str] = Field(default_factory=dict)
    price: float


class Product(BaseModel):
    product_id: str
    title: str
    brand: str
    category: str
    sub_category: str
    price: float
    image_path: str
    skus: list[SKU] = Field(default_factory=list)
    marketing_description: str = ""
    faqs: list[dict[str, str]] = Field(default_factory=list)
    reviews: list[dict[str, object]] = Field(default_factory=list)
    chunk: str = ""
    search_text: str = ""
    brand_region: str = "未知"
    extracted_terms: list[str] = Field(default_factory=list)
    review_rating: float = 0.0


class HardConstraints(BaseModel):
    category: str | None = None
    sub_category: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    exclude_terms: list[str] = Field(default_factory=list)
    include_brands: list[str] = Field(default_factory=list)
    exclude_brands: list[str] = Field(default_factory=list)
    exclude_brand_regions: list[str] = Field(default_factory=list)
    in_stock_only: bool = True


class RetrievalPlan(BaseModel):
    intent: str = "recommend_product"
    retrieval_mode: str = "single"
    category: str | None = None
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    soft_preferences: dict[str, str] = Field(default_factory=dict)
    retrieval_query: str
    need_clarification: bool = False
    clarification_question: str | None = None


class ConstraintPatch(BaseModel):
    category: str | None = None
    sub_category: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    exclude_terms: list[str] = Field(default_factory=list)
    include_brands: list[str] = Field(default_factory=list)
    exclude_brands: list[str] = Field(default_factory=list)
    exclude_brand_regions: list[str] = Field(default_factory=list)
    soft_preferences: dict[str, str] = Field(default_factory=dict)


class ConstraintEdits(BaseModel):
    add: ConstraintPatch = Field(default_factory=ConstraintPatch)
    remove: ConstraintPatch = Field(default_factory=ConstraintPatch)
    relax: list[str] = Field(default_factory=list)


class ProductReference(BaseModel):
    reference: str = "focus_product"
    selection_strategy: str = "primary"
    index: int | None = None
    product_id: str | None = None


class CartOperation(BaseModel):
    action: str = "add_to_cart"
    target: ProductReference = Field(default_factory=ProductReference)
    quantity: int = 1


class QueryIntent(BaseModel):
    category: str | None = None
    sub_category: str | None = None
    soft_preferences: dict[str, str] = Field(default_factory=dict)
    query_terms: list[str] = Field(default_factory=list)


class SemanticFrame(BaseModel):
    intent: str = "recommend_product"
    confidence: float = 1.0
    constraint_edits: ConstraintEdits = Field(default_factory=ConstraintEdits)
    cart_operation: CartOperation | None = None
    target: ProductReference | None = None
    references: list[ProductReference] = Field(default_factory=list)
    query_intent: QueryIntent = Field(default_factory=QueryIntent)
    response_goal: str | None = None
    clarification_question: str | None = None


ShoppingIntentIR = SemanticFrame


class ExecutionPlan(BaseModel):
    execution_type: str
    retrieval_plan: RetrievalPlan | None = None
    reference_bindings: dict[str, str | None] = Field(default_factory=dict)
    stream_policy: str = "cards_before_explanation"
    clarification_question: str | None = None


class UserProfile(BaseModel):
    stable_preferences: dict[str, object] = Field(default_factory=dict)
    negative_preferences: list[str] = Field(default_factory=list)


class DialogState(BaseModel):
    last_intent: str | None = None
    last_user_message: str | None = None
    turn_index: int = 0


class ActiveFocusState(BaseModel):
    type: str | None = None
    product_id: str | None = None
    source: str | None = None


class RecommendationMemoryItem(BaseModel):
    index: int
    product_id: str
    role: str = "alternative"
    score: float | None = None


class RecommendationMemory(BaseModel):
    last_set_id: str | None = None
    items: list[RecommendationMemoryItem] = Field(default_factory=list)


class PendingClarification(BaseModel):
    category: str | None = None
    sub_category: str | None = None
    question: str | None = None
    created_turn: int = 0


class CurrentTaskState(BaseModel):
    task_id: str | None = None
    category: str | None = None
    sub_category: str | None = None


class ConstraintState(BaseModel):
    hard: HardConstraints = Field(default_factory=HardConstraints)
    soft: dict[str, str] = Field(default_factory=dict)
    source_turns: list[dict[str, Any]] = Field(default_factory=list)


class CartMemory(BaseModel):
    recent_product_id: str | None = None


class PendingRecovery(BaseModel):
    recovery_id: str
    failed_query: str
    failed_object: str | None = None
    reason: str
    options: list[dict[str, Any]] = Field(default_factory=list)


class ContextEvent(BaseModel):
    event_id: str
    turn_index: int
    user_message: str
    assistant_intent: str
    result_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TraceState(BaseModel):
    last_ir: dict[str, Any] | None = None
    last_execution_plan: dict[str, Any] | None = None
    decision_log: list[dict[str, Any]] = Field(default_factory=list)


class SessionState(BaseModel):
    session_id: str = ""
    user_profile: UserProfile = Field(default_factory=UserProfile)
    dialog_state: DialogState = Field(default_factory=DialogState)
    active_focus: ActiveFocusState = Field(default_factory=ActiveFocusState)
    recommendation_memory: RecommendationMemory = Field(default_factory=RecommendationMemory)
    pending_clarification: PendingClarification | None = None
    current_task: CurrentTaskState = Field(default_factory=CurrentTaskState)
    constraint_state: ConstraintState = Field(default_factory=ConstraintState)
    cart_memory: CartMemory = Field(default_factory=CartMemory)
    pending_recovery: PendingRecovery | None = None
    context_events: list[ContextEvent] = Field(default_factory=list)
    trace: TraceState = Field(default_factory=TraceState)


class RankedProduct(BaseModel):
    product: Product
    score: float
    tier: int
    reason: str
    evidence: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    type: str
    session_id: str
    message: str = ""
    input_type: str = "text"
    focus_product_id: str | None = None
    tts_enabled: bool = False
    voice: str | None = None
    action: str | None = None
    product_id: str | None = None
    quantity: int = 1

    @field_validator("input_type")
    @classmethod
    def _validate_input_type(cls, v: str) -> str:
        allowed = {"text", "voice"}
        if v not in allowed:
            raise ValueError(f"input_type must be one of {allowed}")
        return v


class STTResponse(BaseModel):
    text: str
    is_final: bool = True
    confidence: float | None = None
    language: str | None = "zh"


class CartActionRequest(BaseModel):
    session_id: str
    product_id: str | None = None
    quantity: int = 1


class OrderActionRequest(BaseModel):
    order_id: str
    address_id: str | None = None


class ProductCard(BaseModel):
    product_id: str
    name: str
    brand: str
    category: str
    sub_category: str
    price: float
    main_image_url: str
    image_url: str = ""          # Android 端兼容字段
    tags: list[str] = Field(default_factory=list)
    reason: str = ""
    is_primary: bool = False     # Android 端主推标记
    derived_attributes: dict[str, Any] = Field(default_factory=dict)
    positive_feedback_summary: list[str] = Field(default_factory=list)
    negative_feedback_summary: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)


class SessionContext(BaseModel):
    session_id: str
    state: SessionState = Field(default_factory=SessionState)
    last_plan: RetrievalPlan | None = None
    last_product_ids: list[str] = Field(default_factory=list)
    focus_product_id: str | None = None
    focus_history: list[str] = Field(default_factory=list)
    global_profile: dict[str, object] = Field(default_factory=dict)
    active_focus: dict[str, object] = Field(default_factory=dict)
    last_recommendations: list[dict[str, object]] = Field(default_factory=list)
    negative_feedback: list[str] = Field(default_factory=list)
    recent_cart_product_id: str | None = None
    schema_version: int = 1
    last_activity_at: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.state.session_id:
            self.state.session_id = self.session_id


class Address(BaseModel):
    address_id: str
    name: str
    phone: str
    province: str
    city: str
    detail: str = ""
    is_default: bool = False


class OrderItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int
    amount: float


class Order(BaseModel):
    order_id: str
    session_id: str
    status: str
    items: list[OrderItem] = Field(default_factory=list)
    total_amount: float = 0.0
    address: Address | None = None


class DimensionScore(BaseModel):
    dimension: str
    winner_product_id: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    explanation: str = ""


class ComparisonResult(BaseModel):
    product_ids: list[str]
    dimensions: list[DimensionScore]
    overall_winner: str | None = None
    overall_reason: str = ""
    scenario_recommendations: dict[str, str] = Field(default_factory=dict)


# ---------- 反馈闭环模型 ----------

class FeedbackEvent(BaseModel):
    """单条反馈事件（隐式行为 + 显式评价）"""
    session_id: str
    signal_type: str = "explicit_rating"
    # explicit_rating | quick_action | add_to_cart | followup | checkout | clarification_answer
    product_id: str | None = None
    rating: int | None = None               # 1=👍, -1=👎
    action_label: str | None = None          # "更便宜" / "不要Apple" / "更适合户外"
    context: dict = Field(default_factory=dict)  # plan / candidates 快照
    timestamp: str = ""


class FeedbackSignal(BaseModel):
    """单次聚合后的反馈信号权重"""
    product_boosts: dict[str, float] = Field(default_factory=dict)
    brand_weights: dict[str, float] = Field(default_factory=dict)
    price_preference: str | None = None       # "更便宜" | "更贵"
    category_affinity: dict[str, float] = Field(default_factory=dict)
    preference_tags: list[str] = Field(default_factory=list)


class UserFeedbackProfile(BaseModel):
    """跨 session 持久化的用户偏好画像"""
    user_id: str
    total_ratings: int = 0
    liked_product_ids: list[str] = Field(default_factory=list)
    disliked_product_ids: list[str] = Field(default_factory=list)
    signals: list[FeedbackSignal] = Field(default_factory=list)  # 最近 N 轮
    updated_at: str = ""
