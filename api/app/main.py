from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .services import prepare_stream
import logging
import os
from fastapi.middleware.cors import CORSMiddleware # <--- Importe isso

app = FastAPI()
logger = logging.getLogger("uvicorn")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Libera para qualquer origem
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend dentro do container
FRONT_DIR = "/app/front"

if not os.path.isdir(FRONT_DIR):
    raise RuntimeError(f"Directory '{FRONT_DIR}' does not exist")

app.mount("/static", StaticFiles(directory=FRONT_DIR), name="static")


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(os.path.join(FRONT_DIR, "index.html"))


@app.get("/stream/{device_name}")
def get_stream(
    device_name: str,
    user_id: str = Query(..., description="ID do usuário"),
):
    logger.info(
        "stream request",
        extra={"user_id": user_id, "device": device_name},
    )

    try:
        return prepare_stream(user_id, device_name)
    except HTTPException:
        raise
    except Exception:
        logger.exception("erro inesperado ao preparar stream")
        raise HTTPException(status_code=500, detail="Erro interno")
