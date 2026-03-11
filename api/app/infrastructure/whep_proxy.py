from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from requests import RequestException

from app.core.http_errors import http_error
from app.core.settings import settings
from app.core.whep_session_store import WHEPSession, WHEPSessionStore
from app.infrastructure.mediamtx_token_service import MediaMTXTokenService
from app.infrastructure.principal_claims import VerifiedPrincipal


@dataclass(frozen=True)
class ProxyResponse:
    status_code: int
    content: bytes
    headers: dict[str, str]
    session_id: str | None = None


class WHEPProxy:
    def __init__(
        self,
        token_service: MediaMTXTokenService | None = None,
        session_store: WHEPSessionStore | None = None,
    ) -> None:
        self._token_service = token_service or MediaMTXTokenService()
        self._session_store = session_store or WHEPSessionStore()
        self._timeout = 15

    def start_session(
        self,
        principal: VerifiedPrincipal,
        device_name: str,
        offer_sdp: bytes,
    ) -> ProxyResponse:
        upstream_url = self._upstream_offer_url(device_name)
        response = self._request(
            method="POST",
            url=upstream_url,
            principal=principal,
            headers={"Content-Type": "application/sdp"},
            body=offer_sdp,
        )

        headers = self._response_headers(response)
        session_id = None
        location = response.headers.get("Location")
        if response.ok and location:
            session = self._session_store.create(
                subject=principal.subject,
                device_name=device_name,
                upstream_url=urljoin(upstream_url, location),
            )
            session_id = session.session_id

        return ProxyResponse(
            status_code=response.status_code,
            content=response.content,
            headers=headers,
            session_id=session_id,
        )

    def continue_session(
        self,
        principal: VerifiedPrincipal,
        session: WHEPSession,
        method: str,
        body: bytes,
        content_type: str | None,
        if_match: str | None,
    ) -> ProxyResponse:
        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        if if_match:
            headers["If-Match"] = if_match

        response = self._request(
            method=method,
            url=session.upstream_url,
            principal=principal,
            headers=headers,
            body=body,
        )

        if method == "DELETE" or response.status_code in {404, 410}:
            self._session_store.delete(session.session_id)

        return ProxyResponse(
            status_code=response.status_code,
            content=response.content,
            headers=self._response_headers(response),
            session_id=None,
        )

    def get_session(self, session_id: str | None) -> WHEPSession | None:
        return self._session_store.get(session_id)

    def delete_session(self, session_id: str | None) -> None:
        self._session_store.delete(session_id)

    def _request(
        self,
        method: str,
        url: str,
        principal: VerifiedPrincipal,
        headers: dict[str, str],
        body: bytes,
    ) -> requests.Response:
        token = self._token_service.issue_viewer_token(
            subject=principal.subject,
            permissions=[{"action": "read", "path": ""}],
        )
        request_headers = {
            **headers,
            "Authorization": f"Bearer {token}",
        }

        try:
            return requests.request(
                method=method,
                url=url,
                headers=request_headers,
                data=body,
                timeout=self._timeout,
            )
        except RequestException as exc:
            raise http_error(
                status_code=503,
                code="mediamtx_unavailable",
                message="MediaMTX indisponivel.",
            ) from exc

    @staticmethod
    def _response_headers(response: requests.Response) -> dict[str, str]:
        headers: dict[str, str] = {}
        for name in ("Content-Type", "ETag", "Accept-Patch", "Link"):
            value = response.headers.get(name)
            if value:
                headers[name] = value
        return headers

    @staticmethod
    def _upstream_offer_url(device_name: str) -> str:
        return f"http://{settings.mediamtx_host}:{settings.webrtc_port}/{device_name}/whep"
