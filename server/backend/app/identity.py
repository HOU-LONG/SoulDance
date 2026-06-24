"""User identity transport — single source for tenant attribution.

A request without `X-User-Id` resolves to `ANONYMOUS_USER_ID` (Spec
principle 4). Malformed values fail loud with HTTP 400 so client bugs
cannot silently corrupt the ledger (Spec principle 8).
"""
from __future__ import annotations

import re

from fastapi import HTTPException, Request

ANONYMOUS_USER_ID = "anonymous"
_USER_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def is_valid_user_id(value: str) -> bool:
    return bool(_USER_ID_RE.fullmatch(value))


def get_current_user_id(request: Request) -> str:
    raw = request.headers.get("X-User-Id")
    if raw is None:
        return ANONYMOUS_USER_ID
    if not is_valid_user_id(raw):
        raise HTTPException(
            status_code=400,
            detail="Invalid X-User-Id header: user_id must match ^[a-z0-9_]{1,64}$",
        )
    return raw