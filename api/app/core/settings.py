from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
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


settings = Settings(
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
)
