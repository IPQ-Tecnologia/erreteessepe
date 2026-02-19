#!/usr/bin/env python3
"""
RTSP -> WebRTC bridge using FastAPI + aiortc.

Quick start:
1) python -m venv .venv
2) source .venv/bin/activate
3) pip install -r python_webrtc/requirements.txt
4) export RTSP_CAMERA_CAM1_URL="rtsp://user:pass@camera-host:554/stream"
5) uvicorn python_webrtc.rtsp_webrtc_fastapi:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rtsp-webrtc")

TCP_CHECK_TIMEOUT_MS = 3000
PROBE_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    rtsp_url: str


def load_cameras() -> dict[str, Camera]:
    cameras = {
        "dss": Camera(
            id="dss",
            name="DSS Playback",
            rtsp_url=os.getenv(
                "RTSP_CAMERA_DSS_URL",
                "rtsp://192.168.202.165:9320/playback/center/110?streamID=224&beginTime=1745783566&endTime=1745784000",
            ),
        ),
        "cam1": Camera(
            id="cam1",
            name="Camera 1",
            rtsp_url=os.getenv(
                "RTSP_CAMERA_CAM1_URL",
                "rtsp://admin:admin%40123@192.168.101.212:554/cam/realmonitor?channel=1&subtype=0",
            ),
        ),
        "cam2": Camera(
            id="cam2",
            name="Camera 2",
            rtsp_url=os.getenv(
                "RTSP_CAMERA_CAM2_URL",
                "rtsp://admin:admin123@192.168.101.211:554/cam/realmonitor?channel=1&subtype=0",
            ),
        ),
    }

    if not cameras:
        raise RuntimeError(
            "No cameras configured. Set RTSP_CAMERA_DSS_URL, RTSP_CAMERA_CAM1_URL, and RTSP_CAMERA_CAM2_URL."
        )

    return cameras


class OfferRequest(BaseModel):
    sdp: str
    type: str
    camera_id: str = Field(default="cam1")


class AnswerResponse(BaseModel):
    sdp: str
    type: str


class CameraStreamManager:
    def __init__(self, cameras: dict[str, Camera]):
        self._cameras = cameras
        self._relay = MediaRelay()
        self._players: dict[str, MediaPlayer] = {}
        self._lock = asyncio.Lock()

    def list_cameras(self) -> list[dict[str, str]]:
        return [{"id": c.id, "name": c.name} for c in self._cameras.values()]

    def get_camera(self, camera_id: str) -> Camera:
        camera = self._cameras.get(camera_id)
        if camera is None:
            raise KeyError(camera_id)
        return camera

    async def get_video_track(self, camera_id: str):
        camera = self.get_camera(camera_id)

        async with self._lock:
            player = self._players.get(camera_id)
            if player is None:
                logger.info("Opening RTSP stream for camera '%s'", camera_id)
                player = MediaPlayer(
                    camera.rtsp_url,
                    format="rtsp",
                    options={
                        "rtsp_transport": os.getenv("RTSP_TRANSPORT", "tcp"),
                        "stimeout": os.getenv("RTSP_TIMEOUT_US", "5000000"),
                        "fflags": "nobuffer",
                        "flags": "low_delay",
                    },
                )
                self._players[camera_id] = player

        if player.video is None:
            raise RuntimeError(f"Camera '{camera_id}' has no video track")

        return self._relay.subscribe(player.video)

    async def close(self) -> None:
        async with self._lock:
            for camera_id, player in self._players.items():
                logger.info("Closing player for camera '%s'", camera_id)
                player.stop()
            self._players.clear()


async def check_tcp_reachability(rtsp_url: str) -> bool:
    try:
        parsed = urlparse(rtsp_url)
        host = parsed.hostname
        port = parsed.port or 554
        if not host:
            return False

        conn = asyncio.open_connection(host, port)
        _reader, writer = await asyncio.wait_for(conn, timeout=TCP_CHECK_TIMEOUT_MS / 1000)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def validate_camera_connection(rtsp_url: str) -> dict[str, Any]:
    is_reachable = await check_tcp_reachability(rtsp_url)
    logger.info("TCP reachability check for %s: %s", rtsp_url, "reachable" if is_reachable else "unreachable")

    if not is_reachable:
        return {"ok": False, "reason": "unreachable", "message": "Camera host is not reachable"}

    command = [
        "ffprobe",
        "-v",
        "error",
        "-rtsp_transport",
        os.getenv("RTSP_TRANSPORT", "tcp"),
        "-timeout",
        str(PROBE_TIMEOUT_SECONDS * 1_000_000),
        "-i",
        rtsp_url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "reason": "stream_error",
            "message": "ffprobe not found in PATH",
        }
    except Exception as exc:
        return {"ok": False, "reason": "stream_error", "message": str(exc)}

    try:
        _, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=PROBE_TIMEOUT_SECONDS + 2,
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        return {"ok": False, "reason": "unreachable", "message": "Connection timed out"}

    stderr = stderr_bytes.decode("utf-8", errors="ignore").strip()

    if process.returncode == 0:
        return {"ok": True}

    lower = stderr.lower()
    if "401" in lower or "unauthorized" in lower:
        return {"ok": False, "reason": "auth_failed", "message": "Invalid credentials"}

    unreachable_markers = [
        "connection refused",
        "network is unreachable",
        "no route to host",
        "connection timed out",
        "timeout",
    ]
    if any(marker in lower for marker in unreachable_markers):
        return {"ok": False, "reason": "unreachable", "message": "Camera is unreachable"}

    return {
        "ok": False,
        "reason": "stream_error",
        "message": stderr[:200] if stderr else "Unknown stream error",
    }


app = FastAPI(title="RTSP -> WebRTC Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ALLOW_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pcs: set[RTCPeerConnection] = set()
stream_manager: CameraStreamManager | None = None


@app.on_event("startup")
async def on_startup() -> None:
    global stream_manager
    cameras = load_cameras()
    stream_manager = CameraStreamManager(cameras)
    logger.info(
        "Configured cameras: %s",
        ", ".join([f"{c.id} ({c.name})" for c in cameras.values()]),
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Shutting down %d peer connections", len(pcs))
    await asyncio.gather(*[pc.close() for pc in pcs], return_exceptions=True)
    pcs.clear()
    if stream_manager is not None:
        await stream_manager.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cameras")
async def cameras() -> dict[str, Any]:
    if stream_manager is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"cameras": stream_manager.list_cameras()}


@app.get("/status")
async def status(camera_id: str | None = None) -> dict[str, Any]:
    if stream_manager is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    if camera_id:
        try:
            camera = stream_manager.get_camera(camera_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found") from exc

        validation = await validate_camera_connection(camera.rtsp_url)
        return {"camera_id": camera.id, "camera_name": camera.name, "status": validation}

    camera_ids = [camera_data["id"] for camera_data in stream_manager.list_cameras()]
    camera_objects = [stream_manager.get_camera(cid) for cid in camera_ids]
    validations = await asyncio.gather(
        *[validate_camera_connection(camera.rtsp_url) for camera in camera_objects]
    )
    checks = [
        {
            "camera_id": camera.id,
            "camera_name": camera.name,
            "status": validation,
        }
        for camera, validation in zip(camera_objects, validations)
    ]

    return {"cameras": checks}


@app.post("/offer", response_model=AnswerResponse)
async def offer(payload: OfferRequest) -> AnswerResponse:
    if stream_manager is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    try:
        camera = stream_manager.get_camera(payload.camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Camera '{payload.camera_id}' not found") from exc

    connection_status = await validate_camera_connection(camera.rtsp_url)
    if not connection_status["ok"]:
        reason_to_http = {
            "auth_failed": 401,
            "unreachable": 504,
            "stream_error": 502,
        }
        status_code = reason_to_http.get(connection_status.get("reason"), 502)
        raise HTTPException(status_code=status_code, detail=connection_status)

    try:
        video_track = await stream_manager.get_video_track(payload.camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Camera '{payload.camera_id}' not found") from exc
    except Exception as exc:
        logger.exception("Failed to create video track for camera '%s'", payload.camera_id)
        raise HTTPException(status_code=500, detail=f"Camera stream error: {exc}") from exc

    pc_id = f"pc-{uuid.uuid4().hex[:8]}"
    pc = RTCPeerConnection()
    pcs.add(pc)
    logger.info("Created %s for camera '%s' (peers=%d)", pc_id, payload.camera_id, len(pcs))

    @pc.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        state = pc.connectionState
        logger.info("%s connection state -> %s", pc_id, state)
        if state in {"failed", "closed", "disconnected"}:
            await pc.close()
            pcs.discard(pc)
            logger.info("Closed %s (peers=%d)", pc_id, len(pcs))

    pc.addTrack(video_track)

    try:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=payload.sdp, type=payload.type))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
    except Exception as exc:
        logger.exception("WebRTC negotiation failed for %s", pc_id)
        await pc.close()
        pcs.discard(pc)
        raise HTTPException(status_code=500, detail=f"WebRTC negotiation failed: {exc}") from exc

    local = pc.localDescription
    if local is None:
        raise HTTPException(status_code=500, detail="No local description generated")

    return AnswerResponse(sdp=local.sdp, type=local.type)


FRONTEND_FILE = Path(__file__).resolve().parent / "static" / "index.html"


@app.get("/")
async def index() -> FileResponse:
    if not FRONTEND_FILE.exists():
        raise HTTPException(status_code=500, detail="Missing frontend file")
    return FileResponse(FRONTEND_FILE)
