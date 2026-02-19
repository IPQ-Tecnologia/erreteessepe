import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .cameras import load_cameras
from .config import LOGGER_NAME, Settings, configure_logging
from .models import AnswerResponse, OfferRequest
from .sdp import apply_video_bitrate_caps
from .stream_manager import CameraStreamManager
from .validation import validate_camera_connection


FRONTEND_FILE = Path(__file__).resolve().parent / "static" / "index.html"


@dataclass
class RuntimeState:
    settings: Settings
    stream_manager: CameraStreamManager | None = None
    peer_connections: set[RTCPeerConnection] = field(default_factory=set)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    configure_logging(runtime_settings.log_level)
    logger = logging.getLogger(LOGGER_NAME)

    app = FastAPI(title="RTSP -> WebRTC Bridge")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[runtime_settings.cors_allow_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.runtime = RuntimeState(settings=runtime_settings)

    def get_runtime() -> RuntimeState:
        return cast(RuntimeState, app.state.runtime)

    def get_stream_manager() -> CameraStreamManager:
        runtime = get_runtime()
        if runtime.stream_manager is None:
            raise HTTPException(status_code=503, detail="Service not ready")
        return runtime.stream_manager

    @app.on_event("startup")
    async def on_startup() -> None:
        runtime = get_runtime()
        cameras = load_cameras()
        runtime.stream_manager = CameraStreamManager(cameras, runtime.settings)

        logger.info(
            "Low-latency config: relay_buffered=%s max_delay_us=%d reorder_queue_size=%d max_bitrate_bps=%d",
            runtime.settings.webrtc_relay_buffered,
            runtime.settings.rtsp_max_delay_us,
            runtime.settings.rtsp_reorder_queue_size,
            runtime.settings.webrtc_video_max_bitrate_bps,
        )
        logger.info(
            "Configured cameras: %s",
            ", ".join([f"{camera.id} ({camera.name})" for camera in cameras.values()]),
        )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        runtime = get_runtime()
        logger.info("Shutting down %d peer connections", len(runtime.peer_connections))

        pcs = list(runtime.peer_connections)
        await asyncio.gather(*[pc.close() for pc in pcs], return_exceptions=True)
        runtime.peer_connections.clear()

        if runtime.stream_manager is not None:
            await runtime.stream_manager.close()
            runtime.stream_manager = None

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/cameras")
    async def cameras() -> dict[str, Any]:
        manager = get_stream_manager()
        return {"cameras": manager.list_cameras()}

    @app.get("/status")
    async def status(camera_id: str | None = None) -> dict[str, Any]:
        runtime = get_runtime()
        manager = get_stream_manager()

        if camera_id:
            try:
                camera = manager.get_camera(camera_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found") from exc

            validation = await validate_camera_connection(camera.rtsp_url, runtime.settings)
            return {"camera_id": camera.id, "camera_name": camera.name, "status": validation}

        camera_ids = [camera_data["id"] for camera_data in manager.list_cameras()]
        camera_objects = [manager.get_camera(camera_id_value) for camera_id_value in camera_ids]
        validations = await asyncio.gather(
            *[validate_camera_connection(camera.rtsp_url, runtime.settings) for camera in camera_objects]
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
        runtime = get_runtime()
        manager = get_stream_manager()

        try:
            camera = manager.get_camera(payload.camera_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Camera '{payload.camera_id}' not found") from exc

        connection_status = await validate_camera_connection(camera.rtsp_url, runtime.settings)
        if not connection_status["ok"]:
            reason_to_http = {
                "auth_failed": 401,
                "unreachable": 504,
                "stream_error": 502,
            }
            status_code = reason_to_http.get(connection_status.get("reason"), 502)
            raise HTTPException(status_code=status_code, detail=connection_status)

        try:
            video_track = await manager.get_video_track(payload.camera_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Camera '{payload.camera_id}' not found") from exc
        except Exception as exc:
            logger.exception("Failed to create video track for camera '%s'", payload.camera_id)
            raise HTTPException(status_code=500, detail=f"Camera stream error: {exc}") from exc

        pc_id = f"pc-{uuid.uuid4().hex[:8]}"
        pc = RTCPeerConnection()
        runtime.peer_connections.add(pc)
        logger.info("Created %s for camera '%s' (peers=%d)", pc_id, payload.camera_id, len(runtime.peer_connections))

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            state = pc.connectionState
            logger.info("%s connection state -> %s", pc_id, state)
            if state in {"failed", "closed", "disconnected"}:
                await pc.close()
                runtime.peer_connections.discard(pc)
                logger.info("Closed %s (peers=%d)", pc_id, len(runtime.peer_connections))

        pc.addTrack(video_track)

        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=payload.sdp, type=payload.type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
        except Exception as exc:
            logger.exception("WebRTC negotiation failed for %s", pc_id)
            await pc.close()
            runtime.peer_connections.discard(pc)
            raise HTTPException(status_code=500, detail=f"WebRTC negotiation failed: {exc}") from exc

        local = pc.localDescription
        if local is None:
            raise HTTPException(status_code=500, detail="No local description generated")

        tuned_sdp = apply_video_bitrate_caps(local.sdp, runtime.settings)
        return AnswerResponse(sdp=tuned_sdp, type=local.type)

    @app.get("/")
    async def index() -> FileResponse:
        if not FRONTEND_FILE.exists():
            raise HTTPException(status_code=500, detail="Missing frontend file")
        return FileResponse(FRONTEND_FILE)

    return app


app = create_app()
