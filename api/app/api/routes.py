from __future__ import annotations

import time

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status

from app.core.http_errors import http_error
from app.core.settings import settings
from app.core.session_store import SessionStore
from app.domain.access_control import validate_user_access
from app.infrastructure.external_jwt_verifier import ExternalJWTVerifier
from app.infrastructure.keycloak_client import KeycloakClient
from app.infrastructure.principal_claims import principal_from_payload
from app.infrastructure.whep_proxy import ProxyResponse, WHEPProxy
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse
from app.schemas.stream import StreamResponse
from app.usecases.prepare_stream import StreamPreparationService

router = APIRouter()
service = StreamPreparationService()
session_store = SessionStore()
keycloak_client = KeycloakClient()
external_jwt_verifier = ExternalJWTVerifier()
whep_proxy = WHEPProxy()
SESSION_COOKIE_NAME = "stream_session"

def _resolve_whep_url(device_name: str) -> str:
    path = str(router.url_path_for("whep_offer", device_name=device_name))
    if settings.whep_url:
        return settings.whep_url.rstrip("/") + path
    return path


def _get_active_session(session_id: str | None):
    session = session_store.get(session_id)
    if not session:
        raise http_error(
            status_code=401,
            code="session_missing_or_expired",
            message="Sessao ausente ou expirada",
        )
    return session


def _principal_from_token(token: str):
    payload = external_jwt_verifier.verify(token)
    return principal_from_payload(payload, token)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1]


def _principal_from_session(stream_session: str | None):
    session = _get_active_session(stream_session)
    return _principal_from_token(session.token)


def _principal_from_request_auth(
    authorization: str | None,
    stream_session: str | None,
):
    bearer = _extract_bearer_token(authorization)
    if bearer:
        return _principal_from_token(bearer)
    if stream_session:
        return _principal_from_session(stream_session)
    raise http_error(
        status_code=401,
        code="stream_auth_missing",
        message="Autenticacao ausente",
    )


def _proxy_response(
    request: Request,
    result: ProxyResponse,
) -> Response:
    headers = dict(result.headers)
    if result.session_id:
        headers["Location"] = str(
            request.url_for("whep_session", session_id=result.session_id)
        )
    return Response(
        content=result.content,
        status_code=result.status_code,
        headers=headers,
    )


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
    request: Request,
    stream_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    principal = _principal_from_session(stream_session)

    try:
        return service.prepare_stream(
            principal=principal,
            device_name=device_name,
            whep_url=str(request.url_for("whep_offer", device_name=device_name)),
            client_auth_type="session",
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
    request: Request,
    authorization: str | None = Header(None),
):
    token = _extract_bearer_token(authorization)
    if not token:
        raise http_error(
            status_code=401,
            code="bearer_token_missing",
            message="Token Bearer ausente",
        )

    principal = _principal_from_token(token)

    try:
        return service.prepare_stream(
            principal=principal,
            device_name=camera,
            whep_url=_resolve_whep_url(camera),
            client_auth_type="bearer",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise http_error(
            status_code=500,
            code="internal_error",
            message="Erro interno",
        ) from exc


@router.post("/whep/{device_name}/whep", name="whep_offer")
async def whep_offer(
    device_name: str,
    request: Request,
    authorization: str | None = Header(None),
    stream_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    principal = _principal_from_request_auth(authorization, stream_session)
    offer_sdp = await request.body()
    service.ensure_stream_ready(principal, device_name)
    result = whep_proxy.start_session(principal, device_name, offer_sdp)
    return _proxy_response(request, result)


@router.api_route("/whep/session/{session_id}", methods=["PATCH", "DELETE"], name="whep_session")
async def whep_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(None),
    stream_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    principal = _principal_from_request_auth(authorization, stream_session)
    session = whep_proxy.get_session(session_id)
    if not session:
        raise http_error(
            status_code=404,
            code="whep_session_not_found",
            message="Sessao WHEP nao encontrada",
        )
    if session.subject != principal.subject or not validate_user_access(
        principal.roles,
        session.device_name,
    ):
        raise http_error(
            status_code=403,
            code="camera_access_denied",
            message="Denied access to this camera",
        )

    body = await request.body()
    result = whep_proxy.continue_session(
        principal=principal,
        session=session,
        method=request.method,
        body=body,
        content_type=request.headers.get("content-type"),
        if_match=request.headers.get("if-match"),
    )
    return _proxy_response(request, result)
