# RAG Cache Pilot Report

## Owners

```text
RAG owner:
Data governance owner: Houlong
Android/UI owner: Houlong
Backend endpoint/date:
Dataset version:
```

## Baseline

```text
Android unit tests:
Android debug build:
Data governance tests:
Known baseline issues:
```

## Pilot Measurements

| query | model | cache_status | first_token_ms | first_card_ms | primary_product_id | focus_product_id | android_result | notes |
|---|---|---:|---:|---:|---|---|---|---|
| 推荐一款适合油皮的洗面奶，预算100以内 |  |  |  |  |  |  |  |  |
| 推荐防晒霜，但不要含酒精，也不要日系品牌 |  |  |  |  |  |  |  |  |
| 下周去三亚度假，帮我搭配一套从防晒到穿搭的方案 |  |  |  |  |  |  |  |  |
| 这个有点贵，有没有100以内的？ |  |  |  |  |  |  |  |  |
| 这个适合敏感肌吗？ |  |  |  |  |  |  |  |  |

## Acceptance

- Cache metadata is present for every RAG response.
- Primary product id in backend trace matches Android UI.
- Focused follow-up request includes `focus_product_id`.
- Replacement product appears in the bottom sheet flow.
- Android production mode does not use local recommendation fallback.
- Product cards show generated tags when available.
- Malicious or irrelevant reviews are excluded from RAG chunks.

## Sign-Off

```text
Backend owner:
Android owner:
Date:
Known issues:
Decision: pass / pass with issues / fail
```
