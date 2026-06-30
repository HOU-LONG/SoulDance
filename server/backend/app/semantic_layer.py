"""
语义解析层 — 将用户自然语言消息转换为结构化的语义帧（SemanticFrame）。

===== 领域概念扫盲 =====

"语义帧"（SemanticFrame）：
用户的原始消息（如"想给女朋友买一款 200 元以内的保湿精华"）经解析后，
变成结构化的 {intent, constraint_edits, cart_operation, ...} 字典。
后续模块（StateReducer、Agent、Retriever）只消费语义帧，不再看原始文本。
这就像编译器把源代码转成 AST——后续流程不再依赖原始字符串。

"意图分类"（Intent Classification）：
判断用户这句话想干什么——是推荐商品（recommend_product）、操作购物车（cart_operation）、
比较商品（compare_products）、闲聊（small_talk），还是表达不清需要澄清（clarification）。

"混合解析：LLM + 规则"：
- SemanticParser.parse() 优先走 LLM 解析（更灵活，能理解复杂表达）
- 当 LLM 不可用或置信度 < 0.6 时，回退到 rule_semantic_frame()（纯规则匹配）
- 两条路径的结果都要经过 _merge_rule_guards() 合并——规则检测到的硬约束
  （如购物车操作、违规内容）不会被 LLM 覆盖

"C4 / A1 / A2 评测开关"：
这些是长会话评测中的实验条件代码名，通过 config.Settings 的 eval_* 字段控制：
- C4（窗口截断）生产默认启用：只保留最近 3 轮对话上下文，防止 LLM 对历史过拟合
- A1（结构化快照）生产默认启用：用结构化 JSON 代替原始对话日志，减少 token 消耗
- A2（推荐记忆缓存）生产默认启用：缓存最近推荐结果，相同查询直接返回缓存

"规则保底"（Rule Guards）：
rule_semantic_frame() 是一套基于正则和关键字匹配的规则引擎。
它的作用不是替代 LLM，而是作为 LLM 的安全网——LLM 可能出错（返回不存在的商品、
错误的购物车操作等），规则引擎可以检测并覆盖这些错误。

===== 数据流 =====

用户消息 → SemanticParser.parse()
    ├─ LLM 路径：llm_client.parse_semantic_frame() → _parse_frame() → JSON → SemanticFrame
    │   └─ 置信度 < 0.6 → intent 改为 clarification
    └─ 规则路径：rule_semantic_frame() → 正则+关键字 → 硬规则分类
    ↓
_merge_rule_guards()：合并两条路径结果，规则检测的硬约束优先级更高
    ↓
返回 SemanticFrame → 被 Agent.stream_message() 消费 → StateReducer.apply() → 检索

===== 与其它模块协作 =====

- agent.py：ShopGuideAgent 创建 SemanticParser 实例并调用 parse()
- models.py：SemanticFrame, ConstraintEdits, CartOperation, ShoppingIntentIR
- state_reducer.py：消费 SemanticFrame.constraint_edits 更新对话状态
- intent_compiler.py：将 SemanticFrame 进一步编译为 ShoppingIntentIR
- cart_intent.py：_detect_quantity 等购物车意图检测辅助
- utils.py：extract_json 从 LLM 返回文本中提取 JSON
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from .cart_intent import _detect_cart_action, _detect_quantity as _detect_cart_quantity, _normalize_cart_action
from .constraint_filter import dedupe, extract_excluded_brands, extract_included_brands
from .models import CartOperation, ChatRequest, ConstraintEdits, HardConstraints, ProductReference, RetrievalPlan, SemanticFrame, SessionContext
from .utils import extract_json


class SemanticParser:
    """混合语义解析器：LLM + 规则双路径，LLM 优先 + 规则保底。

    初始化时可选择注入 llm_client（弱类型，支持任何实现了 parse_semantic_frame 的对象）。
    如果 llm_client 为 None 或调用失败，parse() 自动回退到纯规则模式。
    """
    def __init__(self, llm_client: Any | None = None, settings: Any | None = None):
        # settings: 仅长会话评测专用。运行时由 ShopGuideAgent 注入，用于决定是否启用
        # A1（窗口截断）/ A2（结构化快照）禁用开关。production 默认 None → 全开行为。
        self.llm_client = llm_client
        self.settings = settings

    def _payload(self, context: SessionContext | None) -> dict[str, Any]:
        disable_window = bool(getattr(self.settings, "eval_disable_window_truncation", False))
        disable_snapshot = bool(getattr(self.settings, "eval_disable_structured_snapshot", False))
        return semantic_context_payload(context, disable_window=disable_window, disable_snapshot=disable_snapshot)

    async def parse(self, request: ChatRequest, context: SessionContext | None = None) -> SemanticFrame:
        if self.llm_client and hasattr(self.llm_client, "parse_semantic_frame"):
            try:
                raw = await self.llm_client.parse_semantic_frame(
                    request.message,
                    self._payload(context),
                    request_type=request.type,
                )
                frame = _parse_frame(raw)
                if frame.confidence < 0.6:
                    frame.intent = "clarification"
                    frame.clarification_question = frame.clarification_question or "我没太理解你的意思，可以再说具体一点吗？比如想买什么、预算多少，或者有什么偏好。"
                guarded = _merge_rule_guards(frame, request)
                if guarded.intent == "unclear_input":
                    recovered = await self._try_contextual_followup_judge(request, self._payload(context))
                    if recovered is not None:
                        return recovered
                    recovered_by_rule = _contextual_rule_followup(request, self._payload(context))
                    if recovered_by_rule is not None:
                        return recovered_by_rule
                recovered_by_rule = _contextual_rule_followup(request, self._payload(context))
                if recovered_by_rule is not None and guarded.intent == "recommend_product":
                    return recovered_by_rule
                return guarded
            except Exception:
                pass
        return rule_semantic_frame(request)

    async def _try_contextual_followup_judge(
        self, request: ChatRequest, context_payload: dict[str, Any]
    ) -> SemanticFrame | None:
        if request.type != "user_message" or not context_payload.get("has_focus_product"):
            return None
        if not self.llm_client or not hasattr(self.llm_client, "classify_contextual_followup"):
            return None
        try:
            raw = await self.llm_client.classify_contextual_followup(request.message, context_payload)
            frame = _parse_frame(raw)
            if frame.intent != "product_followup":
                return None
            return _merge_rule_guards(frame, request)
        except Exception:
            return None


def apply_constraint_edits(base_plan: RetrievalPlan, edits: ConstraintEdits, message: str = "") -> RetrievalPlan:
    """将 ConstraintEdits 应用到 RetrievalPlan，返回修改后的新 plan（深拷贝）。

    原 plan 不会被修改（model_copy(deep=True)），调用方可以安全地重用原 plan。
    这是与 StateReducer._apply_constraint_edits 平行的路径——StateReducer 修改
    SessionContext 中的约束状态，而这里修改独立的 RetrievalPlan（如 PlannerAgent 产出后微调）。
    """
    plan = base_plan.model_copy(deep=True)
    constraints = plan.hard_constraints
    _remove_constraints(constraints, edits.remove)
    _relax_constraints(constraints, edits.relax)
    _add_constraints(constraints, edits.add)
    if edits.add.soft_preferences:
        plan.soft_preferences.update(edits.add.soft_preferences)
    if edits.remove.soft_preferences:
        for key, value in edits.remove.soft_preferences.items():
            if plan.soft_preferences.get(key) == value:
                plan.soft_preferences.pop(key, None)
    plan.category = constraints.sub_category or constraints.category or plan.category
    plan.retrieval_query = _build_retrieval_query(message, constraints, plan.soft_preferences)
    return plan


def resolve_cart_operation(operation: CartOperation, context: SessionContext, product_map: dict[str, Any], cart_snapshot: dict) -> tuple[str, int, str | None]:
    action = _normalize_cart_action(operation.action)
    product_id = _resolve_reference(operation.target, context, product_map, cart_snapshot)
    quantity = max(operation.quantity, 0)
    return action, quantity, product_id


def rule_semantic_frame(request: ChatRequest):
    """纯规则引擎 — 直接返回 UnifiedPlan（Stage 2 扁平字段）。"""
    from .models import UnifiedPlan
    text = request.message or ""
    tool = "product_followup" if request.type == "product_followup" else "recommend_product"

    cart_action = _detect_cart_action(text)
    if cart_action != "get_cart" or any(word in text for word in ["购物车", "下单", "结算"]):
        return UnifiedPlan(
            tool="cart_operation",
            cart_action=cart_action,
            cart_quantity=_detect_quantity(text) or request.quantity,
        )
    if request.type == "user_message" and _is_compare_request(text):
        return UnifiedPlan(tool="compare_products")
    if request.type == "user_message" and _is_small_talk(text):
        return UnifiedPlan(tool="small_talk")
    if request.type == "user_message" and not _has_shopping_signal(text):
        return UnifiedPlan(tool="unclear_input")

    frame = UnifiedPlan(tool=tool)
    price_min = _detect_price_min(text)
    if price_min is not None:
        frame.price_min = price_min
    price_max = _detect_price_max(text)
    if price_max is not None:
        frame.price_max = price_max
    included_brands = extract_included_brands(text)
    if included_brands:
        frame.include_brands = dedupe(list(frame.include_brands) + included_brands)
    if re.search(r"不要|不含|排除|除了", text):
        frame.exclude_brands = dedupe(list(frame.exclude_brands) + extract_excluded_brands(text))
    # soft preferences
    soft: dict[str, str] = {}
    if "拍照" in text: soft["priority"] = "拍照"
    if "续航" in text: soft["priority"] = "续航"
    if "性价比" in text: soft["priority"] = "性价比"
    if "轻薄" in text or "便携" in text: soft["priority"] = "轻薄便携"
    if "性能" in text or "游戏" in text: soft["priority"] = "性能优先"
    if "油皮" in text or "混油" in text: soft["skin_type"] = "油皮"
    if "敏感肌" in text: soft["skin_type"] = "敏感肌"
    if "干性皮肤" in text or "干皮" in text or "干性" in text: soft["skin_type"] = "干性"
    if "秋冬" in text: soft["season"] = "秋冬"
    if "春天" in text or "春季" in text: soft["season"] = "春季"
    if "夏天" in text or "夏季" in text: soft["season"] = "夏季"
    if "冬天" in text or "冬季" in text: soft["season"] = "冬季"
    if "保湿" in text or "修护" in text: soft["effect"] = "保湿修护"
    if "女朋友" in text or "女生" in text: soft["recipient"] = "女朋友"
    if "男朋友" in text or "男生" in text: soft["recipient"] = "男朋友"
    if "爸" in text or "妈" in text or "父母" in text or "长辈" in text: soft["recipient"] = "长辈"
    if "礼物" in text or "送人" in text or "送给" in text or "送" in text: soft["occasion"] = "送礼"
    if "惊喜" in text: soft["gift_style"] = "惊喜感"
    if "稳妥" in text or "不踩雷" in text: soft["gift_style"] = "稳妥不踩雷"
    if "实用" in text: soft["gift_style"] = "实用"
    if any(phrase in text for phrase in ["回到第一轮", "最开始那个", "第一轮那个", "回到最开始"]):
        soft["anchor_reference"] = "first_turn"
    if request.type == "product_followup":
        tool = "product_followup"
    frame.tool = tool
    frame.soft_preferences = soft
    return frame


def _contextual_rule_followup(request: ChatRequest, context_payload: dict[str, Any]):
    """Stage 2: 直接返回 UnifiedPlan。"""
    from .models import UnifiedPlan
    if request.type != "user_message":
        return None
    has_context = (
        context_payload.get("has_focus_product") or
        (context_payload.get("last_plan") and context_payload.get("last_product_ids"))
    )
    if not has_context:
        return None
    text = request.message or ""
    soft: dict[str, str] = {}
    response_goal = None
    has_cheaper_cue = any(word in text for word in ["再便宜", "便宜点", "更便宜", "价格低", "低价"])
    if has_cheaper_cue or any(word in text for word in ["替代品", "平替"]):
        soft["price_preference"] = "更便宜"
        response_goal = "recommend_cheaper_alternative"
    if any(word in text for word in ["更贵", "贵一点", "高端", "高价位", "价位高"]):
        soft["price_preference"] = "更贵"
        response_goal = "recommend_more_expensive_alternative"
    excluded = extract_excluded_brands(text)
    if any(word in text for word in ["不要这个品牌", "不要这个牌子", "换个品牌", "别的品牌"]):
        response_goal = "exclude_current_brand"
    if any(word in text for word in ["刚刚那个", "为什么推荐", "是什么", "介绍一下"]):
        response_goal = "explain_focus_product"
    if not response_goal and any(word in text for word in ["还有别的", "还有别", "换一个", "换一款", "这个不适合", "不适合"]):
        response_goal = "recommend_alternative"
    if response_goal is None:
        return None
    return UnifiedPlan(
        tool="product_followup",
        soft_preferences=soft,
        exclude_brands=list(excluded),
        followup_kind=response_goal,
    )


def _parse_frame(raw: str):
    """Stage 2: 解析 LLM JSON，旧格式 → UnifiedPlan 扁平字段。"""
    from .models import UnifiedPlan
    data = extract_json(raw)
    edits = data.get("constraint_edits")
    if isinstance(edits, dict):
        add = edits.get("add") or {}
        data.setdefault("price_min", add.get("price_min"))
        data.setdefault("price_max", add.get("price_max"))
        data.setdefault("include_brands", add.get("include_brands") or [])
        data.setdefault("exclude_brands", add.get("exclude_brands") or [])
        data.setdefault("soft_preferences", add.get("soft_preferences") or {})
    cart = data.get("cart_operation")
    if isinstance(cart, dict):
        data.setdefault("cart_action", cart.get("action"))
        data.setdefault("cart_quantity", cart.get("quantity", 1))
        target = cart.get("target")
        if isinstance(target, dict):
            data.setdefault("cart_target_product_id", target.get("product_id"))
    if "intent" in data and "tool" not in data:
        data["tool"] = data.pop("intent")
    return UnifiedPlan.model_validate(data)


def _merge_rule_guards(frame, request: ChatRequest):
    """Stage 2: 直接操作 UnifiedPlan 扁平字段。"""
    guarded = rule_semantic_frame(request)
    if guarded.tool == "small_talk":
        frame.tool = "small_talk"
        return frame
    if guarded.tool == "unclear_input" and frame.tool == "recommend_product":
        frame.tool = "unclear_input"
        return frame
    if guarded.tool == "cart_operation" and frame.tool not in {"product_followup", "compare_products"} and frame.cart_action is None:
        frame.tool = guarded.tool
        frame.cart_action = guarded.cart_action
        frame.cart_target_product_id = guarded.cart_target_product_id
        frame.cart_quantity = guarded.cart_quantity
    frame.include_brands = dedupe(list(frame.include_brands) + list(guarded.include_brands))
    frame.exclude_brands = dedupe(list(frame.exclude_brands) + list(guarded.exclude_brands))
    if guarded.price_min is not None:
        frame.price_min = guarded.price_min
    if guarded.price_max is not None:
        frame.price_max = guarded.price_max
    frame.soft_preferences.update(guarded.soft_preferences)
    return frame


def _is_compare_request(text: str) -> bool:
    return bool(re.search(r"对比|比较一下|比较下|哪个更|哪款更|怎么选|第一款|第二款|第三款", text or ""))


def _is_small_talk(text: str) -> bool:
    normalized = re.sub(r"[\s?？!！。,.，、]+", "", (text or "").lower())
    if not normalized:
        return True
    if _has_shopping_signal(text):
        return False
    capability_patterns = [
        "你能做什么",
        "你能帮我做什么",
        "你能帮我做些什么",
        "你能做啥",
        "你有什么功能",
        "你有什么用",
        "你可以做什么",
        "你可以帮我做什么",
        "你是干嘛的",
        "你是做什么的",
        "你是谁",
        "你是谁呀",
    ]
    if any(p in normalized for p in capability_patterns):
        return True
    # 扩展的日常闲聊模式：涵盖更广泛的自然对话场景
    small_talk_patterns = [
        # 问候与告别
        r"(早上好|中午好|下午好|晚上好|早安|晚安|再见|拜拜|bye|goodbye|seeyou)",
        # 心情与状态
        r"(心情|开心|难过|无聊|累了|好累|困了|好困|睡不着|压力|焦虑)",
        # 日常闲聊
        r"(今天天气|天气|下雨|晴天|阴天|好冷|好热|好饿|饿了|吃了|吃饭)",
        # 意见与闲聊
        r"^(你觉得|你认为|你怎么看|怎么看|行不行|好不好|可以吗|有没有可能)",
        # 能力边界
        r"(你能|你会|你知道|你懂|你来|你给我|帮我|帮我看|看看这个|听一下)",
        # 纯社交
        r"^(好的|好吧|行吧|嗯嗯|哦哦|哈哈|呵呵|嘿嘿|嘻嘻|不错|厉害|牛|nb)",
        # 感谢与反馈
        r"(谢谢|多谢|感谢|谢了|辛苦了|麻烦|拜托|不客气|没问题|没关系)",
        # 表达感受
        r"(我喜欢|我不喜欢|我觉得|我感觉|我想|我需要|我打算|我计划)",
    ]
    if any(re.search(p, normalized) for p in small_talk_patterns):
        return True
    # 极短消息（<=5 个字符且无明确购物动词）视为闲聊
    if len(normalized) <= 5 and not re.search(r"(买|卖|要|给|换|找|订|配)", normalized):
        return True
    return bool(
        re.fullmatch(
            r"(你好|您好|h[ae]l+o+|hello|hi|hey|yo|在吗|在不在|谢谢|谢了|感谢|辛苦了)",
            normalized,
        )
    )


def _has_shopping_signal(text: str) -> bool:
    return bool(
        re.search(
            r"推荐|recommend|找|买|buy|want|想要|想买|我要|要一|要个|来一|来瓶|来个|拿一|看看|有没有|预算|budget|under|below|以内|以下|以上|不低于|不要|不含|排除|对比|比较|哪个更|怎么选|购物车|加购|加入|下单|结算|防晒|精华|护肤|美妆|化妆|化妆品|彩妆|手机|笔记本|电脑|耳机|跑鞋|鞋|衣服|背包|咖啡|coffee|cafe|饮料|食品|零食|特饮|功能饮料|能量饮料|礼物|送人|送给",
            text or "",
            flags=re.I,
        )
    )


def semantic_context_payload(
    context: SessionContext | None,
    *,
    disable_window: bool = False,
    disable_snapshot: bool = False,
) -> dict[str, Any]:
    """构建注入 LLM 语义解析的上下文 payload。

    包含当前焦点商品、最近推荐列表、购物车最近操作、全局画像、待澄清/恢复状态等。
    这是 LLM 理解"当前对话在聊什么"的关键信息包。

    评测模式：
    - disable_window=True（A1 评测）：不截断历史窗口，LLM 看到全量对话事件
    - disable_snapshot=True（A2 评测）：清空结构化快照字段（last_plan/pending/current_task），
      但不碰 focus_product_id（状态机仍需要它），LLM 完全依赖原始文本做决策
    - 生产环境两者均为 False：窗口截断 + 结构化快照全开（C4 全开行为）
    """
    if context is None:
        return {}
    focus_product = _focus_product_summary(context)
    pending_clar = (
        context.state.pending_clarification.model_dump(mode="json")
        if context.state.pending_clarification
        else None
    )
    pending_rec = (
        context.state.pending_recovery.model_dump(mode="json")
        if context.state.pending_recovery
        else None
    )
    last_plan_payload = context.last_plan.model_dump(mode="json") if context.last_plan else None
    current_task_payload = context.state.current_task.model_dump(mode="json")

    if disable_snapshot:
        # A2 评测模式：清四项结构化快照字段；focus_product_id 自身保留（状态机仍跑）
        focus_product = None
        last_plan_payload = None
        pending_clar = None
        current_task_payload = None

    return {
        "last_plan": last_plan_payload,
        "last_intent": context.state.dialog_state.last_intent,
        "focus_product_id": context.focus_product_id,
        "has_focus_product": focus_product is not None,
        "focus_product": focus_product,
        "last_product_ids": list(context.last_product_ids),
        "last_recommendations": list(context.last_recommendations),
        "recent_cart_product_id": context.recent_cart_product_id,
        "global_profile": dict(context.global_profile),
        "current_task": current_task_payload,
        "pending_clarification": pending_clar,
        "pending_recovery": pending_rec,
        "recent_context": _recent_context_summary(context, disable_window=disable_window),
    }


def _focus_product_summary(context: SessionContext) -> dict[str, Any] | None:
    focus_id = context.focus_product_id
    if not focus_id:
        return None
    for item in context.last_recommendations:
        if item.get("product_id") == focus_id:
            return dict(item)
    return {"product_id": focus_id}


def _recent_context_summary(
    context: SessionContext,
    *,
    disable_window: bool = False,
) -> dict[str, Any]:
    """构建"最近对话上下文"的摘要，供 LLM 理解当前对话状态。

    正常模式（disable_window=False，C4 全开）：
    - recent_user_turns：最近 3 轮用户消息（取 user_turn_events[-6:][-3:]）
    - recent_recommendation_sets：最近 3 组推荐结果
    - last_events：最近 3 个对话事件

    评测模式（disable_window=True，A1 禁用窗口截断）：
    - 返回全量历史，不做任何截断
    - 外层有 25K token 硬截断保护（agent.py 中的 trim 逻辑），
      所以这里不截断也不会 OOM，但 LLM 可能对历史过拟合
    """
    rec_events = [
        event.model_dump(mode="json")
        for event in context.state.context_events
        if event.result_type == "recommendation_set"
    ]
    user_turn_events = [
        {
            "turn_index": event.turn_index,
            "user_message": event.user_message,
            "assistant_intent": event.assistant_intent,
            "result_type": event.result_type,
        }
        for event in context.state.context_events
    ]
    all_events = [event.model_dump(mode="json") for event in context.state.context_events]
    if disable_window:
        # A1 评测模式：不截窗口，让 LLM 看到全量历史；外层 25K 硬截断保护见 agent.py
        return {
            "recent_user_turns": user_turn_events,
            "recent_recommendation_sets": rec_events,
            "last_events": all_events,
        }
    return {
        "recent_user_turns": user_turn_events[-6:][-3:],
        "recent_recommendation_sets": rec_events[-3:],
        "last_events": all_events[-3:],
    }


def _remove_constraints(constraints: HardConstraints, patch) -> None:
    if patch.category and constraints.category == patch.category:
        constraints.category = None
    if patch.sub_category and constraints.sub_category == patch.sub_category:
        constraints.sub_category = None
    if patch.price_min is not None and constraints.price_min == patch.price_min:
        constraints.price_min = None
    if patch.price_max is not None and constraints.price_max == patch.price_max:
        constraints.price_max = None
    for term in patch.exclude_terms:
        constraints.exclude_terms = [value for value in constraints.exclude_terms if value != term]
    for brand in patch.include_brands:
        constraints.include_brands = [value for value in constraints.include_brands if value != brand]
    for brand in patch.exclude_brands:
        constraints.exclude_brands = [value for value in constraints.exclude_brands if value != brand]
    for region in patch.exclude_brand_regions:
        constraints.exclude_brand_regions = [value for value in constraints.exclude_brand_regions if value != region]


def _relax_constraints(constraints: HardConstraints, fields: list[str]) -> None:
    for field in fields:
        if field == "price_min":
            constraints.price_min = None
        if field == "price_max":
            constraints.price_max = None
        if field == "category":
            constraints.category = None
        if field == "sub_category":
            constraints.sub_category = None
        if field == "exclude_terms":
            constraints.exclude_terms = []
        if field == "include_brands":
            constraints.include_brands = []
        if field == "exclude_brands":
            constraints.exclude_brands = []
        if field == "exclude_brand_regions":
            constraints.exclude_brand_regions = []


def _add_constraints(constraints: HardConstraints, patch) -> None:
    if patch.category:
        constraints.category = patch.category
    if patch.sub_category:
        constraints.sub_category = patch.sub_category
    if patch.price_min is not None:
        constraints.price_min = patch.price_min
    if patch.price_max is not None:
        constraints.price_max = patch.price_max
    constraints.exclude_terms = dedupe(constraints.exclude_terms + patch.exclude_terms)
    constraints.include_brands = dedupe(constraints.include_brands + patch.include_brands)
    constraints.exclude_brands = dedupe(constraints.exclude_brands + patch.exclude_brands)
    constraints.exclude_brand_regions = dedupe(constraints.exclude_brand_regions + patch.exclude_brand_regions)


def _build_retrieval_query(message: str, constraints: HardConstraints, soft_preferences: dict[str, str]) -> str:
    return " ".join(
        part
        for part in [
            message,
            constraints.category or "",
            constraints.sub_category or "",
            *constraints.include_brands,
            *soft_preferences.values(),
        ]
        if part
    ) or "商品推荐"


def _resolve_reference(reference: ProductReference, context: SessionContext, product_map: dict[str, Any], cart_snapshot: dict) -> str | None:
    if reference.product_id:
        return reference.product_id
    if reference.reference in {"focus_product", "current_product"}:
        return context.focus_product_id or (context.last_product_ids[0] if context.last_product_ids else None)
    if reference.reference in {"last_recommendation", "last_recommendations", "recommendations"}:
        candidates = [product_map[product_id] for product_id in context.last_product_ids if product_id in product_map]
        if not candidates:
            return None
        if reference.index is not None and 0 <= reference.index < len(candidates):
            return candidates[reference.index].product_id
        if reference.selection_strategy == "cheapest":
            return min(candidates, key=lambda product: product.price).product_id
        if reference.selection_strategy == "most_expensive":
            return max(candidates, key=lambda product: product.price).product_id
        return candidates[0].product_id
    if reference.reference in {"recent_cart_item", "cart_item"}:
        if context.recent_cart_product_id:
            return context.recent_cart_product_id
        items = cart_snapshot.get("items", [])
        if reference.index is not None and 0 <= reference.index < len(items):
            return items[reference.index].get("product_id")
        if items:
            return items[0].get("product_id")
    return context.focus_product_id or (context.last_product_ids[0] if context.last_product_ids else None)


def _rule_product_reference(text: str) -> ProductReference:
    if "最便宜" in text:
        return ProductReference(reference="last_recommendations", selection_strategy="cheapest")
    index = _detect_index(text)
    if index is not None:
        return ProductReference(reference="last_recommendations", selection_strategy="index", index=index)
    if any(word in text for word in ["刚才", "这款", "这个", "主推"]):
        return ProductReference(reference="focus_product", selection_strategy="primary")
    return ProductReference(reference="focus_product", selection_strategy="primary")


def _detect_index(text: str) -> int | None:
    index_map = {"第一": 0, "第1": 0, "第二": 1, "第2": 1, "第三": 2, "第3": 2}
    for marker, index in index_map.items():
        if marker in text:
            return index
    return None



def _detect_quantity(text: str) -> int | None:
    return _detect_cart_quantity(text)


def _detect_price_min(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以上|起|往上)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"(?:不低于|至少|高于)\s*(\d+(?:\.\d+)?)\s*(?:元|块)?", text)
    if match:
        return float(match.group(1))
    match = re.search(r"预算\s*(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以上|起|往上)", text)
    if match:
        return float(match.group(1))
    return None


def _detect_price_max(text: str) -> float | None:
    if _detect_price_min(text) is not None:
        return None
    match = re.search(
        r"(?:不超过|不超|不高于|低于|小于|少于|最多|至多|最高)\s*(\d+(?:\.\d+)?)\s*(?:元|块)?",
        text,
    )
    if match:
        return float(match.group(1))
    match = re.search(
        r"(?:under|below|less than|no more than)\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.I,
    )
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以内|以下|内)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"预算\s*(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    return None
