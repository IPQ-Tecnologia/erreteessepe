from __future__ import annotations

import logging
import threading
import time

from app.core.http_errors import http_error
from app.core.settings import settings
from app.domain.access_control import validate_user_access
from app.domain.cameras import CAMERAS
from app.domain.rtsp import build_rtsp_url
from app.infrastructure.camera_catalog import CameraCatalog
from app.infrastructure.mediamtx_client import MediaMTXClient
from app.infrastructure.principal_claims import VerifiedPrincipal
from app.infrastructure.rtsp_probe import RTSPProbe
from app.schemas.stream import ICEServer, StreamResponse, WebRTCConfig


class StreamPreparationService:
    def __init__(
        self,
        mediamtx: MediaMTXClient | None = None,
        rtsp_probe: RTSPProbe | None = None,
        camera_catalog: CameraCatalog | None = None,
    ) -> None:
        self._mediamtx = mediamtx or MediaMTXClient()
        self._rtsp_probe = rtsp_probe or RTSPProbe()
        self._camera_catalog = camera_catalog or CameraCatalog()
        self._cleanup_lock = threading.Lock()
        self._managed_paths: set[str] = set()
        self._logger = logging.getLogger(__name__)
        self._cleanup_thread: threading.Thread | None = None
        if settings.idle_room_cleanup_seconds > 0:
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                daemon=True,
                name="stream-room-cleanup",
            )
            self._cleanup_thread.start()

    def prepare_stream(
        self,
        principal: VerifiedPrincipal,
        device_name: str,
        whep_url: str,
        client_auth_type: str,
    ) -> StreamResponse:
        viewers = self.ensure_stream_ready(principal, device_name)

        return StreamResponse(
            device=device_name,
            viewers=viewers,
            webrtc=WebRTCConfig(
                url=whep_url,
                ice_servers=self._build_ice_servers(),
                **self._build_webrtc_auth(principal, client_auth_type),
            ),
        )

    def ensure_stream_ready(
        self,
        principal: VerifiedPrincipal,
        device_name: str,
    ) -> int:
        if not validate_user_access(principal.roles, device_name):
            raise http_error(
                status_code=403,
                code="camera_access_denied",
                message="Denied access to this camera",
            )

        rtsp_source = self.get_rtsp_source(device_name)

        viewers = self._mediamtx.get_viewer_count(device_name)
        if viewers >= settings.max_viewers:
            raise http_error(
                status_code=429,
                code="viewers_limit_reached",
                message="Viewers limit reached",
            )

        path_info = self._mediamtx.get_path_info(device_name)
        if not path_info or not path_info.get("ready"):
            self._rtsp_probe.ensure_source_available(rtsp_source)

        if not path_info:
            self._mediamtx.create_path(device_name, rtsp_source)

        self._mediamtx.wait_until_ready(
            device_name,
            timeout_seconds=settings.mediamtx_ready_timeout_seconds,
        )
        with self._cleanup_lock:
            self._managed_paths.add(device_name)

        return viewers

    def cleanup_if_idle(self, device_name: str) -> bool:
        viewers = self._mediamtx.get_viewer_count(device_name)
        if viewers == 0 and self._mediamtx.path_exists(device_name):
            self._mediamtx.remove_path(device_name)
            return True
        return False

    def get_rtsp_source(self, device_name: str) -> str:
        camera = self._camera_catalog.get(device_name)
        rtsp = build_rtsp_url(camera)
        if not rtsp:
            raise http_error(
                status_code=502,
                code="camera_url_invalid",
                message=f"Unable to build RTSP URL for camera '{device_name}'.",
            )
        return rtsp

    def _build_webrtc_auth(
        self,
        principal: VerifiedPrincipal,
        client_auth_type: str,
    ) -> dict:
        if settings.media_auth_mode == "internal_jwt":
            return {
                "auth_type": client_auth_type,
                "username": None,
                "password": None,
                "token": None,
            }

        if settings.auth_provider != "keycloak":
            return {
                "auth_type": "basic",
                "username": settings.webrtc_user,
                "password": settings.webrtc_pass,
                "token": None,
            }

        if not principal.external_token:
            raise http_error(
                status_code=401,
                code="keycloak_session_missing_or_expired",
                message="Keycloak session missing or expired",
            )

        return {
            "auth_type": "bearer",
            "username": None,
            "password": None,
            "token": principal.external_token,
        }

    @staticmethod
    def _build_ice_servers() -> list[ICEServer]:
        servers: list[ICEServer] = []

        if settings.webrtc_stun_server:
            servers.append(ICEServer(urls=[settings.webrtc_stun_server]))

        if not settings.turn_enabled:
            return servers

        if not settings.turn_public_ip:
            raise http_error(
                status_code=500,
                code="turn_public_ip_missing",
                message="TURN enabled without TURN_PUBLIC_IP configured",
            )

        if not settings.turn_username or not settings.turn_password:
            raise http_error(
                status_code=500,
                code="turn_credentials_missing",
                message="TURN enabled without TURN_USERNAME/TURN_PASSWORD configured",
            )

        turn_base = f"turn:{settings.turn_public_ip}:{settings.turn_port}"
        servers.append(
            ICEServer(
                urls=[
                    f"{turn_base}?transport=udp",
                    f"{turn_base}?transport=tcp",
                ],
                username=settings.turn_username,
                credential=settings.turn_password,
            )
        )

        return servers

    def _cleanup_loop(self) -> None:
        interval = max(2, settings.idle_room_cleanup_seconds)
        while True:
            time.sleep(interval)
            with self._cleanup_lock:
                managed = set(self._managed_paths)
            # Also scan known camera path names, so cleanup still works after API restarts.
            paths = sorted(managed.union(self._camera_catalog.list_known_ids()).union(CAMERAS.keys()))

            for device_name in paths:
                try:
                    removed = self.cleanup_if_idle(device_name)
                    exists = self._mediamtx.path_exists(device_name)
                    if removed or not exists:
                        with self._cleanup_lock:
                            self._managed_paths.discard(device_name)
                except Exception as exc:
                    self._logger.warning(
                        "Idle cleanup check failed for %s: %s",
                        device_name,
                        exc,
                    )
