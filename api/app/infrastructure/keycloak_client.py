from __future__ import annotations

import base64
import json
import threading
import time

import requests
from fastapi import HTTPException
from requests import RequestException

from app.core.settings import settings


class KeycloakClient:
    _cache_lock = threading.Lock()
    _token_cache: dict[tuple[str, str], tuple[str, int]] = {}

    def __init__(self) -> None:
        self._token_url = (
            f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
            "/protocol/openid-connect/token"
        )
        self._client_id = settings.keycloak_client_id
        self._client_secret = settings.keycloak_client_secret
        self._timeout = 8

    def issue_token(self, username: str, password: str) -> str:
        token, _ = self.issue_token_with_exp(username, password)
        return token

    def issue_token_with_exp(self, username: str, password: str) -> tuple[str, int]:
        cache_key = (username, password)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "username": username,
            "password": password,
            "grant_type": "password",
        }
        try:
            response = requests.post(self._token_url, data=payload, timeout=self._timeout)
        except RequestException as exc:
            raise HTTPException(
                status_code=503,
                detail="Keycloak indisponivel no momento",
            ) from exc

        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Falha ao autenticar no Keycloak")

        body = response.json()
        token = body.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Token do Keycloak ausente")

        expires_at = self._extract_exp(token)
        if expires_at is None:
            expires_in = int(body.get("expires_in", 300))
            expires_at = int(time.time()) + expires_in

        with self._cache_lock:
            self._token_cache[cache_key] = (token, expires_at)
        return token, expires_at

    def _get_cached(self, cache_key: tuple[str, str]) -> tuple[str, int] | None:
        with self._cache_lock:
            cached = self._token_cache.get(cache_key)
        if not cached:
            return None

        token, expires_at = cached
        # Keep a small safety window to avoid returning almost-expired tokens.
        if expires_at - int(time.time()) <= 10:
            with self._cache_lock:
                self._token_cache.pop(cache_key, None)
            return None
        return token, expires_at

    @staticmethod
    def _extract_exp(token: str) -> int | None:
        try:
            payload_segment = token.split(".")[1]
            payload_segment += "=" * (-len(payload_segment) % 4)
            payload_json = base64.urlsafe_b64decode(payload_segment.encode("utf-8")).decode(
                "utf-8"
            )
            payload = json.loads(payload_json)
            exp = payload.get("exp")
            if isinstance(exp, int):
                return exp
        except Exception:
            return None
        return None
