from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionData:
    session_id: str
    username: str
    token: str
    expires_at: int


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionData] = {}

    def create(self, username: str, token: str, expires_at: int) -> SessionData:
        self.cleanup()
        session = SessionData(
            session_id=secrets.token_urlsafe(32),
            username=username,
            token=token,
            expires_at=expires_at,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str | None) -> SessionData | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            return None
        if session.expires_at <= int(time.time()):
            self.delete(session.session_id)
            return None
        return session

    def delete(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)

    def cleanup(self) -> None:
        now = int(time.time())
        with self._lock:
            expired = [sid for sid, session in self._sessions.items() if session.expires_at <= now]
            for sid in expired:
                del self._sessions[sid]

