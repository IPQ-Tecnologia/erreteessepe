from __future__ import annotations

import time

import requests
from requests import RequestException

from app.core.http_errors import http_error
from app.core.settings import settings
from app.infrastructure.keycloak_client import KeycloakClient
from app.infrastructure.mediamtx_token_service import MediaMTXTokenService


class MediaMTXClient:
    def __init__(self) -> None:
        self._base_url = settings.mediamtx_api
        self._timeout = 5
        self._keycloak_client = KeycloakClient()
        self._token_service = MediaMTXTokenService()

    def path_exists(self, device_name: str) -> bool:
        response = self._get_path(device_name)
        if response.status_code == 404:
            return False
        if response.status_code != 200:
            raise http_error(
                status_code=502,
                code="mediamtx_query_failed",
                message="Erro ao consultar o MediaMTX.",
            )
        return True

    def get_path_info(self, device_name: str) -> dict:
        response = self._get_path(device_name)
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            raise http_error(
                status_code=502,
                code="mediamtx_query_failed",
                message="Erro ao consultar o status da camera no MediaMTX.",
            )
        return response.json()

    def wait_until_ready(self, device_name: str, timeout_seconds: float = 8.0) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            info = self.get_path_info(device_name)
            if info.get("ready"):
                return
            time.sleep(0.4)

        raise http_error(
            status_code=504,
            code="camera_start_timeout",
            message="A camera respondeu, mas o stream nao ficou pronto a tempo no MediaMTX.",
        )

    def create_path(self, device_name: str, rtsp_source: str) -> None:
        payload = {"source": rtsp_source}
        try:
            response = requests.post(
                f"{self._base_url}/v3/config/paths/add/{device_name}",
                auth=self._basic_auth(),
                headers=self._auth_headers(),
                json=payload,
                timeout=self._timeout,
            )
        except RequestException as exc:
            raise http_error(
                status_code=503,
                code="mediamtx_unavailable",
                message="MediaMTX indisponivel.",
            ) from exc

        if response.status_code not in (200, 201, 409):
            raise http_error(
                status_code=502,
                code="mediamtx_path_create_failed",
                message="Nao foi possivel criar a rota da camera no MediaMTX.",
            )

    def remove_path(self, device_name: str) -> None:
        try:
            response = requests.delete(
                f"{self._base_url}/v3/config/paths/delete/{device_name}",
                auth=self._basic_auth(),
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except RequestException as exc:
            raise http_error(
                status_code=503,
                code="mediamtx_unavailable",
                message="MediaMTX indisponivel.",
            ) from exc

        if response.status_code not in (200, 201, 204):
            raise http_error(
                status_code=502,
                code="mediamtx_path_delete_failed",
                message="Nao foi possivel remover a rota da camera no MediaMTX.",
            )

    def get_viewer_count(self, device_name: str) -> int:
        try:
            response = requests.get(
                f"{self._base_url}/v3/paths/list",
                auth=self._basic_auth(),
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except RequestException:
            return 0
        if response.status_code != 200:
            return 0

        data = response.json()
        for item in data.get("items", []):
            if item.get("name") == device_name:
                return len(item.get("readers", []))
        return 0

    def _get_path(self, device_name: str) -> requests.Response:
        try:
            return requests.get(
                f"{self._base_url}/v3/paths/get/{device_name}",
                auth=self._basic_auth(),
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except RequestException as exc:
            raise http_error(
                status_code=503,
                code="mediamtx_unavailable",
                message="MediaMTX indisponivel.",
            ) from exc

    def _auth_headers(self) -> dict | None:
        if settings.media_auth_mode == "internal_jwt":
            token = self._token_service.issue_api_token()
            return {"Authorization": f"Bearer {token}"}
        if settings.auth_provider != "keycloak":
            return None
        token = self._keycloak_client.issue_token(
            settings.mediamtx_api_user,
            settings.mediamtx_api_pass,
        )
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _basic_auth() -> tuple[str, str] | None:
        if settings.media_auth_mode == "internal_jwt":
            return None
        if settings.auth_provider == "keycloak":
            return None
        return (settings.mediamtx_api_user, settings.mediamtx_api_pass)
