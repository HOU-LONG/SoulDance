import os

import pytest

from backend.app.config import Settings, get_settings


def test_settings_default_voice_preset():
    s = Settings()
    assert "calm_female" in s.voice_preset
    assert "energetic_male" in s.voice_preset


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("TTS_BASE_URL", "http://tts.example.com:8080")
    monkeypatch.setenv("STT_BASE_URL", "http://stt.example.com:9090")
    monkeypatch.setenv("TTS_ENABLED", "false")
    monkeypatch.setenv("STT_ENABLED", "0")
    s = get_settings()
    assert s.tts_base_url == "http://tts.example.com:8080"
    assert s.stt_base_url == "http://stt.example.com:9090"
    assert s.tts_enabled is False
    assert s.stt_enabled is False
