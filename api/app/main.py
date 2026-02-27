import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as stream_router


def _resolve_front_dir() -> str:
    configured = os.getenv("FRONT_DIR")
    candidates = []
    if configured:
        candidates.append(configured)
    candidates.extend(
        [
            "/app/front",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../front")),
        ]
    )

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    raise RuntimeError(
        "Frontend directory not found. Set FRONT_DIR or provide /app/front or ./front."
    )


def create_app() -> FastAPI:
    front_dir = _resolve_front_dir()
    app = FastAPI(title="RTSP to WebRTC API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(stream_router)

    app.mount("/static", StaticFiles(directory=front_dir), name="static")

    @app.get("/", include_in_schema=False)
    def login_page():
        return FileResponse(os.path.join(front_dir, "index.html"))

    @app.get("/player", include_in_schema=False)
    def player_page():
        return FileResponse(os.path.join(front_dir, "player.html"))

    return app


app = create_app()
