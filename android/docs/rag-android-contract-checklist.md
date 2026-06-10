# RAG Android Contract Checklist

## Ownership

- RAG/cache owner: Huiruize
- Data governance owner: Houlong
- Android/UI owner: Houlong

## Required Stream Metadata

Every RAG-backed response should expose these fields in backend trace logs or stream metadata:

```text
cache_status: hit | miss | bypass
model_name: doubao | chatgpt | other
retrieval_version: string
cache_key_debug: non-secret string or hash
first_token_ms: number
first_card_ms: number
primary_product_id: string
```

## Product Payload Rules

Streamed product payloads must include:

```text
product_id
title or name
price
image_url or image_path
reason
generated_tags
tags fallback
role: primary | alternative
evidence and risk fields when available
```

`generated_tags` should be evidence-backed and product-specific. Android falls back to `tags` only when generated tags are unavailable.

## Focused Follow-Up Rules

Android request:

```json
{
  "type": "product_followup",
  "session_id": "demo_session_001",
  "focus_product_id": "p_beauty_001",
  "message": "这个适合敏感肌吗？"
}
```

Backend response events:

```text
focus_text_delta
replacement_product
focus_done
error
```

The replacement product must inherit the original user constraints plus the focused follow-up constraint.

## Review Governance Rules

RAG chunks must exclude reviews classified as:

```text
irrelevant
malicious
unsafe
low_signal
```

Product-relevant negative reviews must remain available as risk evidence.
