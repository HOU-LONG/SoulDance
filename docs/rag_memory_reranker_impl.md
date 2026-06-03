# RAG Memory Cache and Evidence Reranker Implementation

Date: 2026-06-01

Remote branch:

```text
codex/rag-memory-reranker
```

Implementation commit:

```text
8093630 feat: add rag memory cache and evidence reranker
```

Baseline save commit before this work:

```text
d560a65 chore: save qwen start gpu default
```

## Goal

This pass adds two backend capabilities to the SoulDance ShopGuide agent:

1. Structured RAG memory cache for reusing repeated recommendation results.
2. Evidence-level reranking/filtering so noisy user reviews do not mislead the LLM.

The implementation is demo-first: no Redis or external service, no final-answer text cache, and no required Android/WebSocket protocol changes.

## Structured Memory Cache

New module:

```text
backend/app/memory_cache.py
```

The cache stores structured recommendation results, not final generated replies. Each cache row contains:

- normalized retrieval plan key
- product ids
- rank score and tier
- reason
- evidence snippets

The cache key includes:

- intent
- retrieval mode
- category
- hard constraints
- soft preferences
- normalized retrieval query

This prevents unsafe reuse across different hard constraints. For example, `推荐精华，预算100以内` and `推荐精华，预算800以内` produce different keys.

Runtime behavior:

- `ShopGuideAgent.retrieve_and_rank()` checks cache before retriever search.
- On cache hit, ranked products are reconstructed from product ids and revalidated with `hard_filter()`.
- On miss, the normal retriever/ranker path runs and then writes the structured result back to cache.

Default cache is in-memory. Optional JSONL persistence can be enabled with:

```bash
export SHOPGUIDE_MEMORY_CACHE_PATH="cache/shopguide_memory.jsonl"
```

When enabled, cache writes append JSONL rows and startup reloads the latest rows by key.


## Recommendation Memory Cache

The backend now has a higher-level recommendation memory above the existing retrieval/rank cache.

Runtime order:

```text
semantic parse / backend admission / taxonomy
-> recommendation memory exact hit
-> recommendation memory semantic hit
-> retrieval/rank cache
-> normal retriever/ranker/LLM selection
```

`RecommendationMemoryCache` stores structured product decisions, not full final answers:

- normalized query
- taxonomy and hard constraints
- selected product ids and roles
- selected reasons and evidence
- short response summary
- catalog and prompt version markers

On exact or semantic hit, the backend reconstructs selected products, re-runs hard filtering and taxonomy validation, skips retriever/ranker and LLM product selection, then emits normal `product_item` events. The `assistant_state.memory_mode` field reports `exact_hit`, `semantic_hit`, or `miss` for verification UIs.

The first semantic version is intentionally conservative and dependency-free: it only reuses entries with compatible taxonomy and identical hard constraints, using lightweight token overlap as a similarity signal.

## Evidence Reranker

Changed module:

```text
backend/app/knowledge_base.py
```

Product evidence is now split into `EvidenceChunk` objects with:

- `source_type`: `marketing`, `faq`, or `review`
- `rating`
- `query_overlap`
- `field_consistency`
- `noise_score`

The first version uses simple, explainable rules instead of an always-on LLM judge.

Noise score follows the planned shape:

```text
0.4 * cross-category action risk
+ 0.3 * product-field inconsistency
+ 0.2 * weak query relevance
+ 0.1 * constraint conflict text
```

Examples:

- Non-food products with reviews mentioning `吃`, `好吃`, `入口`, `味道`, or `喝` are treated as cross-category risk.
- Food products with beauty terms such as `上脸`, `不卡粉`, `不闷痘`, `肤感`, `补水`, `泛红`, or `刺痛` are treated as cross-category risk.
- Reviews with `noise_score >= 0.6` and weak query overlap are dropped from final evidence.

Important detail: original review data is not deleted or rewritten. The filter only controls which chunks are used as evidence.

## Risk Evidence

Sensitive-skin risk is intentionally preserved.

If the query mentions sensitive skin or barrier concerns, low-rating reviews that mention:

```text
敏感肌 / 泛红 / 刺痛 / 过敏 / 不适 / 起疹
```

can be surfaced as risk evidence. This avoids the old failure mode where official positive copy dominates and user-reported risk disappears.

## Regression Fixes Included

Two observed behavior issues were added to tests and fixed:

1. `不要苹果` now becomes a hard brand exclusion. Apple product cards should not be emitted for that request.
2. `比较敏感` is no longer interpreted as product comparison. Compare mode now requires clearer comparison language such as `比较一下`, `对比`, `哪个更`, or ordinal references like `第一款`.

## Tests Added

New tests in:

```text
tests/test_agent_core.py
```

Coverage includes:

- repeated requests reuse structured cache and avoid a second retriever call
- cache does not cross hard constraints
- noisy towel-style food review is filtered from product evidence
- sensitive-skin negative review remains available as risk evidence
- `不要苹果` does not emit Apple product cards
- cat-food style fresh recommendation does not fall into compare-context response

Verification on `mix_A100`:

```text
env/venv_shopguide_backend/bin/python -m pytest tests/test_agent_core.py tests/test_api.py -q
33 passed, 1 warning in 8.94s
```

Manual smoke verification used a temporary backend on port `18081` with `USE_EMBEDDING=0`.

Smoke result:

- recommendation stream works
- no-match followup recovery works
- cart add/update/checkout works

## Operational Notes

- No API key is written to source, docs, cache, or logs.
- Existing WebSocket event shapes remain compatible.
- `/health` now includes memory cache stats.
- The implementation does not restart the existing `18080` backend process. It was verified through tests and a temporary `18081` process.

## Follow-Up Ideas

1. Add a debug endpoint for evidence diagnostics: kept/dropped chunks and noise reasons.
2. Add offline evaluation cases for each product category.
3. Calibrate thresholds with a small labeled set instead of keeping the first-pass `0.6` risk cutoff forever.
4. Add optional LLM judge only for low-confidence or high-risk cases after collecting threshold metrics.
