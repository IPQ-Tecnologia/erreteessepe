from __future__ import annotations

import base64
import hashlib
from threading import Lock
from time import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.settings import settings


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

# classe para emitir o token jwt para consumo do mediamtx e uso do usuário ao se conectar no stream
class MediaMTXTokenService:
    _lock = Lock()
    _private_key = None
    _public_key = None
    _kid: str | None = None

    def issue_viewer_token(self, subject: str, permissions: list[dict[str, str]]) -> str:
        return self._issue_token(
            subject=subject,
            permissions=permissions,
            ttl_seconds=settings.mediamtx_jwt_ttl_seconds,
        )

    def issue_api_token(self) -> str:
        return self._issue_token(
            subject=settings.mediamtx_admin_subject,
            permissions=[{"action": "api", "path": ""}],
            ttl_seconds=settings.mediamtx_api_token_ttl_seconds,
        )

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        _, public_key, kid = self._material()
        numbers = public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": kid,
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            ]
        }

    def _issue_token(
        self,
        subject: str,
        permissions: list[dict[str, str]],
        ttl_seconds: int,
    ) -> str:
        private_key, _, kid = self._material()
        now = int(time())
        payload = {
            "iss": settings.mediamtx_jwt_issuer,
            "sub": subject,
            "iat": now,
            "exp": now + max(5, ttl_seconds),
            "mediamtx_permissions": permissions,
        }
        return jwt.encode(
            payload,
            private_key,
            algorithm="RS256",
            headers={"kid": kid},
        )

    @classmethod
    def _material(cls):
        with cls._lock:
            if cls._private_key is not None and cls._public_key is not None and cls._kid:
                return cls._private_key, cls._public_key, cls._kid

            private_key = cls._load_or_generate_private_key()
            public_key = private_key.public_key()
            kid = settings.mediamtx_jwt_kid or cls._derive_kid(public_key)

            cls._private_key = private_key
            cls._public_key = public_key
            cls._kid = kid
            return cls._private_key, cls._public_key, cls._kid

    @staticmethod
    def _load_or_generate_private_key():
        pem = settings.mediamtx_jwt_private_key
        if pem:
            print("Loading MediaMTX JWT private key from environment variable.")
            print(f"pem: {pem}")
        else:
            print("No MediaMTX JWT private key in environment variable.")
        print(f"MediaMTX JWT private key path: {settings.mediamtx_jwt_private_key_path}")
        if not pem and settings.mediamtx_jwt_private_key_path:
            print("Attempting to load MediaMTX JWT private key from file.")
            with open(settings.mediamtx_jwt_private_key_path, "rb") as handle:
                pem = handle.read().decode("utf-8")

        if pem:
            print("MediaMTX JWT private key loaded successfully.")
            return serialization.load_pem_private_key(
                pem.replace("\\n", "\n").encode("utf-8"),
                password=None,
            )

        print("No MediaMTX JWT private key found. Generating new RSA key pair.")
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @staticmethod
    def _derive_kid(public_key) -> str:
        der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(der).hexdigest()[:16]
