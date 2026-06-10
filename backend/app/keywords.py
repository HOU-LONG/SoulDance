"""轻量确定性中文 marker。

本模块只放稳定、低风险、可被规则层复用的词表。
不要在这里放复杂语义解析、动态 prompt、长 UI 文案或领域推理逻辑。
"""

PRODUCT_REQUEST_MARKERS = ("推荐", "找", "买", "想要", "有没有")
EXPLAIN_FOCUS_MARKERS = ("刚刚那个是什么", "刚才那个是什么", "为什么推荐", "介绍一下", "这个是什么")
CHEAPER_ALTERNATIVE_MARKERS = ("更便宜", "便宜点", "便宜的", "价格低")
MORE_EXPENSIVE_ALTERNATIVE_MARKERS = ("更贵", "贵一点", "高端", "高价位", "价位高")
DIFFERENT_BRAND_MARKERS = ("不要这个品牌", "换个品牌", "别的品牌", "不要这个牌子")
