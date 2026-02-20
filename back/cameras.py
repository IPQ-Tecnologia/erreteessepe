import os
import re
from collections import OrderedDict

from .models import Camera


def _normalize_camera_id(raw_id: str) -> str:
    normalized = raw_id.strip().lower().replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_-]", "", normalized)
    return normalized


def _humanize_camera_id(camera_id: str) -> str:
    tokens = re.split(r"[_-]", camera_id)
    return " ".join([token.upper() if token.startswith("cam") else token.capitalize() for token in tokens if token])


def _load_from_env() -> dict[str, Camera]:
    cameras: "OrderedDict[str, Camera]" = OrderedDict()

    for env_name, env_value in sorted(os.environ.items()):
        if not env_value:
            continue

        raw_id: str | None = None

        match_rtsp_camera = re.match(r"^RTSP_CAMERA_(.+)_URL$", env_name)
        if match_rtsp_camera:
            raw_id = match_rtsp_camera.group(1)

        match_camera_rtsp = re.match(r"^CAMERA_(.+)_RTSP$", env_name)
        if match_camera_rtsp:
            raw_id = match_camera_rtsp.group(1)

        match_cam_rtsp = re.match(r"^(CAM[0-9A-Z_]+)_RTSP$", env_name)
        if match_cam_rtsp:
            raw_id = match_cam_rtsp.group(1)

        if raw_id is None:
            continue

        camera_id = _normalize_camera_id(raw_id)
        if not camera_id:
            continue

        name_env_key = f"CAMERA_{raw_id}_NAME"
        camera_name = os.getenv(name_env_key, _humanize_camera_id(camera_id))

        cameras[camera_id] = Camera(id=camera_id, name=camera_name, rtsp_url=env_value)

    return dict(cameras)


def _default_cameras() -> dict[str, Camera]:
    return {
        "dss": Camera(
            id="dss",
            name="DSS Playback",
            rtsp_url="rtsp://192.168.202.165:9320/playback/center/110?streamID=224&beginTime=1745783566&endTime=1745784000",
        ),
        "cam1": Camera(
            id="cam1",
            name="Camera 1",
            rtsp_url="rtsp://admin:admin%40123@192.168.101.212:554/cam/realmonitor?channel=1&subtype=0",
        ),
        "cam2": Camera(
            id="cam2",
            name="Camera 2",
            rtsp_url="rtsp://admin:admin123@192.168.101.211:554/cam/realmonitor?channel=1&subtype=0",
        ),
    }


def load_cameras() -> dict[str, Camera]:
    configured = _load_from_env()
    if configured:
        return configured
    return _default_cameras()


def build_room_name(camera_id: str, prefix: str) -> str:
    normalized_id = re.sub(r"[^a-z0-9_-]", "-", camera_id.lower())
    normalized_prefix = re.sub(r"[^a-z0-9_-]", "-", prefix.lower())
    return f"{normalized_prefix}-{normalized_id}"
