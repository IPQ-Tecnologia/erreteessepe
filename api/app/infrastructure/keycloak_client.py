from __future__ import annotations

import base64
import json
import logging
import threading
import time

import requests
from fastapi import HTTPException
from requests import RequestException

from app.core.settings import settings

logger = logging.getLogger(__name__)


class KeycloakClient:
    _cache_lock = threading.Lock()
    _token_cache: dict[tuple[str, str], tuple[str, int]] = {}
    _jwks_lock = threading.Lock()
    _jwks_kids: set[str] = set()
    _jwks_cached_until: float = 0.0

    def __init__(self) -> None:
        self._token_url = (
            f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
            "/protocol/openid-connect/token"
        )
        self._jwks_url = (
            f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
            "/protocol/openid-connect/certs"
        )
        self._client_id = settings.keycloak_client_id
        self._client_secret = settings.keycloak_client_secret
        self._timeout = 8
        self._max_attempts = 4
        self._jwks_cache_ttl_seconds = 30

    def issue_token(self, username: str, password: str) -> str:
        token, _ = self.issue_token_with_exp(username, password)
        return token

    def issue_token_with_exp(self, username: str, password: str) -> tuple[str, int]:
        cache_key = (username, password)
        cached = self._get_cached(cache_key)
        if cached:
            cached_token, _ = cached
            if self._kid_is_known(cached_token):
                return cached
            # Keycloak likely rotated keys, cached token became unverifiable.
            with self._cache_lock:
                self._token_cache.pop(cache_key, None)

        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "username": username,
            "password": password,
            "grant_type": "password",
        }
        response = self._request_token_with_retry(payload)
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Falha ao autenticar no Keycloak")

        body = response.json()
        token = body.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Token do Keycloak ausente")

        # In rare startup races, Keycloak can mint a token before JWKS propagation.
        # Retry once to return a token whose kid is already published.
        if not self._kid_is_known(token):
            response = self._request_token_with_retry(payload)
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

    def _request_token_with_retry(self, payload: dict[str, str]) -> requests.Response:
        delay_seconds = 0.6
        last_error: RequestException | None = None

        for attempt in range(self._max_attempts):
            try:
                response = requests.post(self._token_url, data=payload, timeout=self._timeout)
            except RequestException as exc:
                last_error = exc
                logger.warning(
                    "Keycloak token request failed on attempt %s/%s",
                    attempt + 1,
                    self._max_attempts,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
                if attempt == self._max_attempts - 1:
                    break
                time.sleep(delay_seconds)
                delay_seconds *= 1.8
                continue

            # Retry temporary server-side failures that happen during startup.
            if response.status_code in (502, 503, 504) and attempt < self._max_attempts - 1:
                logger.warning(
                    "Keycloak token request returned retryable status=%s on attempt %s/%s",
                    response.status_code,
                    attempt + 1,
                    self._max_attempts,
                )
                time.sleep(delay_seconds)
                delay_seconds *= 1.8
                continue
            return response

        raise HTTPException(
            status_code=503,
            detail="Keycloak indisponivel no momento",
        ) from last_error

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

    @staticmethod
    def _extract_kid(token: str) -> str | None:
        try:
            header_segment = token.split(".")[0]
            header_segment += "=" * (-len(header_segment) % 4)
            header_json = base64.urlsafe_b64decode(header_segment.encode("utf-8")).decode("utf-8")
            header = json.loads(header_json)
            kid = header.get("kid")
            if isinstance(kid, str) and kid:
                return kid
        except Exception:
            return None
        return None

    def _kid_is_known(self, token: str) -> bool:
        kid = self._extract_kid(token)
        if not kid:
            return True
        now = time.time()
        with self._jwks_lock:
            if now < self._jwks_cached_until and self._jwks_kids:
                return kid in self._jwks_kids

        try:
            response = requests.get(self._jwks_url, timeout=self._timeout)
        except RequestException as exc:
            logger.warning(
                "Keycloak JWKS fetch failed while checking token kid",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            # If JWKS is temporarily unreachable, don't fail token issuance here.
            return True
        if response.status_code != 200:
            logger.warning(
                "Keycloak JWKS fetch returned status=%s while checking token kid",
                response.status_code,
            )
            return True

        try:
            keys = response.json().get("keys", [])
        except ValueError as exc:
            logger.warning(
                "Keycloak JWKS response was not valid JSON while checking token kid",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            return True
        if not isinstance(keys, list):
            return True
        known_kids: set[str] = set()
        for item in keys:
            if isinstance(item, dict):
                item_kid = item.get("kid")
                if isinstance(item_kid, str):
                    known_kids.add(item_kid)
        with self._jwks_lock:
            self._jwks_kids = known_kids
            self._jwks_cached_until = time.time() + self._jwks_cache_ttl_seconds
        return kid in known_kids
