from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass

from app.core.http_errors import http_error
from app.infrastructure.redis_client import RedisError, redis_client


WHEP_SESSION_PREFIX = "whep_session:"


@dataclass(frozen=True)
class WHEPSession:
    session_id: str
    subject: str
    device_name: str
    upstream_url: str
    expires_at: float


class WHEPSessionStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl_seconds = max(60, ttl_seconds)

    def create(self, subject: str, device_name: str, upstream_url: str) -> WHEPSession:
        now = time.time()
        session = WHEPSession(
            session_id=secrets.token_urlsafe(24),
            subject=subject,
            device_name=device_name,
            upstream_url=upstream_url,
            expires_at=now + self._ttl_seconds,
        )
        self._set(
            session.session_id,
            {
                "subject": session.subject,
                "device_name": session.device_name,
                "upstream_url": session.upstream_url,
                "expires_at": session.expires_at,
            },
            self._ttl_seconds,
        )
        return session

    def get(self, session_id: str | None) -> WHEPSession | None:
        if not session_id:
            return None
        payload = self._get(session_id)
        if payload is None:
            return None
        session = WHEPSession(
            session_id=session_id,
            subject=str(payload.get("subject") or ""),
            device_name=str(payload.get("device_name") or ""),
            upstream_url=str(payload.get("upstream_url") or ""),
            expires_at=float(payload.get("expires_at") or 0),
        )
        if session.expires_at <= time.time():
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
                code="whep_session_store_unavailable",
                message="WHEP session store indisponivel.",
            ) from exc

    def _set(self, session_id: str, payload: dict[str, object], ttl_seconds: int) -> None:
        client = self._client()
        try:
            client.set(self._key(session_id), json.dumps(payload), ex=max(1, ttl_seconds))
        except RedisError as exc:
            raise http_error(
                status_code=503,
                code="whep_session_store_unavailable",
                message="WHEP session store indisponivel.",
            ) from exc

    def _get(self, session_id: str) -> dict[str, object] | None:
        client = self._client()
        try:
            raw = client.get(self._key(session_id))
        except RedisError as exc:
            raise http_error(
                status_code=503,
                code="whep_session_store_unavailable",
                message="WHEP session store indisponivel.",
            ) from exc
        if raw is None:
            return None
        try:
            return json.loads(redis_client.decode(raw))
        except json.JSONDecodeError as exc:
            self.delete(session_id)
            raise http_error(
                status_code=503,
                code="whep_session_store_invalid",
                message="WHEP session store invalido.",
            ) from exc

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{WHEP_SESSION_PREFIX}{session_id}"

    @staticmethod
    def _client():
        client = redis_client.get()
        if client is None:
            raise http_error(
                status_code=503,
                code="whep_session_store_unavailable",
                message="WHEP session store indisponivel.",
            )
        return client
