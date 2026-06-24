"""Session context compression — watermark policy and stable part decisions.

This module is the deterministic core of the compression layer:

- `choose_watermark_level` maps real token usage to one of five policy levels.
- `stable_part_id` produces a session-scoped id whose bytes never change.
- `is_protected_part` answers "is this part allowed to be compressed".
  The 8000-token / latest-3-turns recency budget is enforced upstream when
  the protected-window builder marks parts as `is_recent`; this helper does
  NOT re-filter recent parts by size (Spec principle 6, Plan review fix).
- `apply_or_reuse_decision` enforces Spec principle 7: once a `part_id` has
  a placeholder decision, the exact same replacement bytes are returned on
  every later turn, so prompt caches stay valid.

The runtime LLM context limit is owned by `Settings.llm_context_limit` and
must be passed in here — the data model intentionally defaults to 0 so that
misconfiguration cannot be silently masked by a hard-coded production value.
"""
from __future__ import annotations

from typing import Callable, Protocol

from .models import CompressionPartDecision, SessionCompressionState


# ---------------------------------------------------------------------------
# Watermark policy
# ---------------------------------------------------------------------------

# Level names are stable strings; persisted in SessionCompressionState and
# read by the agent lifecycle. Don't rename without a migration.
LEVEL_MAINTAIN = "maintain"
LEVEL_CHEAP_DETERMINISTIC = "cheap_deterministic"
LEVEL_STRUCTURED_COMPACTION = "structured_compaction"
LEVEL_INCREMENTAL_SUMMARY = "incremental_summary"
LEVEL_EMERGENCY_FIT = "emergency_fit"


def choose_watermark_level(total_tokens: int, limit: int) -> str:
    """Map real provider-reported token usage to a compression level.

    The thresholds (50/70/85/95) are deliberately conservative — Spec
    principle 1 prefers continuous small actions over cliff-edge failures.

    A non-positive `limit` is treated as emergency: the caller is
    misconfigured and the safest response is to refuse expensive history
    construction so the failure surfaces, not to silently divide by zero.
    """
    if limit <= 0:
        return LEVEL_EMERGENCY_FIT
    ratio = total_tokens / limit
    if ratio >= 0.95:
        return LEVEL_EMERGENCY_FIT
    if ratio >= 0.85:
        return LEVEL_INCREMENTAL_SUMMARY
    if ratio >= 0.70:
        return LEVEL_STRUCTURED_COMPACTION
    if ratio >= 0.50:
        return LEVEL_CHEAP_DETERMINISTIC
    return LEVEL_MAINTAIN


# ---------------------------------------------------------------------------
# Stable part ids
# ---------------------------------------------------------------------------


def stable_part_id(
    session_id: str, turn_index: int, role: str, ordinal: int
) -> str:
    """Build a deterministic, session-scoped id for a prompt part.

    The id is part of the persisted compression ledger key — any change to
    this format is a data migration, not a refactor.
    """
    return f"{session_id}:{turn_index}:{role}:{ordinal}"


# ---------------------------------------------------------------------------
# Protected-window predicate
# ---------------------------------------------------------------------------


class _PartLike(Protocol):
    """Structural type for parts the policy can see.

    The protected-window builder upstream populates `is_recent` /
    `is_current_user_message`; this protocol keeps the policy decoupled from
    whatever concrete part type ends up in the assembler.
    """

    part_id: str
    token_count: int
    turn_index: int
    is_recent: bool
    is_current_user_message: bool


def is_protected_part(part: _PartLike) -> bool:
    """Decide whether `part` is allowed to be compressed.

    Spec principles 5 and 6:
      - The current user message is always protected, regardless of size
        (a huge user paste must not be truncated for compression).
      - Recent parts are always protected. The 8000-token / latest-3-turns
        budget is applied UPSTREAM when marking `is_recent`. This predicate
        must not re-filter recent parts by `token_count` — doing so would
        cause a 9000-token recent message to slip out of the protected window.
    """
    return bool(part.is_current_user_message or part.is_recent)


# ---------------------------------------------------------------------------
# Byte-stable decision ledger
# ---------------------------------------------------------------------------


def apply_or_reuse_decision(
    state: SessionCompressionState,
    part: _PartLike,
    replacement_factory: Callable[[_PartLike], str],
) -> str:
    """Return the placeholder text for `part`, creating it once if missing.

    Once a `part_id` has a stored decision, the persisted `replacement_text`
    wins forever — even if `replacement_factory` is later updated. This is
    what makes Spec principle 7 (monotonic boundaries / no sliding-window
    re-stubbing) work: prompt cache keys for old turns stay byte-stable.
    """
    existing = state.decisions.get(part.part_id)
    if existing is not None:
        return existing.replacement_text
    replacement_text = replacement_factory(part)
    state.decisions[part.part_id] = CompressionPartDecision(
        part_id=part.part_id,
        action="placeholder",
        replacement_text=replacement_text,
        original_token_count=part.token_count,
        compressed_token_count=max(1, len(replacement_text) // 3),
        created_turn=part.turn_index,
    )
    return replacement_text
