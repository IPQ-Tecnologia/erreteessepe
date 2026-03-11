from __future__ import annotations

import json
import threading
import time

import jwt
import requests
from cryptography import x509
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm
from requests import RequestException

from app.core.http_errors import http_error
from app.core.settings import settings

# essa classe serve para verificar se o token jwt que recebi é válido no keycloak que temos externamente
class ExternalJWTVerifier:
    _jwks_lock = threading.Lock()
    _jwks_cache: dict[str, object] = {"keys": {}, "expires_at": 0.0}

    def __init__(self) -> None:
        self._issuer = settings.keycloak_issuer
        self._static_key = self._load_static_key()

    def verify(self, token: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise http_error(
                status_code=401,
                code="external_token_invalid",
                message="Token externo invalido",
            ) from exc

        key = self._resolve_key(header.get("kid"))
        options = {"require": ["exp", "iat", "iss"], "verify_aud": False}

        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=["RS256", "RS384", "RS512"],
                issuer=self._issuer,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise http_error(
                status_code=401,
                code="external_token_invalid",
                message="Token externo invalido",
            ) from exc

        if not isinstance(payload, dict):
            raise http_error(
                status_code=401,
                code="external_token_invalid",
                message="Token externo invalido",
            )
        return payload

    def _resolve_key(self, kid: str | None):
        cached = self._get_cached_key(kid)
        if cached is not None:
            return cached

        try:
            self._refresh_jwks()
        except HTTPException:
            if self._static_key is not None:
                return self._static_key
            raise

        refreshed = self._get_cached_key(kid)
        if refreshed is not None:
            return refreshed
        if self._static_key is not None:
            return self._static_key

        raise http_error(
            status_code=401,
            code="external_token_unknown_key",
            message="Token externo assinado com chave desconhecida",
        )

    @classmethod
    def _get_cached_key(cls, kid: str | None):
        now = time.time()
        with cls._jwks_lock:
            keys = cls._jwks_cache["keys"]
            expires_at = float(cls._jwks_cache["expires_at"])
            if now >= expires_at or not isinstance(keys, dict):
                return None
            if kid:
                return keys.get(kid)
            return next(iter(keys.values()), None)

    @classmethod
    def _refresh_jwks(cls) -> None:
        try:
            response = requests.get(settings.keycloak_jwks_url, timeout=5)
        except RequestException as exc:
            raise http_error(
                status_code=503,
                code="external_jwks_unavailable",
                message="JWKS externo indisponivel",
            ) from exc

        if response.status_code != 200:
            raise http_error(
                status_code=503,
                code="external_jwks_unavailable",
                message="JWKS externo indisponivel",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise http_error(
                status_code=503,
                code="external_jwks_invalid",
                message="JWKS externo invalido",
            ) from exc

        parsed: dict[str, object] = {}
        for item in payload.get("keys", []):
            if not isinstance(item, dict):
                continue
            kid = item.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            parsed[kid] = RSAAlgorithm.from_jwk(json.dumps(item))

        if not parsed:
            raise http_error(
                status_code=503,
                code="external_jwks_invalid",
                message="JWKS externo invalido",
            )

        with cls._jwks_lock:
            cls._jwks_cache = {
                "keys": parsed,
                "expires_at": time.time() + settings.keycloak_jwks_cache_ttl_seconds,
            }

    @staticmethod
    def _load_static_key():
        certificate = settings.keycloak_certificate
        if not certificate:
            return None

        try:
            parsed = x509.load_pem_x509_certificate(
                certificate.replace("\\n", "\n").encode("utf-8")
            )
        except ValueError as exc:
            raise http_error(
                status_code=500,
                code="external_certificate_invalid",
                message="Certificado externo invalido",
            ) from exc

        return parsed.public_key()
