"""Reranker scenario detection. Pure logic, no I/O."""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from ..models import RetrievalPlan


class RerankScenario(str, Enum):
    DEFAULT = "default"
    COMPARISON = "comparison"
    LOW_CONFIDENCE = "low_confidence"
    REFINEMENT = "refinement"


_COMPARISON_INTENTS = {"compare_products", "compare"}


def detect_pre_scenario(plan: RetrievalPlan, *, refinement: bool = False) -> RerankScenario:
    """Decide the scenario before cross-encoder scores are available.

    Priority: COMPARISON > REFINEMENT > DEFAULT. LOW_CONFIDENCE is only
    evaluated after cross-encoder produces scores (see upgrade_scenario).
    """
    if plan.intent in _COMPARISON_INTENTS:
        return RerankScenario.COMPARISON
    if refinement:
        return RerankScenario.REFINEMENT
    return RerankScenario.DEFAULT


def detect_low_confidence(scores: Sequence[float], threshold: float) -> bool:
    """True iff |scores[0] - scores[1]| < threshold."""
    if len(scores) < 2:
        return False
    return abs(scores[0] - scores[1]) < threshold


def upgrade_scenario(
    pre: RerankScenario,
    scores: Sequence[float],
    threshold: float,
) -> RerankScenario:
    """Upgrade DEFAULT to LOW_CONFIDENCE if cross-encoder scores cluster.

    Strong intents (COMPARISON / REFINEMENT) are preserved as-is.
    """
    if pre is not RerankScenario.DEFAULT:
        return pre
    if detect_low_confidence(scores, threshold):
        return RerankScenario.LOW_CONFIDENCE
    return RerankScenario.DEFAULT