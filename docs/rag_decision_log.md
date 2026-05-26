# ShopGuide RAG Decision Log

## 2026-05-25 Interaction Naturalness Pass

Goal: make the backend behave more like a low-pressure shopping guide without breaking the existing Android contract.

## Decisions

- Keep hard constraints deterministic. Negative requirements such as `不要含酒精` and `不要日系品牌` remain hard filters.
- Add a small interaction policy in the backend instead of relying on free-form LLM behavior.
- Ask clarification only for high-risk vague requests. Example: `推荐一款手机` asks whether the user values camera, battery, or value.
- Stream product cards earlier. The backend sends one deterministic understanding sentence, then product cards, then grounded explanation.
- Keep new events optional. Android can progressively render `quick_actions`, `comparison_result`, and bundle events.
- Resolve cart and comparison references from session state, not from the LLM.

## Verification Scenarios

- `推荐防晒霜，但不要含酒精的，也不要日系品牌`
- `推荐一款手机`
- `推荐防晒霜` then `第一款和第二款哪个更适合油皮？`
- `下周去三亚度假，帮我搭配一套从防晒到穿搭的方案`
- `把刚才那款加到购物车` then `数量改成2`
- No-match recovery with an impossible budget.

