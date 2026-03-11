from __future__ import annotations

import time

from fastapi import APIRouter, Cookie, Header, HTTPException, Response, status

from app.core.http_errors import http_error
from app.core.settings import settings
from app.core.session_store import SessionStore
from app.infrastructure.keycloak_client import KeycloakClient
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse
from app.schemas.stream import StreamResponse
from app.usecases.prepare_stream import StreamPreparationService

router = APIRouter()
service = StreamPreparationService()
session_store = SessionStore()
keycloak_client = KeycloakClient()
SESSION_COOKIE_NAME = "stream_session"


def _get_active_session(session_id: str | None):
    session = session_store.get(session_id)
    if not session:
        raise http_error(
            status_code=401,
            code="session_missing_or_expired",
            message="Sessao ausente ou expirada",
        )
    return session


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response):
    if settings.auth_provider != "keycloak":
        raise http_error(
            status_code=400,
            code="external_login_unavailable",
            message="Login externo indisponivel",
        )

    token, expires_at = keycloak_client.issue_token_with_exp(payload.username, payload.password)
    session = session_store.create(payload.username, token, expires_at)
    max_age = max(60, session.expires_at - int(time.time()) - 10)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )
    return LoginResponse(username=session.username, expires_at=session.expires_at)


@router.get("/auth/me", response_model=MeResponse)
def me(stream_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME)):
    session = session_store.get(stream_session)
    if not session:
        return MeResponse(authenticated=False)
    return MeResponse(authenticated=True, username=session.username, access_token=session.token)

@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, stream_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME)):
    session_store.delete(stream_session)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return None


@router.get("/stream/{device_name}", response_model=StreamResponse)
def get_stream(
    device_name: str,
    stream_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    viewer_token = None
    user_id = "anonymous"
    if settings.auth_provider == "keycloak":
        session = _get_active_session(stream_session)
        viewer_token = session.token
        user_id = session.username

    try:
        return service.prepare_stream(
            user_id=user_id,
            device_name=device_name,
            viewer_token=viewer_token,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise http_error(
            status_code=500,
            code="internal_error",
            message="Erro interno",
        ) from exc


@router.get("/api/stream/{camera}", response_model=StreamResponse)
def get_stream_by_query(
    camera: str,
    authorization: str | None = Header(None),
):
    viewer_token = None
    user_id = "anonymous"

    print(f"Authorization header: {authorization}")

    if settings.auth_provider == "keycloak":
        if not authorization or not authorization.lower().startswith("bearer "):
            raise http_error(
                status_code=401,
                code="bearer_token_missing",
                message="Token Bearer ausente",
            )
        viewer_token = authorization.split(" ", 1)[1]
        user_id = "bearer_user"
    print(f"Extracted viewer_token: {viewer_token}")
    print(f"Extracted user_id: {user_id}")
    try:
        return service.prepare_stream(
            user_id=user_id,
            device_name=camera,
            viewer_token=viewer_token,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise http_error(
            status_code=500,
            code="internal_error",
            message="Erro interno",
        ) from exc
