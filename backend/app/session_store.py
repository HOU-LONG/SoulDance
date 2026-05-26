from __future__ import annotations

from .models import SessionContext


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, SessionContext] = {}

    def get(self, session_id: str) -> SessionContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionContext(session_id=session_id)
        return self._sessions[session_id]
