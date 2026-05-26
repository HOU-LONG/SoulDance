from __future__ import annotations

from pydantic import BaseModel, Field


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
    price_max: float | None = None
    exclude_terms: list[str] = Field(default_factory=list)
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


class CartActionRequest(BaseModel):
    session_id: str
    product_id: str | None = None
    quantity: int = 1


class ProductCard(BaseModel):
    product_id: str
    name: str
    brand: str
    category: str
    sub_category: str
    price: float
    main_image_url: str
    tags: list[str]
    reason: str
    evidence: list[str] = Field(default_factory=list)


class SessionContext(BaseModel):
    session_id: str
    last_plan: RetrievalPlan | None = None
    last_product_ids: list[str] = Field(default_factory=list)
    focus_product_id: str | None = None
    focus_history: list[str] = Field(default_factory=list)
    global_profile: dict[str, object] = Field(default_factory=dict)
    active_focus: dict[str, object] = Field(default_factory=dict)
    last_recommendations: list[dict[str, object]] = Field(default_factory=list)
    negative_feedback: list[str] = Field(default_factory=list)
    recent_cart_product_id: str | None = None
