from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.app.config import get_settings
from backend.app.eval.long_session_judge import JudgeResult, LongSessionJudge
from backend.app.eval.long_session_templates import ScriptTurn


@pytest.mark.asyncio
async def test_judge_returns_three_raw_results_in_dryrun_mode():
    judge = LongSessionJudge(get_settings(), call_count=3)
    judge._call_once = AsyncMock(
        return_value={"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1, "reason": ""}
    )
    turn = ScriptTurn(phase="A", turn_type="retrieval", query="推荐防晒", expected={})
    result = await judge.judge(turn, "推荐一款防晒霜", ["p1"], {})
    assert isinstance(result, JudgeResult)
    assert result.call_count == 3
    assert len(result.raw) == 3
    assert result.mean == 4.0
    assert result.disagreement == 0.0


@pytest.mark.asyncio
async def test_judge_detects_disagreement():
    judge = LongSessionJudge(get_settings(), call_count=3)
    judge._call_once = AsyncMock(side_effect=[
        {"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1},
        {"hit": 0, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1},
        {"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1},
    ])
    turn = ScriptTurn(phase="A", turn_type="retrieval", query="x", expected={})
    result = await judge.judge(turn, "...", [], {})
    assert result.disagreement > 0


def test_recommend_call_count_low():
    assert LongSessionJudge.recommend_pilot_call_count(0.02) == 1


def test_recommend_call_count_mid():
    assert LongSessionJudge.recommend_pilot_call_count(0.10) == 3


def test_recommend_call_count_high():
    assert LongSessionJudge.recommend_pilot_call_count(0.25) is None
