from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraDefinition:
    device_name: str
    manufacturer: str
    host: str
    username: str
    password: str
    port: int = 554
    channel: int = 1
    subtype: int = 0
    rtsp_path: str | None = None
    rtsp_url: str | None = None

