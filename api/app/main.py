import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as stream_router
FRONT_DIR = "/app/front"


def create_app() -> FastAPI:
    app = FastAPI(title="RTSP to WebRTC API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(stream_router)

    if not os.path.isdir(FRONT_DIR):
        raise RuntimeError(f"Directory '{FRONT_DIR}' does not exist")
    app.mount("/static", StaticFiles(directory=FRONT_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def login_page():
        return FileResponse(os.path.join(FRONT_DIR, "index.html"))

    @app.get("/player", include_in_schema=False)
    def player_page():
        return FileResponse(os.path.join(FRONT_DIR, "player.html"))

    return app


app = create_app()
