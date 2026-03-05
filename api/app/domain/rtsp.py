from __future__ import annotations

from urllib.parse import quote

from app.core.http_errors import http_error
from app.domain.camera_catalog import CameraDefinition


_DAHUA_MANUFACTURERS = {"dahua", "intelbras"}
_HIKVISION_MANUFACTURERS = {"hikvision", "hilook"}
_GENERIC_MANUFACTURERS = {"generic", "genérico", "generico", "onvif"}


def build_rtsp_url(camera: CameraDefinition) -> str:
    if camera.rtsp_url:
        return camera.rtsp_url

    manufacturer = _normalize_manufacturer(camera.manufacturer)
    user = quote(camera.username, safe="")
    password = quote(camera.password, safe="")

    if camera.rtsp_path:
        path = camera.rtsp_path.lstrip("/")
        return f"rtsp://{user}:{password}@{camera.host}:{camera.port}/{path}"

    if manufacturer in _DAHUA_MANUFACTURERS:
        return (
            f"rtsp://{user}:{password}@{camera.host}:{camera.port}/"
            f"cam/realmonitor?channel={camera.channel}&subtype={camera.subtype}"
        )

    if manufacturer in _HIKVISION_MANUFACTURERS:
        stream_id = f"{camera.channel:02d}{camera.subtype + 1}"
        return f"rtsp://{user}:{password}@{camera.host}:{camera.port}/Streaming/Channels/{stream_id}"

    if manufacturer in _GENERIC_MANUFACTURERS:
        return f"rtsp://{user}:{password}@{camera.host}:{camera.port}/"

    raise http_error(
        status_code=422,
        code="camera_manufacturer_unsupported",
        message=f"Fabricante '{camera.manufacturer}' nao suportado para montagem da URL RTSP.",
    )


def _normalize_manufacturer(value: str) -> str:
    return value.strip().lower()

