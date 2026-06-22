from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:16]}"


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:12]}"


@dataclass
class RealtimeEnvelope:
    session_id: str
    trace_id: str = field(default_factory=new_trace_id)
    message_id: str = field(default_factory=new_message_id)
    seq: int = 0

    def ack(self) -> dict[str, Any]:
        return self._with_meta(
            {
                "type": "ack",
                "message_id": self.message_id,
                "payload": {"state": "received"},
            }
        )

    def wrap(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("message_id", self.message_id)
        return self._with_meta(payload)

    def _with_meta(self, event: dict[str, Any]) -> dict[str, Any]:
        event.setdefault("trace_id", self.trace_id)
        event.setdefault("session_id", self.session_id)
        event.setdefault("timestamp", utc_now_iso())
        event["seq"] = self.seq
        self.seq += 1
        return event
