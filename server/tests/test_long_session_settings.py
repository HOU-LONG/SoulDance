from __future__ import annotations

import os

import pytest

from backend.app.config import Settings, get_settings


def test_default_eval_switches_keep_production_behavior():
    settings = Settings()
    assert settings.eval_disable_window_truncation is False
    assert settings.eval_disable_structured_snapshot is False
    assert settings.eval_disable_recommendation_memory is False
    assert settings.eval_disable_rank_cache is False
    assert settings.eval_force_trim_token_budget == 25000


def test_env_overrides_eval_switches(monkeypatch):
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION", "1")
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT", "true")
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY", "yes")
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_RANK_CACHE", "on")
    monkeypatch.setenv("SHOPGUIDE_EVAL_FORCE_TRIM_TOKEN_BUDGET", "12345")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.eval_disable_window_truncation is True
    assert settings.eval_disable_structured_snapshot is True
    assert settings.eval_disable_recommendation_memory is True
    assert settings.eval_disable_rank_cache is True
    assert settings.eval_force_trim_token_budget == 12345


def test_env_default_unset_returns_false(monkeypatch):
    for key in (
        "SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION",
        "SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT",
        "SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY",
        "SHOPGUIDE_EVAL_DISABLE_RANK_CACHE",
        "SHOPGUIDE_EVAL_FORCE_TRIM_TOKEN_BUDGET",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.eval_disable_window_truncation is False
    assert settings.eval_force_trim_token_budget == 25000
