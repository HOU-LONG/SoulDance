"""
RAG 类型系统 — 检索结果的数据结构、chunk 权重策略与证据格式化。

===== 领域概念扫盲 =====

"RAG"（Retrieval-Augmented Generation，检索增强生成）：
一种 AI 架构模式，先"检索"相关信息，再把信息喂给 LLM 生成答案。
就像考试时先翻书找答案，再凭记忆回答——翻书=检索，回答=生成。
SoulDance 的 RAG 分为两层：
  1. HybridRetriever（混合检索）：同时跑 BM25（关键词匹配）+ 向量检索（语义匹配），
     再通过 RRF/weighted 融合两路结果
  2. Reranker（重排）：对融合结果做精细排序，CrossEncoder 为主，LLM 为兜底

"Chunk"（检索块/文本块）：
把每个商品的信息（描述、规格、评价摘要等）切分成小块文本，每个块独立索引和检索。
不同块类型有不同的业务权重——比如规格参数的 chunks 比营销文案的 chunks 更可信。

"canonical_chunk_type"（规范 chunk 类型）：
原始数据中 chunk_type 可能不一致（如 "review" vs "review_summary"），
通过 canonical_chunk_type() 统一映射到标准名称，保证权重策略的一致性。

"chunk_relevance_weight"（chunk 相关性权重）：
检索时对不同类型的 chunk 施加不同的分数乘数，体现业务判断：
- 规格参数（specification）最可信，权重 1.25
- 评价摘要（review_summary）在用户主动问评价时权重升到 1.15，否则降到 0.65
- 营销文案（marketing_copy）权重只有 0.55，因为商家自夸不可全信
这些权重是业务经验值，可通过 A/B 实验 calibration。

===== 数据流向 =====

数据库中的 chunk 行 → chunk_result_from_orm() → ChunkSearchResult
    → chunk_relevance_weight()（对 score 加权）
    → 合并到 ProductRetrievalResult.evidence_chunks
    → format_chunk_evidence()（格式化为 LLM 可读文本）
    → 注入 LLM system/user prompt

===== 与其它模块协作 =====

- chunking.py：canonical_chunk_type 映射
- fusion.py / vector_search.py：检索结果返回 ChunkSearchResult
- agent.py：format_chunk_evidence 用于构建 LLM 上下文
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import Product
from .chunking import canonical_chunk_type

# ── 评价意图检测 ─────────────────────────────────────────────
# 用户消息中包含这些词时，视为主动在问"这个商品评价怎么样"，
# 此时 review_summary chunks 的权重会从 0.65 提升到 1.15。
_REVIEW_INTENT_PATTERN = re.compile(
    "|".join([
        "review",
        "feedback",
        "comment",
        "\\u8bc4\\u4ef7",    # 评价
        "\\u8bc4\\u8bba",    # 评论
        "\\u53e3\\u7891",    # 口碑
        "\\u5dee\\u8bc4",    # 差评
        "\\u53cd\\u9988",    # 反馈
        "\\u4e70\\u5bb6",    # 买家
        "\\u7528\\u6237",    # 用户
    ]),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChunkSearchResult:
    """检索返回的单个文本块（chunk）结果。

    每个 chunk 是商品信息的原子单元，包含内容、类型、来源、可信度标记等。
    frozen=True 确保一旦创建不可修改，避免下游意外改动影响排序。

    score 含义：由检索引擎（BM25 或向量）为该 chunk 分配的原始相关性分数，
    分数越高表示 chunk 内容与用户查询越相关。后续会经过 chunk_relevance_weight()
    加权修正，再做 product 级别的聚合排序。
    """
    product_id: str
    chunk_id: str
    sku_id: str | None
    category_id: str
    sub_category: str
    chunk_type: str
    source_type: str
    trust_level: str
    document_version: int
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def excerpt(self) -> str:
        return self.content[:160]


@dataclass(frozen=True)
class ProductRetrievalResult:
    product: Product
    score: float
    evidence_chunks: list[ChunkSearchResult] = field(default_factory=list)


def chunk_result_from_orm(chunk, score: float) -> ChunkSearchResult:
    """将数据库 ORM 行转换为 ChunkSearchResult 领域对象。

    这是 DB 层与 RAG 层之间的适配器——数据库返回的 chunk 行通过
    canonical_chunk_type() 规范化类型名后，包装为业务层可用的 frozon dataclass。
    """
    return ChunkSearchResult(
        product_id=chunk.product_id,
        chunk_id=chunk.chunk_id,
        sku_id=chunk.sku_id,
        category_id=chunk.category_id,
        sub_category=chunk.sub_category,
        chunk_type=canonical_chunk_type(chunk.chunk_type),
        source_type=chunk.source_type,
        trust_level=chunk.trust_level,
        document_version=chunk.document_version,
        content=chunk.content or "",
        score=float(score),
        metadata=dict(chunk.metadata_json or {}),
    )


def chunk_relevance_weight(
    query: str,
    chunk_type: str,
    source_type: str,
    trust_level: str,
) -> float:
    """根据 chunk 的类型、来源、可信度，返回对原始检索分数的加权乘数。

    ===== 权重设计依据 =====

    | 条件                     | 权重   | 依据                                    |
    |--------------------------|--------|-----------------------------------------|
    | specification（规格参数）  | 1.25   | 客观数据，不包含主观评价，最可信            |
    | sku（SKU 信息）           | 1.20   | 具体的款式/型号信息，对精确匹配很有用        |
    | official_description     | 1.05   | 官方描述，可靠但有一定美化                  |
    | faq（常见问题）           | 1.00   | 问答形式，对澄清类查询有帮助               |
    | review_summary + 评价意图 | 1.15   | 用户主动问评价时，评价摘要权重提升          |
    | review_summary（常规）    | 0.65   | 非评价意图时降权，避免过度依赖主观评价       |
    | marketing_copy           | 0.55   | 营销文案，商家自夸成分大，可信度最低        |
    | 其它（默认）              | 0.80   | 未归类 chunk 的保守权重                    |

    ===== 调整建议 =====
    这些权重是业务经验值（heuristics），非机器学习优化结果。
    如果发现检索结果偏差（比如营销文案排太前面），可以通过 A/B 实验
    验证调参效果。参数化到 config 是未来的改进方向。
    """
    canonical_type = canonical_chunk_type(chunk_type)
    review_intent = bool(_REVIEW_INTENT_PATTERN.search(query or ""))
    if canonical_type == "review_summary":
        return 1.15 if review_intent else 0.65
    if source_type == "marketing_copy" or trust_level == "marketing":
        return 0.55
    weights = {
        "specification": 1.25,
        "sku": 1.2,
        "official_description": 1.05,
        "faq": 1.0,
    }
    return weights.get(canonical_type, 0.8)


def format_chunk_evidence(chunk: ChunkSearchResult) -> str:
    """将 chunk 格式化为一行 LLM 可读的证据文本。

    输出格式：[chunk类型/来源/版本号] 内容前160字

    这个函数是 RAG 管线的最后一步——检索到的 chunk 经加权排序后，
    通过此函数转换为 LLM prompt 中的"证据引用"，帮助 LLM 做出有据可依的推荐。
    """
    text = chunk.excerpt.strip()
    if not text:
        return ""
    return f"[{chunk.chunk_type}/{chunk.source_type}/v{chunk.document_version}] {text}"
