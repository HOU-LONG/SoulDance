# 以商品为锚点的多轮导购设计说明

## 设计动机

用户在购物时常见的压力不是“找不到商品”，而是：

```text
1. 不知道哪个真正适合自己。
2. 害怕踩雷。
3. 不想在很多结果里比较。
4. 说出需求后还要不断重复约束。
5. 对某个推荐不满意时不知道怎么自然修正。
```

因此，本项目采用“商品为锚点”的多轮导购，而不是普通搜索结果列表。

## 核心流程

```text
用户普通提问
  -> 系统给出主推商品
  -> 用户点击商品卡片
  -> 商品详情 BottomSheet 浮起
  -> 用户围绕当前商品继续问
  -> Android 发送 product_followup + focus_product_id
  -> 后端在当前商品上下文内重新规划检索
  -> 返回解释和替代商品
```

## 前端 UI

### BottomSheet 内容

```text
商品主图
商品名
价格
标签
推荐理由
匹配用户需求的证据
可能不适合的情况
加入购物车
Quick Actions
围绕商品继续问输入框
替代商品区域
```

### Quick Actions

```text
换个更便宜的
换个更清爽的
不要这个品牌
更适合户外
更适合敏感肌
加入购物车
```

## 后端上下文

```json
{
  "session_id": "demo_session_001",
  "active_focus": {
    "focus_type": "product",
    "product_id": "sku_101",
    "origin_constraints": {
      "category": "防晒霜",
      "exclude_ingredients": ["酒精"],
      "exclude_brand_regions": ["日本"]
    },
    "local_constraints": {
      "price_max": 100
    }
  }
}
```

## 关键规则

```text
1. product_followup 必须带 focus_product_id。
2. 替代商品必须继承 origin_constraints。
3. 如果用户的新要求与原约束冲突，后端需要解释并追问。
4. 如果用户切换到另一个商品，focus 切换。
5. 普通输入框不自动继承商品 focus。
```

## 示例

原始请求：

```text
推荐防晒霜，但不要含酒精，也不要日系品牌
```

主推商品：sku_101，价格 129。

用户在详情浮层输入：

```text
这个有点贵，有没有100以内的？
```

后端应理解：

```text
保留：防晒霜、不含酒精、非日系品牌
新增：price <= 100
目标：找替代商品
```

返回：

```text
我保留你原来的排除条件，并把价格限制到 100 元以内，给你换成这款。
```

然后返回 replacement_product。
