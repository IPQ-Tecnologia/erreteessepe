from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    auth_provider: str
    mediamtx_host: str
    mediamtx_api: str
    rtsp_port: int
    webrtc_port: int
    mediamtx_api_user: str
    mediamtx_api_pass: str
    webrtc_user: str
    webrtc_pass: str
    public_webrtc_host: str
    max_viewers: int
    mediamtx_ready_timeout_seconds: float
    idle_room_cleanup_seconds: int
    mediamtx_source_close_after: str
    keycloak_base_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_client_secret: str


settings = Settings(
    auth_provider=os.getenv("AUTH_PROVIDER", "keycloak"),
    mediamtx_host=os.getenv("MEDIAMTX_HOST", "mediamtx"),
    mediamtx_api=os.getenv("MEDIAMTX_API", "http://mediamtx:9997"),
    rtsp_port=int(os.getenv("RTSP_PORT", "8554")),
    webrtc_port=int(os.getenv("WEBRTC_PORT", "8889")),
    mediamtx_api_user=os.getenv("MEDIAMTX_API_USER", "backend"),
    mediamtx_api_pass=os.getenv("MEDIAMTX_API_PASS", "backendpassword"),
    webrtc_user=os.getenv("WEBRTC_USER", "viewer"),
    webrtc_pass=os.getenv("WEBRTC_PASS", "strongpassword"),
    public_webrtc_host=os.getenv("PUBLIC_WEBRTC_HOST", "localhost"),
    max_viewers=int(os.getenv("MAX_VIEWERS", "5")),
    mediamtx_ready_timeout_seconds=float(os.getenv("MEDIAMTX_READY_TIMEOUT_SECONDS", "20")),
    idle_room_cleanup_seconds=int(os.getenv("IDLE_ROOM_CLEANUP_SECONDS", "20")),
    mediamtx_source_close_after=os.getenv("MEDIAMTX_SOURCE_CLOSE_AFTER", "20s"),
    keycloak_base_url=os.getenv("KEYCLOAK_BASE_URL", "http://localhost:8080"),
    keycloak_realm=os.getenv("KEYCLOAK_REALM", "mediamtx"),
    keycloak_client_id=os.getenv("KEYCLOAK_CLIENT_ID", "mediamtx"),
    keycloak_client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET", "mediamtx-dev-secret"),
)
