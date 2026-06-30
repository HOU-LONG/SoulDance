"""Normalize LLM provider token usage across response shapes.

Spec principle 4: trigger decisions must use provider-reported usage when
available; approximate counts are allowed only for internal ordering and
preflight streaming fallback.

This module gives the rest of the backend a single typed surface to read
that info from:

- `LLMUsage` — the normalized record. `is_authoritative=False` marks values
  that came from a preflight estimate or were missing entirely; the watermark
  policy MUST NOT treat them as the sole trigger for an LLM summarization
  call.
- `extract_usage(response_or_chunk, call_kind)` — pulls `usage` out of an
  OpenAI-compatible response or a final stream chunk. Tolerates both
  `total_tokens`/`totalTokens` casing and the dict-shaped variant that
  some httpx-raw providers emit. Missing usage returns a non-authoritative
  fallback rather than raising.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LLMUsage(BaseModel):
    """A single normalized usage record.

    `source` is one of:
      - `provider`  — read from the response/chunk `usage` payload.
      - `preflight` — estimated locally before the call; non-authoritative.
      - `unknown`   — neither was available; non-authoritative.
    """

    call_kind: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    source: str = "provider"
    is_authoritative: bool = True


# Field name candidates in priority order — first hit wins.
_PROMPT_KEYS = ("prompt_tokens", "promptTokens")
_COMPLETION_KEYS = ("completion_tokens", "completionTokens")
_TOTAL_KEYS = ("total_tokens", "totalTokens")


def _read_int(container: Any, keys: tuple[str, ...]) -> int | None:
    if container is None:
        return None
    if isinstance(container, dict):
        for key in keys:
            value = container.get(key)
            if value is not None:
                return int(value)
        return None
    for key in keys:
        value = getattr(container, key, None)
        if value is not None:
            return int(value)
    return None


def extract_usage(response_or_chunk: Any, call_kind: str) -> LLMUsage:
    """Pull a normalized `LLMUsage` out of a provider response or chunk.

    Returns a non-authoritative `source="unknown"` record when usage is
    absent — callers should never treat that as a real measurement.
    """
    if response_or_chunk is None:
        return LLMUsage(call_kind=call_kind, source="unknown", is_authoritative=False)

    usage_obj = getattr(response_or_chunk, "usage", None)
    if usage_obj is None and isinstance(response_or_chunk, dict):
        usage_obj = response_or_chunk.get("usage")
    if usage_obj is None:
        return LLMUsage(call_kind=call_kind, source="unknown", is_authoritative=False)

    prompt = _read_int(usage_obj, _PROMPT_KEYS)
    completion = _read_int(usage_obj, _COMPLETION_KEYS)
    total = _read_int(usage_obj, _TOTAL_KEYS)
    if prompt is None and completion is None and total is None:
        return LLMUsage(call_kind=call_kind, source="unknown", is_authoritative=False)

    return LLMUsage(
        call_kind=call_kind,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        source="provider",
        is_authoritative=True,
    )
