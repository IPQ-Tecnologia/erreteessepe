from __future__ import annotations

import os
from dataclasses import dataclass


def _clean_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return _clean_env_value(raw).lower() in {"1", "true", "yes", "on"}


def _env_text(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = _clean_env_value(raw)
    if not value:
        return default
    return value


@dataclass(frozen=True)
class Settings:
    auth_provider: str
    media_auth_mode: str
    mediamtx_host: str
    mediamtx_api: str
    camera_redis_url: str
    camera_redis_prefix: str
    camera_redis_timeout_seconds: float
    camera_default_manufacturer: str
    camera_default_port: int
    camera_default_channel: int
    camera_default_subtype: int
    webrtc_port: int
    whep_url: str
    mediamtx_api_user: str
    mediamtx_api_pass: str
    webrtc_user: str
    webrtc_pass: str
    public_webrtc_host: str
    webrtc_stun_server: str
    turn_enabled: bool
    turn_public_ip: str
    turn_port: int
    turn_username: str
    turn_password: str
    max_viewers: int
    mediamtx_ready_timeout_seconds: float
    idle_room_cleanup_seconds: int
    keycloak_base_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_certificate: str
    keycloak_jwks_cache_ttl_seconds: int
    stream_roles_claim_path: str
    stream_access_role: str
    mediamtx_jwt_issuer: str
    mediamtx_jwt_private_key: str
    mediamtx_jwt_private_key_path: str
    mediamtx_jwt_kid: str
    mediamtx_jwt_ttl_seconds: int
    mediamtx_api_token_ttl_seconds: int
    mediamtx_admin_subject: str


_keycloak_base_url = _env_text("KEYCLOAK_BASE_URL", "http://localhost:8080").rstrip("/")
_keycloak_realm = _env_text("KEYCLOAK_REALM", "mediamtx")
_keycloak_client_id = _env_text("KEYCLOAK_CLIENT_ID", "mediamtx")
_keycloak_issuer = f"{_keycloak_base_url}/realms/{_keycloak_realm}"

settings = Settings(
    auth_provider=os.getenv("AUTH_PROVIDER", "keycloak"),
    media_auth_mode=_env_text("MEDIA_AUTH_MODE", "internal_jwt"),
    mediamtx_host=os.getenv("MEDIAMTX_HOST", "localhost"),
    mediamtx_api=os.getenv("MEDIAMTX_API", "http://localhost:9997"),
    camera_redis_url=os.getenv("CAMERA_REDIS_URL", "").strip(),
    camera_redis_prefix=os.getenv("CAMERA_REDIS_PREFIX", "camera:"),
    camera_redis_timeout_seconds=float(os.getenv("CAMERA_REDIS_TIMEOUT_SECONDS", "2")),
    camera_default_manufacturer=_env_text("CAMERA_DEFAULT_MANUFACTURER", "dahua"),
    camera_default_port=int(os.getenv("CAMERA_DEFAULT_PORT", "554")),
    camera_default_channel=int(os.getenv("CAMERA_DEFAULT_CHANNEL", "1")),
    camera_default_subtype=int(os.getenv("CAMERA_DEFAULT_SUBTYPE", "0")),
    webrtc_port=int(os.getenv("WEBRTC_PORT", "8889")),
    whep_url=os.getenv("WHEP_URL", "").strip(),
    mediamtx_api_user=os.getenv("MEDIAMTX_API_USER", "backend"),
    mediamtx_api_pass=os.getenv("MEDIAMTX_API_PASS", "backendpassword"),
    webrtc_user=os.getenv("WEBRTC_USER", "viewer"),
    webrtc_pass=os.getenv("WEBRTC_PASS", "strongpassword"),
    public_webrtc_host=os.getenv("PUBLIC_WEBRTC_HOST", "localhost"),
    webrtc_stun_server=os.getenv("WEBRTC_STUN_SERVER", "stun:stun.l.google.com:19302"),
    turn_enabled=_env_bool("TURN_ENABLED", False),
    turn_public_ip=os.getenv("TURN_PUBLIC_IP", "").strip(),
    turn_port=int(os.getenv("TURN_PORT", "3478")),
    turn_username=os.getenv("TURN_USERNAME", "turnuser"),
    turn_password=os.getenv("TURN_PASSWORD", "turnpassword"),
    max_viewers=int(os.getenv("MAX_VIEWERS", "20")),
    mediamtx_ready_timeout_seconds=float(os.getenv("MEDIAMTX_READY_TIMEOUT_SECONDS", "20")),
    idle_room_cleanup_seconds=int(os.getenv("IDLE_ROOM_CLEANUP_SECONDS", "20")),
    keycloak_base_url=_keycloak_base_url,
    keycloak_realm=_keycloak_realm,
    keycloak_client_id=_keycloak_client_id,
    keycloak_client_secret=_env_text("KEYCLOAK_CLIENT_SECRET", "mediamtx-dev-secret"),
    keycloak_issuer=_keycloak_issuer,
    keycloak_jwks_url=f"{_keycloak_issuer}/protocol/openid-connect/certs",
    keycloak_certificate=_env_text("KEYCLOAK_CERTIFICATE", ""),
    keycloak_jwks_cache_ttl_seconds=int(
        os.getenv("KEYCLOAK_JWKS_CACHE_TTL_SECONDS", "300")
    ),
    stream_roles_claim_path=f"resource_access.{_keycloak_client_id}.roles,realm_access.roles",
    stream_access_role=_env_text("STREAM_ACCESS_ROLE", "stream:read"),
    mediamtx_jwt_issuer=_env_text("MEDIAMTX_JWT_ISSUER", "stream-api"),
    mediamtx_jwt_private_key=_env_text("MEDIAMTX_JWT_PRIVATE_KEY", ""),
    mediamtx_jwt_private_key_path=_env_text("MEDIAMTX_JWT_PRIVATE_KEY_PATH", ""),
    mediamtx_jwt_kid=_env_text("MEDIAMTX_JWT_KID", "mediamtx-internal-dev"),
    mediamtx_jwt_ttl_seconds=int(os.getenv("MEDIAMTX_JWT_TTL_SECONDS", "60")),
    mediamtx_api_token_ttl_seconds=int(
        os.getenv("MEDIAMTX_API_TOKEN_TTL_SECONDS", "60")
    ),
    mediamtx_admin_subject=_env_text("MEDIAMTX_ADMIN_SUBJECT", "mediamtx-admin"),
)
