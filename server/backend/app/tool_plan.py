"""LLM Planner 输出的结构化工具调度方案。

LLM 在 `tool_planner.txt` 系统提示约束下输出 ToolPlan JSON，agent 入口按 tool 字段
分发到具体 tool。设计原则：

- LLM 只负责"调什么工具 / 用户的关键参数是什么"，不直接生成回复
- LLM 不选 product_id（防编造）—— 商品识别由 ProductMatcher / retriever 负责
- 字段命名贴近用户原话："target_product_query" 直接放用户提到的商品名片段
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ToolName = Literal[
    "recommend_product",
    "product_analysis",
    "compare_products",
    "cart_operation",
    "scenario_bundle",
    "product_followup",
    "chitchat",
]


class ToolPlanArgs(BaseModel):
    """所有 tool 共享的参数池——按 tool 字段决定哪几项被使用。

    LLM 只填它能可靠抽取的字段；其它 tool 默认行为兜底。
    """

    # 商品识别（recommend / product_analysis / compare / followup 共用）
    target_product_query: str | None = None
    """用户原话中提到的具体商品名片段，例如 '华为 Pura 70 Pro' / '小棕瓶' / '雀巢咖啡'。
    后端用 ProductMatcher 做模糊匹配，不要让 LLM 直接给 product_id。"""

    category_hint: str | None = None
    """用户暗示的类目或子类目，例如 '手机' / '防晒霜' / '咖啡'。"""

    compare_targets: list[str] = Field(default_factory=list)
    """对比场景下的多个商品名（模糊也行，每个都跑 matcher）。"""

    # 约束（recommend / product_followup 用）
    price_max: float | None = None
    price_min: float | None = None
    include_brands: list[str] = Field(default_factory=list)
    exclude_brands: list[str] = Field(default_factory=list)
    soft_preferences: dict[str, str] = Field(default_factory=dict)
    """任意 key: value 软偏好，例如 {'priority': '拍照'} / {'skin_type': '油皮'}。"""

    # 分析/追问场景
    analysis_aspect: str | None = None
    """关心的属性维度：'price' / 'specs' / 'review' / 'compare' / 'general'。"""

    followup_kind: str | None = None
    """追问类型：'explain'(说明当前商品) / 'cheaper'(换更便宜) / 'more_expensive' /
    'exclude_brand'(换品牌) / 'specs'(问参数) / 'price'(问价格)。"""

    # 购物车场景
    cart_action: str | None = None
    """'add' / 'update_quantity' / 'remove' / 'clear' / 'checkout' / 'get_cart'。"""
    cart_quantity: int = 1
    cart_target: str | None = None
    """加购目标的引用：'focus_product' / 'last_recommendation' / 具体商品名片段（走 matcher）。"""


class ToolPlan(BaseModel):
    """Planner 输出的完整结构。"""

    tool: ToolName
    args: ToolPlanArgs = Field(default_factory=ToolPlanArgs)
    confidence: float = 1.0
    """0~1，LLM 对此次决策的自信程度。<0.4 时调用方可以二次确认或走兜底。"""
