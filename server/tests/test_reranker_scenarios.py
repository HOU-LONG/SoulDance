from __future__ import annotations

import pytest

from backend.app.models import RetrievalPlan
from backend.app.rag.reranker_scenarios import (
    RerankScenario,
    detect_low_confidence,
    detect_pre_scenario,
    upgrade_scenario,
)


def _plan(intent: str = "recommend_product", query: str = "shoes") -> RetrievalPlan:
    return RetrievalPlan(intent=intent, retrieval_query=query)


def test_default_when_intent_is_recommend_and_not_refinement():
    assert detect_pre_scenario(_plan()) is RerankScenario.DEFAULT


def test_comparison_when_intent_is_compare_products():
    assert detect_pre_scenario(_plan(intent="compare_products")) is RerankScenario.COMPARISON


def test_comparison_when_intent_is_plain_compare():
    assert detect_pre_scenario(_plan(intent="compare")) is RerankScenario.COMPARISON


def test_refinement_flag_overrides_default():
    assert detect_pre_scenario(_plan(), refinement=True) is RerankScenario.REFINEMENT


def test_comparison_outranks_refinement_when_both_present():
    plan = _plan(intent="compare_products")
    assert detect_pre_scenario(plan, refinement=True) is RerankScenario.COMPARISON


def test_low_confidence_true_when_diff_below_threshold():
    assert detect_low_confidence([0.91, 0.88, 0.40], threshold=0.05) is True


def test_low_confidence_false_when_diff_at_or_above_threshold():
    assert detect_low_confidence([0.91, 0.86, 0.40], threshold=0.05) is False


def test_low_confidence_false_when_fewer_than_two_scores():
    assert detect_low_confidence([0.91], threshold=0.05) is False
    assert detect_low_confidence([], threshold=0.05) is False


def test_upgrade_scenario_preserves_strong_intent():
    upgraded = upgrade_scenario(RerankScenario.COMPARISON, [0.91, 0.90], 0.05)
    assert upgraded is RerankScenario.COMPARISON


def test_upgrade_scenario_raises_default_to_low_confidence():
    upgraded = upgrade_scenario(RerankScenario.DEFAULT, [0.91, 0.90], 0.05)
    assert upgraded is RerankScenario.LOW_CONFIDENCE


def test_upgrade_scenario_keeps_default_when_confident():
    upgraded = upgrade_scenario(RerankScenario.DEFAULT, [0.91, 0.50], 0.05)
    assert upgraded is RerankScenario.DEFAULT