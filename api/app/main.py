import logging
import os
import sys
import threading
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as stream_router
from app.core.http_errors import error_detail
from app.infrastructure.mediamtx_token_service import MediaMTXTokenService

logger = logging.getLogger("stream-api")


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    logger.setLevel(logging.INFO)
    sys.excepthook = _log_unhandled_exception
    threading.excepthook = _log_thread_exception


def _log_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical(
        "Unhandled process-level exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


def _log_thread_exception(args: threading.ExceptHookArgs) -> None:
    logger.critical(
        "Unhandled exception in thread %s",
        args.thread.name if args.thread else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _detail_summary(detail: object) -> str:
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
        if code and message:
            return f"{code}: {message}"
    return str(detail)


def _log_http_exception(request: Request, exc: HTTPException) -> None:
    message = (
        "HTTPException on %s %s -> status=%s detail=%s"
        % (request.method, request.url, exc.status_code, _detail_summary(exc.detail))
    )
    if exc.status_code >= 500 or exc.__cause__ is not None or exc.__context__ is not None:
        logger.error(message, exc_info=(type(exc), exc, exc.__traceback__))
        return
    logger.warning(message)


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
    _configure_logging()
    front_dir = _resolve_front_dir()
    mediamtx_token_service = MediaMTXTokenService()
    app = FastAPI(title="RTSP to WebRTC API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(stream_router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        _log_http_exception(request, exc)
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception on %s %s",
            request.method,
            request.url,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content=error_detail("internal_error", "Erro interno"),
        )

    app.mount("/static", StaticFiles(directory=front_dir), name="static")

    @app.get("/.well-known/jwks.json", include_in_schema=False)
    def media_auth_jwks():
        return mediamtx_token_service.jwks()

    @app.get("/", include_in_schema=False)
    def login_page():
        return FileResponse(os.path.join(front_dir, "index.html"))

    @app.get("/player", include_in_schema=False)
    def player_page():
        return FileResponse(os.path.join(front_dir, "player.html"))

    return app


app = create_app()
