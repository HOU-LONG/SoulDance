from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from backend.app.identity import (
    ANONYMOUS_USER_ID,
    get_current_user_id,
    is_valid_user_id,
)


def _make_request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_get_current_user_id_returns_anonymous_when_header_missing() -> None:
    assert get_current_user_id(_make_request()) == ANONYMOUS_USER_ID


def test_get_current_user_id_reads_x_user_id_header() -> None:
    request = _make_request({"X-User-Id": "demo_user_a"})
    assert get_current_user_id(request) == "demo_user_a"


def test_get_current_user_id_rejects_malformed_header() -> None:
    request = _make_request({"X-User-Id": "Demo User!"})
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(request)
    assert exc.value.status_code == 400
    assert "user_id" in exc.value.detail.lower()


def test_get_current_user_id_rejects_too_long_value() -> None:
    request = _make_request({"X-User-Id": "x" * 65})
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(request)
    assert exc.value.status_code == 400


def test_is_valid_user_id_accepts_lowercase_alnum_underscore() -> None:
    assert is_valid_user_id("demo_user_a")
    assert is_valid_user_id("u1")
    assert is_valid_user_id("a" * 64)


def test_is_valid_user_id_rejects_uppercase_special_or_too_long() -> None:
    assert not is_valid_user_id("Demo")
    assert not is_valid_user_id("user-a")
    assert not is_valid_user_id("")
    assert not is_valid_user_id("a" * 65)