import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .cameras import build_room_name, load_cameras
from .config import LOGGER_NAME, Settings, configure_logging
from .ingest_status import load_ingest_status
from .livekit_auth import build_viewer_token
from .models import Camera, CameraView, ViewerSessionResponse

FRONTEND_FILE = Path(__file__).resolve().parent / "static" / "index.html"


@dataclass
class RuntimeState:
    settings: Settings
    cameras: dict[str, Camera]


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    configure_logging(runtime_settings.log_level)
    logger = logging.getLogger(LOGGER_NAME)

    app = FastAPI(title="RTSP -> LiveKit SFU Bridge")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[runtime_settings.cors_allow_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.runtime = RuntimeState(
        settings=runtime_settings,
        cameras=load_cameras(),
    )

    def get_runtime() -> RuntimeState:
        return cast(RuntimeState, app.state.runtime)

    def get_camera_or_404(camera_id: str) -> Camera:
        runtime = get_runtime()
        camera = runtime.cameras.get(camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
        return camera

    def get_ingest_snapshot() -> dict[str, Any]:
        runtime = get_runtime()
        return load_ingest_status(runtime.settings.ingest_status_path)

    def build_camera_status(camera_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        cameras = snapshot.get("cameras", {})
        if not isinstance(cameras, dict):
            cameras = {}

        camera_state = cameras.get(camera_id, {})
        if not isinstance(camera_state, dict):
            camera_state = {}

        state = str(camera_state.get("state", "offline"))
        online = bool(camera_state.get("online", state == "online"))

        return {
            "state": state,
            "online": online,
            "message": camera_state.get("message"),
            "last_error": camera_state.get("last_error"),
            "updated_at": camera_state.get("updated_at"),
            "ingress_id": camera_state.get("ingress_id"),
            "codec": camera_state.get("codec"),
            "mode": camera_state.get("mode"),
        }

    @app.on_event("startup")
    async def on_startup() -> None:
        runtime = get_runtime()
        logger.info(
            "SFU mode enabled with %d cameras. LiveKit API=%s LiveKit WS=%s",
            len(runtime.cameras),
            runtime.settings.livekit_api_url,
            runtime.settings.livekit_ws_url,
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        runtime = get_runtime()
        ingest_snapshot = get_ingest_snapshot()
        return {
            "status": "ok",
            "mode": "sfu",
            "camera_count": len(runtime.cameras),
            "ingest_updated_at": ingest_snapshot.get("updated_at"),
        }

    @app.get("/cameras")
    async def cameras() -> dict[str, list[CameraView]]:
        runtime = get_runtime()
        snapshot = get_ingest_snapshot()
        result: list[CameraView] = []

        for camera in runtime.cameras.values():
            room_name = build_room_name(camera.id, runtime.settings.camera_room_prefix)
            status = build_camera_status(camera.id, snapshot)
            result.append(
                CameraView(
                    id=camera.id,
                    name=camera.name,
                    room_name=room_name,
                    online=status["online"],
                    state=status["state"],
                    message=status["message"],
                )
            )

        return {"cameras": result}

    @app.get("/status")
    async def status(camera_id: str | None = None) -> dict[str, Any]:
        runtime = get_runtime()
        snapshot = get_ingest_snapshot()

        if camera_id:
            camera = get_camera_or_404(camera_id)
            return {
                "camera_id": camera.id,
                "camera_name": camera.name,
                "room_name": build_room_name(camera.id, runtime.settings.camera_room_prefix),
                "status": build_camera_status(camera.id, snapshot),
            }

        checks = []
        for camera in runtime.cameras.values():
            checks.append(
                {
                    "camera_id": camera.id,
                    "camera_name": camera.name,
                    "room_name": build_room_name(camera.id, runtime.settings.camera_room_prefix),
                    "status": build_camera_status(camera.id, snapshot),
                }
            )

        return {
            "updated_at": snapshot.get("updated_at"),
            "cameras": checks,
        }

    @app.get("/viewer/session", response_model=ViewerSessionResponse)
    async def viewer_session(camera_id: str) -> ViewerSessionResponse:
        runtime = get_runtime()
        camera = get_camera_or_404(camera_id)
        room_name = build_room_name(camera.id, runtime.settings.camera_room_prefix)
        identity = f"viewer-{camera.id}-{secrets.token_hex(4)}"
        token = build_viewer_token(runtime.settings, room_name=room_name, identity=identity)

        return ViewerSessionResponse(
            camera_id=camera.id,
            camera_name=camera.name,
            room_name=room_name,
            livekit_url=runtime.settings.livekit_ws_url,
            token=token,
            identity=identity,
        )

    @app.post("/offer")
    async def offer_deprecated() -> dict[str, str]:
        raise HTTPException(
            status_code=410,
            detail="Deprecated endpoint. Use /viewer/session and connect to LiveKit SFU instead.",
        )

    @app.get("/")
    async def index() -> FileResponse:
        print("Serving frontend from", FRONTEND_FILE)
        if not FRONTEND_FILE.exists():
            raise HTTPException(status_code=500, detail="Missing frontend file")
        return FileResponse(
            FRONTEND_FILE,
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    return app


app = create_app()
