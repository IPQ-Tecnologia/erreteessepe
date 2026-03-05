from __future__ import annotations

import logging
import threading
import time
from fastapi import HTTPException

from app.core.http_errors import http_error
from app.core.settings import settings
from app.domain.access_control import validate_user_access
from app.domain.cameras import CAMERAS
from app.domain.rtsp import build_rtsp_url
from app.infrastructure.camera_catalog import CameraCatalog
from app.infrastructure.mediamtx_client import MediaMTXClient
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
        user_id: str,
        device_name: str,
        viewer_token: str | None = None,
    ) -> StreamResponse:
        if not validate_user_access(user_id, device_name):
            raise HTTPException(status_code=403, detail="Denied access to this camera")

        rtsp_source = self.get_rtsp_source(device_name)

        viewers = self._mediamtx.get_viewer_count(device_name)
        if viewers >= settings.max_viewers:
            raise HTTPException(status_code=429, detail="Viewers limit reached")

        path_info = self._mediamtx.get_path_info(device_name)
        if not path_info or not path_info.get("ready"):
            self._rtsp_probe.ensure_source_available(rtsp_source)

        if not path_info:
            self._mediamtx.create_path(device_name, rtsp_source)

        self._mediamtx.wait_until_ready(
            device_name,
            timeout_seconds=settings.mediamtx_ready_timeout_seconds,
        )
        webrtc_auth = self._build_webrtc_auth(viewer_token)
        with self._cleanup_lock:
            self._managed_paths.add(device_name)

        return StreamResponse(
            device=device_name,
            viewers=viewers,
            webrtc=WebRTCConfig(
                url=self._build_webrtc_url(device_name),
                ice_servers=self._build_ice_servers(),
                **webrtc_auth,
            ),
        )

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

    @staticmethod
    def _build_webrtc_url(device_name: str) -> str:
        return (
            f"http://{settings.public_webrtc_host}:"
            f"{settings.webrtc_port}/{device_name}/whep"
        )

    def _build_webrtc_auth(self, viewer_token: str | None) -> dict:
        if settings.auth_provider != "keycloak":
            return {
                "auth_type": "basic",
                "username": settings.webrtc_user,
                "password": settings.webrtc_pass,
                "token": None,
            }

        if not viewer_token:
            raise HTTPException(
                status_code=401,
                detail="Keycloak session missing or expired",
            )

        return {
            "auth_type": "bearer",
            "username": None,
            "password": None,
            "token": viewer_token,
        }

    @staticmethod
    def _build_ice_servers() -> list[ICEServer]:
        servers: list[ICEServer] = []

        if settings.webrtc_stun_server:
            servers.append(ICEServer(urls=[settings.webrtc_stun_server]))

        if not settings.turn_enabled:
            return servers

        if not settings.turn_public_ip:
            raise HTTPException(
                status_code=500,
                detail="TURN enabled without TURN_PUBLIC_IP configured",
            )

        if not settings.turn_username or not settings.turn_password:
            raise HTTPException(
                status_code=500,
                detail="TURN enabled without TURN_USERNAME/TURN_PASSWORD configured",
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
