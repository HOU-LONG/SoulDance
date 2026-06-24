from __future__ import annotations

from collections import Counter

import pytest

from backend.app.data_loader import load_products
from backend.app.eval.long_session_templates import (
    ScriptTurn,
    build_long_session_script,
)


@pytest.fixture(scope="module")
def products():
    from pathlib import Path
    dataset_path = Path("..") / "ecommerce_agent_dataset"
    return load_products(dataset_path)


def test_script_total_turn_count(products):
    script = build_long_session_script(products)
    assert len(script) == 1100


def test_phase_counts(products):
    script = build_long_session_script(products)
    counter = Counter(t.phase for t in script)
    assert counter["A"] == 1000
    assert counter["B"] == 5
    assert counter["C"] == 10
    assert counter["D"] == 75
    assert counter["E"] == 10


def test_turn_type_diversity(products):
    script = build_long_session_script(products)
    types = {t.turn_type for t in script}
    expected = {
        "retrieval",
        "followup_factual",
        "comparison",
        "cart_action",
        "long_range_reference",
        "constraint_handling",
        "adversarial_reference",
        "adversarial_constraint",
    }
    assert expected.issubset(types)


def test_adversarial_subtypes_distribution(products):
    script = build_long_session_script(products)
    d_turns = [t for t in script if t.phase == "D"]
    counter = Counter(t.adversarial_subtype for t in d_turns)
    assert counter["D1"] == 15
    assert counter["D2"] == 10
    assert counter["D3"] == 10
    assert counter["D4"] == 10
    assert counter["D5"] == 15
    assert counter["D6"] == 15


def test_long_range_reference_targets_earlier_turn(products):
    script = build_long_session_script(products)
    c_turns = [(i, t) for i, t in enumerate(script) if t.phase == "C"]
    for i, t in c_turns:
        target_turn = t.expected.get("expected_focus_turn_index")
        assert target_turn is not None
        # 指代的 turn 必须 >= 100 轮之前
        assert i - target_turn >= 100


def test_script_is_deterministic(products):
    s1 = build_long_session_script(products, seed=42)
    s2 = build_long_session_script(products, seed=42)
    assert [t.model_dump() for t in s1] == [t.model_dump() for t in s2]


def test_seed_changes_query_template_choices(products):
    s1 = build_long_session_script(products, seed=1)
    s2 = build_long_session_script(products, seed=2)
    queries_1 = [t.query for t in s1]
    queries_2 = [t.query for t in s2]
    assert queries_1 != queries_2
