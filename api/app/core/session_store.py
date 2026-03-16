from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass

from app.core.http_errors import http_error
from app.infrastructure.redis_client import RedisError, redis_client


SESSION_PREFIX = "stream_session:"


@dataclass(frozen=True)
class SessionData:
    session_id: str
    username: str
    token: str
    expires_at: int


class SessionStore:
    def create(self, username: str, token: str, expires_at: int) -> SessionData:
        session = SessionData(
            session_id=secrets.token_urlsafe(32),
            username=username,
            token=token,
            expires_at=expires_at,
        )
        ttl_seconds = max(1, session.expires_at - int(time.time()))
        self._set(
            session.session_id,
            {
                "username": session.username,
                "token": session.token,
                "expires_at": session.expires_at,
            },
            ttl_seconds,
        )
        return session

    def get(self, session_id: str | None) -> SessionData | None:
        if not session_id:
            return None
        payload = self._get(session_id)
        if payload is None:
            return None
        session = SessionData(
            session_id=session_id,
            username=str(payload.get("username") or ""),
            token=str(payload.get("token") or ""),
            expires_at=int(payload.get("expires_at") or 0),
        )
        if session.expires_at <= int(time.time()):
            self.delete(session.session_id)
            return None
        return session

    def delete(self, session_id: str | None) -> None:
        if not session_id:
            return
        client = self._client()
        try:
            client.delete(self._key(session_id))
        except RedisError as exc:
            raise http_error(
                status_code=503,
                code="session_store_unavailable",
                message="Session store indisponivel.",
            ) from exc

    def cleanup(self) -> None:
        return None

    def _set(self, session_id: str, payload: dict[str, object], ttl_seconds: int) -> None:
        client = self._client()
        try:
            client.set(self._key(session_id), json.dumps(payload), ex=ttl_seconds)
        except RedisError as exc:
            raise http_error(
                status_code=503,
                code="session_store_unavailable",
                message="Session store indisponivel.",
            ) from exc

    def _get(self, session_id: str) -> dict[str, object] | None:
        client = self._client()
        try:
            raw = client.get(self._key(session_id))
        except RedisError as exc:
            raise http_error(
                status_code=503,
                code="session_store_unavailable",
                message="Session store indisponivel.",
            ) from exc
        if raw is None:
            return None
        try:
            return json.loads(redis_client.decode(raw))
        except json.JSONDecodeError as exc:
            self.delete(session_id)
            raise http_error(
                status_code=503,
                code="session_store_invalid",
                message="Session store invalido.",
            ) from exc

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{SESSION_PREFIX}{session_id}"

    @staticmethod
    def _client():
        client = redis_client.get()
        if client is None:
            raise http_error(
                status_code=503,
                code="session_store_unavailable",
                message="Session store indisponivel.",
            )
        return client
