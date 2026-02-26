from __future__ import annotations

from fastapi import HTTPException

from app.core.settings import settings
from app.domain.access_control import validate_user_access
from app.domain.cameras import CAMERAS
from app.infrastructure.mediamtx_client import MediaMTXClient
from app.schemas.stream import StreamResponse, WebRTCConfig


class StreamPreparationService:
    def __init__(self, mediamtx: MediaMTXClient | None = None) -> None:
        self._mediamtx = mediamtx or MediaMTXClient()

    def prepare_stream(self, user_id: str, device_name: str) -> StreamResponse:
        if not validate_user_access(user_id, device_name):
            raise HTTPException(status_code=403, detail="Sem permissao")

        rtsp_source = self._get_rtsp_source(device_name)

        viewers = self._mediamtx.get_viewer_count(device_name)
        if viewers >= settings.max_viewers:
            raise HTTPException(status_code=429, detail="Limite de viewers atingido")

        if not self._mediamtx.path_exists(device_name):
            self._mediamtx.create_path(device_name, rtsp_source)

        self._mediamtx.wait_until_ready(device_name)

        return StreamResponse(
            device=device_name,
            viewers=viewers,
            webrtc=WebRTCConfig(
                url=(
                    f"http://{settings.public_webrtc_host}:"
                    f"{settings.webrtc_port}/{device_name}/whep"
                ),
                username=settings.webrtc_user,
                password=settings.webrtc_pass,
            ),
        )

    def cleanup_if_idle(self, device_name: str) -> None:
        viewers = self._mediamtx.get_viewer_count(device_name)
        if viewers == 0 and self._mediamtx.path_exists(device_name):
            self._mediamtx.remove_path(device_name)

    @staticmethod
    def _get_rtsp_source(device_name: str) -> str:
        rtsp = CAMERAS.get(device_name)
        if not rtsp:
            raise HTTPException(
                status_code=404,
                detail=f"Camera '{device_name}' nao cadastrada",
            )
        return rtsp
