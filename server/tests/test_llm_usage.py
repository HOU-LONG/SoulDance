"""Tests for LLM token usage extraction and ledger.

Task 3 of session context compression plan: capture real provider-reported
token usage so the watermark policy in Task 2 has accurate input.

`LLMUsage.is_authoritative=True` means the value came from the provider and
can drive expensive compression decisions. `is_authoritative=False` means
the value was preflight-estimated and must NOT be the sole trigger for an
LLM summarization call.
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.app.llm_usage import LLMUsage, extract_usage


# ---------------------------------------------------------------------------
# LLMUsage model
# ---------------------------------------------------------------------------


def test_llm_usage_defaults_are_authoritative_with_none_tokens() -> None:
    usage = LLMUsage(call_kind="response")
    assert usage.call_kind == "response"
    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.total_tokens is None
    assert usage.source == "provider"
    assert usage.is_authoritative is True


def test_llm_usage_preflight_marker_is_not_authoritative() -> None:
    usage = LLMUsage(
        call_kind="stream_response",
        total_tokens=2_500,
        source="preflight",
        is_authoritative=False,
    )
    assert usage.is_authoritative is False
    assert usage.source == "preflight"


# ---------------------------------------------------------------------------
# extract_usage — OpenAI-compatible response shapes
# ---------------------------------------------------------------------------


def test_extract_usage_reads_openai_style_response() -> None:
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=80,
            total_tokens=200,
        )
    )
    usage = extract_usage(response, call_kind="response")
    assert usage.call_kind == "response"
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 80
    assert usage.total_tokens == 200
    assert usage.is_authoritative is True
    assert usage.source == "provider"


def test_extract_usage_reads_camelcase_total_tokens() -> None:
    """Some providers (Doubao-compatible variants, certain proxies) emit
    `totalTokens` instead of `total_tokens`. The extractor must tolerate both.
    """
    response = SimpleNamespace(
        usage=SimpleNamespace(
            promptTokens=120,
            completionTokens=80,
            totalTokens=200,
        )
    )
    usage = extract_usage(response, call_kind="selection")
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 80
    assert usage.total_tokens == 200


def test_extract_usage_reads_dict_shaped_usage() -> None:
    """When `usage` is a plain dict (e.g. raw httpx JSON), still extract it."""
    response = SimpleNamespace(
        usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}
    )
    usage = extract_usage(response, call_kind="json")
    assert usage.prompt_tokens == 50
    assert usage.total_tokens == 60


def test_extract_usage_returns_unknown_when_missing() -> None:
    """A response with no usage attribute (some streaming proxies strip it)
    must produce an explicit non-authoritative record, not raise.
    """
    response = SimpleNamespace(choices=[SimpleNamespace(message=None)])
    usage = extract_usage(response, call_kind="stream_response")
    assert usage.call_kind == "stream_response"
    assert usage.total_tokens is None
    assert usage.is_authoritative is False
    assert usage.source == "unknown"


def test_extract_usage_handles_none_response() -> None:
    """Defensive: an upstream tenacity retry that ate the exception could
    surface None — extract_usage must not crash on it.
    """
    usage = extract_usage(None, call_kind="response")
    assert usage.is_authoritative is False
    assert usage.total_tokens is None


def test_extract_usage_partial_fields_keeps_other_keys_none() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(total_tokens=300))
    usage = extract_usage(response, call_kind="response")
    assert usage.total_tokens == 300
    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.is_authoritative is True


# ---------------------------------------------------------------------------
# extract_usage — streaming final chunk
# ---------------------------------------------------------------------------


def test_extract_usage_reads_streaming_final_chunk() -> None:
    """OpenAI-compatible `stream_options={"include_usage": True}` causes the
    final stream chunk to carry the usage object on the chunk itself.
    """
    final_chunk = SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=300,
            completion_tokens=100,
            total_tokens=400,
        ),
    )
    usage = extract_usage(final_chunk, call_kind="stream_response")
    assert usage.total_tokens == 400
    assert usage.is_authoritative is True


def test_extract_usage_intermediate_chunk_has_no_usage() -> None:
    """Mid-stream delta chunks usually have no usage; extractor returns the
    same non-authoritative fallback rather than guessing.
    """
    delta_chunk = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))]
    )
    usage = extract_usage(delta_chunk, call_kind="stream_response")
    assert usage.is_authoritative is False
    assert usage.total_tokens is None


# ---------------------------------------------------------------------------
# Usage ledger on the LLM client
# ---------------------------------------------------------------------------


def test_record_usage_writes_to_last_usage_by_call_kind(monkeypatch) -> None:
    """The client side records the most recent authoritative usage per call
    kind so the agent lifecycle can read it after each turn.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key-for-fake-init")
    from backend.app.config import get_settings
    from backend.app.llm_client import DoubaoLLMClient

    get_settings.cache_clear()
    try:
        settings = get_settings()
        client = DoubaoLLMClient(settings)
    finally:
        get_settings.cache_clear()

    usage = LLMUsage(call_kind="response", total_tokens=400)
    client.record_usage(usage)
    recorded = client.last_usage_by_call_kind["response"]
    assert recorded.total_tokens == 400
    assert recorded.is_authoritative is True


def test_record_usage_preflight_does_not_overwrite_authoritative(monkeypatch) -> None:
    """Spec principle 4: an authoritative provider value must not be silently
    replaced by a preflight estimate that arrives later.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from backend.app.config import get_settings
    from backend.app.llm_client import DoubaoLLMClient

    get_settings.cache_clear()
    try:
        settings = get_settings()
        client = DoubaoLLMClient(settings)
    finally:
        get_settings.cache_clear()

    client.record_usage(LLMUsage(call_kind="response", total_tokens=400))
    client.record_usage(
        LLMUsage(
            call_kind="response",
            total_tokens=200,
            source="preflight",
            is_authoritative=False,
        )
    )
    assert client.last_usage_by_call_kind["response"].total_tokens == 400
