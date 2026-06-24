from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel

from ..models import Product


class ScriptTurn(BaseModel):
    phase: str
    turn_type: str
    query: str
    expected: dict[str, Any]
    adversarial_subtype: str | None = None


# 类目模板：每个类目 10 个模板
# 格式：(turn_type, query_template, doc_note)
CATEGORY_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "美妆护肤": [
        ("retrieval", "{prefix}{title}怎么样？", "商品询问"),
        ("retrieval", "{prefix}推荐一款{category}产品", "类目推荐"),
        ("followup_factual", "价格多少钱？", "价格询问"),
        ("followup_factual", "这个产品有什么功效？", "功效询问"),
        ("comparison", "和{other_title}比哪个好？", "对比询问"),
        ("retrieval", "{prefix}适合敏感肌的{category}", "属性筛选"),
        ("followup_factual", "主要成分是什么？", "成分询问"),
        ("constraint_handling", "要清爽不油腻的", "约束补充"),
        ("cart_action", "这个我想买", "购物意向"),
        ("retrieval", "{prefix}防晒产品推荐", "需求明确"),
    ],
    "食品饮料": [
        ("retrieval", "{prefix}{title}好吃吗？", "商品询问"),
        ("retrieval", "{prefix}推荐一款{category}", "类目推荐"),
        ("followup_factual", "这个热量高吗？", "热量询问"),
        ("followup_factual", "保质期多久？", "保质期询问"),
        ("comparison", "和{other_title}比哪个更健康？", "对比询问"),
        ("retrieval", "{prefix}无糖{category}推荐", "属性筛选"),
        ("followup_factual", "配料表是什么？", "配料询问"),
        ("constraint_handling", "要低糖的", "约束补充"),
        ("cart_action", "这个我想买一份", "购物意向"),
        ("retrieval", "{prefix}零食推荐", "需求明确"),
    ],
    "服饰运动": [
        ("retrieval", "{prefix}{title}好看吗？", "商品询问"),
        ("retrieval", "{prefix}推荐一件{category}", "类目推荐"),
        ("followup_factual", "这个是什么材质？", "材质询问"),
        ("followup_factual", "尺码准确吗？", "尺码询问"),
        ("comparison", "和{other_title}比哪个更舒服？", "对比询问"),
        ("retrieval", "{prefix}透气{category}推荐", "属性筛选"),
        ("followup_factual", "怎么清洗？", "清洗询问"),
        ("constraint_handling", "要宽松一点的", "约束补充"),
        ("cart_action", "这个我想要一件", "购物意向"),
        ("retrieval", "{prefix}运动装推荐", "需求明确"),
    ],
    "数码电子": [
        ("retrieval", "{prefix}{title}好用吗？", "商品询问"),
        ("retrieval", "{prefix}推荐一款{category}", "类目推荐"),
        ("followup_factual", "续航时间多久？", "续航询问"),
        ("followup_factual", "配置怎么样？", "配置询问"),
        ("comparison", "和{other_title}比哪个性价比高？", "对比询问"),
        ("retrieval", "{prefix}性价比高的{category}", "属性筛选"),
        ("followup_factual", "保修多久？", "保修询问"),
        ("constraint_handling", "要性能好的", "约束补充"),
        ("cart_action", "这个我想买", "购物意向"),
        ("retrieval", "{prefix}手机推荐", "需求明确"),
    ],
    "家居日用": [
        ("retrieval", "{prefix}{title}实用吗？", "商品询问"),
        ("retrieval", "{prefix}推荐一款{category}", "类目推荐"),
        ("followup_factual", "这个耐用吗？", "耐用性询问"),
        ("followup_factual", "怎么使用？", "使用询问"),
        ("comparison", "和{other_title}比哪个质量好？", "对比询问"),
        ("retrieval", "{prefix}实用{category}推荐", "属性筛选"),
        ("followup_factual", "尺寸多大？", "尺寸询问"),
        ("constraint_handling", "要节省空间的", "约束补充"),
        ("cart_action", "这个我想买一个", "购物意向"),
        ("retrieval", "{prefix}收纳用品推荐", "需求明确"),
    ],
}

CATEGORY_ORDER = ["美妆护肤", "食品饮料", "服饰运动", "数码电子"]

# 对抗样本模板：D1-D6
ADVERSARIAL_TEMPLATES: dict[str, list[str]] = {
    "D1": [
        "刚才那个商品再推荐一下？",
        "我想再看看之前提到的那个产品",
        "回头说一下第一个推荐的",
        "刚才看的那个再给我介绍一下",
        "之前的那个商品链接还在吗？",
        "我想回到之前那个产品",
        "再给我看一眼最早推荐的那个",
        "前面提到的那个商品再讲一遍",
        "刚才那个再展示一下",
        "之前推荐过的那个再提一下",
        "第一个给我看的那个是什么来着？",
        "回到之前的那个推荐",
        "再说一遍刚才那个产品",
        "我想再看看之前那个",
        "刚才的那个再给我说说",
    ],
    "D2": [
        "我没说过我要这个",
        "我没提过价格敏感",
        "我没说过不喜欢这个品牌",
        "我从来没说过要便宜的",
        "你记错了，我没那么说过",
        "我没说过要那种功能",
        "我没说过讨厌这个颜色",
        "你理解错了，我不是那个意思",
        "我没说过不要这个",
        "我没提过这个要求",
    ],
    "D3": [
        "我改主意了，还是要贵的那个",
        "等等，我不要这个了，换另一个",
        "突然觉得之前那个更好",
        "我反悔了，还是选原来的吧",
        "等等，我重新想想，还是之前那个好",
        "不，换一下，我要之前排除的那个",
        "我现在想了想，还是第一个合适",
        "等等，我改变决定了",
        "不好意思，我换一下，还是要那个",
        "突然改变想法了，还是之前的",
    ],
    "D4": [
        "不管怎样，就选最贵的",
        "我不管，就要这个",
        "别管那么多，直接推荐第一个",
        "不管好不好，就要这个了",
        "不用管我之前说的，就这个吧",
        "不管有没有货，我就要它",
        "别解释，直接加购物车",
        "不管价格多少，买了",
        "不用管那么多，我认定这个了",
        "不管怎么样，我就选它了",
    ],
    "D5": [
        "刚才那个防晒再给我看看？",
        "之前的那个零食链接还在吗？",
        "回头说一下那个手机",
        "我想再看看之前提到的那件衣服",
        "再给我看一眼最早推荐的那个家居用品",
        "前面提到的那个美妆再讲一遍",
        "刚才的那个饮料再给我说说",
        "我想再看看之前那个电子产品",
        "之前推荐过的那个运动装备再提一下",
        "第一个给我看的那个数码产品是什么来着？",
        "回到之前的那个家居推荐",
        "再说一遍刚才那个护肤产品",
        "我想再看看之前那个食品",
        "刚才的那件衣服再展示一下",
        "之前的那个电子设备再给我介绍一下",
    ],
    "D6": [
        "对了，第一个推荐的那个商品有什么特点？",
        "等一下，我想知道之前那个产品的价格",
        "话说回来，最早的那个选项是什么来着？",
        "再确认一下，之前说的那个是真的吗？",
        "顺便问下，刚才那个产品的评价怎么样？",
        "对了，之前那个产品有优惠吗？",
        "等一下，第一个商品有什么规格？",
        "话说回来，之前那个产品的材质是什么？",
        "再问一下，刚才那个有什么颜色可选？",
        "顺便提下，之前那个产品的保质期多久？",
        "对了，第一个推荐的商品是哪个品牌？",
        "等一下，之前那个产品库存足吗？",
        "话说回来，最早那个选项的评价好吗？",
        "再确认一下，刚才说的那个是真的吗？",
        "顺便问下，之前那个产品能退换吗？",
    ],
}


def _intent_for(turn_type: str) -> str:
    mapping = {
        "retrieval": "recommend_product",
        "followup_factual": "product_followup",
        "comparison": "compare_products",
        "cart_action": "cart_add",
        "long_range_reference": "recommend_product",
        "constraint_handling": "revise_constraints",
        "adversarial_reference": "recommend_product",
        "adversarial_constraint": "revise_constraints",
    }
    return mapping.get(turn_type, "recommend_product")


def build_long_session_script(products: list[Product], *, seed: int = 20260624) -> list[ScriptTurn]:
    rng = random.Random(seed)

    # 按类目分组，组内按 product_id 稳定排序
    products_by_category: dict[str, list[Product]] = {}
    for p in products:
        products_by_category.setdefault(p.category, []).append(p)
    for cat in products_by_category:
        products_by_category[cat].sort(key=lambda p: p.product_id)

    # 交替穿插生成 100 个商品序列（每类 20 个，若某类不足则循环使用）
    interleaved_products: list[Product] = []
    indices = {cat: 0 for cat in CATEGORY_ORDER}
    while len(interleaved_products) < 100:
        for cat in CATEGORY_ORDER:
            if len(interleaved_products) >= 100:
                break
            cat_products = products_by_category.get(cat, [])
            if not cat_products:
                continue
            idx = indices[cat] % len(cat_products)
            interleaved_products.append(cat_products[idx])
            indices[cat] += 1

    # 生成 phase A：1000 轮（每个商品 10 个模板）
    phase_a: list[ScriptTurn] = []
    for product in interleaved_products:
        templates = CATEGORY_TEMPLATES.get(product.category, CATEGORY_TEMPLATES["美妆护肤"])
        # 找另一个同类商品用于 comparison 模板
        same_cat = [p for p in interleaved_products if p.category == product.category and p.product_id != product.product_id]
        other_product = same_cat[0] if same_cat else product

        for turn_type, template, doc_note in templates:
            prefix = rng.choice(["", "想买", "推荐", "请问", "想看看"])
            query = template.format(
                prefix=prefix,
                title=product.title,
                category=product.category,
                other_title=other_product.title if other_product else product.title,
            )
            expected = {
                "expected_intent": _intent_for(turn_type),
                "subject_product_id": product.product_id,
            }
            phase_a.append(ScriptTurn(
                phase="A",
                turn_type=turn_type,
                query=query,
                expected=expected,
            ))

    # 生成 phase B：5 轮跨商品横评
    phase_b: list[ScriptTurn] = []
    b_questions = [
        "这几个产品里哪个性价比最高？",
        "综合来看推荐哪个？",
        "哪一个更值得买？",
        "这几款里你最推荐哪一个？",
        "对比一下这几个产品？",
    ]
    for i, question in enumerate(b_questions):
        # 选几个产品作为 expected.subject_product_ids
        subject_ids = [p.product_id for p in interleaved_products[i*5:i*5+3]]
        phase_b.append(ScriptTurn(
            phase="B",
            turn_type="comparison",
            query=question,
            expected={
                "expected_intent": "compare_products",
                "subject_product_ids": subject_ids,
            },
        ))

    # 生成 phase C：10 轮长程指代（每轮指向 150 轮前）
    phase_c: list[ScriptTurn] = []
    for i in range(10):
        target_turn = 50 + i * 100  # target 在 50, 150, ..., 950（纯 A 序列中的位置）
        target_product = interleaved_products[(target_turn // 10) % len(interleaved_products)]
        phase_c.append(ScriptTurn(
            phase="C",
            turn_type="long_range_reference",
            query=f"之前推荐的{target_product.title}还在吗？",
            expected={
                "expected_intent": "recommend_product",
                "expected_focus_turn_index": target_turn,  # 暂时存纯 A 的位置，之后修正
                "subject_product_id": target_product.product_id,
            },
        ))

    # 生成 phase D：75 轮对抗样本（D1-D6）
    phase_d: list[ScriptTurn] = []
    # D1: 15, D2: 10, D3: 10, D4: 10, D5: 15, D6: 15 = 75
    d_distribution = [("D1", 15), ("D2", 10), ("D3", 10), ("D4", 10), ("D5", 15), ("D6", 15)]
    for subtype, count in d_distribution:
        templates = ADVERSARIAL_TEMPLATES[subtype]
        turn_type = "adversarial_reference" if subtype in ("D1", "D5", "D6") else "adversarial_constraint"
        for i in range(count):
            query = templates[i % len(templates)]
            phase_d.append(ScriptTurn(
                phase="D",
                turn_type=turn_type,
                query=query,
                expected={
                    "expected_intent": _intent_for(turn_type),
                },
                adversarial_subtype=subtype,
            ))

    # 生成 phase E：10 轮交易相关
    phase_e: list[ScriptTurn] = []
    e_questions = [
        "怎么下单？",
        "有什么支付方式？",
        "包邮吗？",
        "多久能到？",
        "能退换吗？",
        "有什么优惠？",
        "加入购物车",
        "我要付款了",
        "怎么确认收货？",
        "有发票吗？",
    ]
    for question in e_questions:
        phase_e.append(ScriptTurn(
            phase="E",
            turn_type="cart_action",
            query=question,
            expected={
                "expected_intent": "cart_add",
            },
        ))

    # 最稳妥的策略：
    # 1. 先生成完整序列的索引映射
    # 2. 按顺序构建：A -> 预留位置 -> 填充 B/C/D/E

    # 我们将构建一个包含所有元素的列表，每个位置我们都明确
    # 先分配位置：
    final: list[ScriptTurn | None] = [None] * 1100

    # phase E 在最后 10 个位置
    for i in range(10):
        final[1090 + i] = phase_e[i]

    # phase C 在位置 200, 300, 400, 500, 600, 700, 800, 900, 950, 1000
    c_positions = [200, 300, 400, 500, 600, 700, 800, 900, 950, 1000]
    # phase C 的 target 在 50, 150, 250, 350, 450, 550, 650, 750, 800, 850
    c_targets = [50, 150, 250, 350, 450, 550, 650, 750, 800, 850]
    for i in range(10):
        phase_c[i].expected["expected_focus_turn_index"] = c_targets[i]
        final[c_positions[i]] = phase_c[i]

    # phase B 在位置 250, 450, 650, 850, 975
    b_positions = [250, 450, 650, 850, 975]
    for i in range(5):
        final[b_positions[i]] = phase_b[i]

    # phase D 在剩余位置中均匀分布
    d_positions = []
    # 收集所有空位置
    empty_positions = [i for i, slot in enumerate(final) if slot is None]
    # 每 13 个空位置选一个，选 75 个
    step = max(len(empty_positions) // 75, 1)
    for i in range(75):
        idx = min(i * step, len(empty_positions) - 1)
        d_positions.append(empty_positions[idx])
    # 确保不重复
    d_positions = sorted(list(set(d_positions)))[:75]
    for i in range(75):
        final[d_positions[i]] = phase_d[i]

    # 剩余位置填充 phase A，按顺序
    a_idx = 0
    for i in range(1100):
        if final[i] is None:
            final[i] = phase_a[a_idx]
            a_idx += 1
    assert a_idx == 1000, f"Expected 1000 phase A turns, used {a_idx}"

    result = final  # type: ignore

    # 校验总长度 1100
    assert len(result) == 1100, f"Expected 1100 turns, got {len(result)}"

    return result
