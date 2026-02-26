from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.stream import StreamResponse
from app.usecases.prepare_stream import StreamPreparationService

router = APIRouter()
service = StreamPreparationService()


@router.get("/stream/{device_name}", response_model=StreamResponse)
def get_stream(device_name: str, user_id: str = Query(..., description="ID do usuario")):
    try:
        return service.prepare_stream(user_id=user_id, device_name=device_name)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Erro interno") from exc
