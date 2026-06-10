# Demo 与评测清单

## 必测 Query

```text
1. 推荐一款适合油皮的洗面奶，预算100以内
2. 推荐防晒霜，但不要含酒精的，也不要日系品牌
3. 下周去三亚度假，帮我搭配一套从防晒到穿搭的方案
4. 点开主推商品，输入：这个有点贵，有没有100以内的？
5. 点开主推商品，输入：这个适合敏感肌吗？
6. 把第一款加入购物车，把数量改成2
7. 看看购物车，然后下单
```

## 评测指标

| 模块 | 指标 |
|---|---|
| 意图理解 | intent accuracy |
| 约束抽取 | constraint extraction accuracy |
| 反选约束 | must_not violation rate |
| 主推商品 | primary recommendation satisfaction |
| 商品追问 | product_followup success rate |
| 替代商品 | replacement constraint inheritance accuracy |
| 场景组合 | required slot coverage |
| 购物车 | cart operation accuracy |
| 流式体验 | first token / first card / first audio latency |
| 稳定性 | crash-free demo rate |

## Android 验收

```text
1. App 可安装。
2. 聊天页不白屏。
3. text_delta 流式显示。
4. 商品卡片 skeleton 后逐张出现。
5. 主推商品视觉突出。
6. 商品详情浮层可打开。
7. 商品级追问可发送。
8. 替代商品可显示。
9. bundle 可分组显示。
10. 购物车可改数量和下单。
11. 语音输入可用。
12. TTS 可播放并停止。
13. 无网络/后端错误不崩溃。
```

## 答辩表达

```text
我们不是做一个自然语言商品搜索，而是做低压力导购。
系统会先理解用户背后的购买动机，给出一个明确主推商品。
当用户对主推商品不满意时，可以直接在商品详情浮层继续追问。
后端把追问绑定到当前 product_id，并继承原始约束，重新检索替代商品。
这样可以减少用户重复输入，也能避免多轮上下文污染。
```
