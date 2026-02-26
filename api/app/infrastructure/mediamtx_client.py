from __future__ import annotations

import time

import requests
from fastapi import HTTPException

from app.core.settings import settings


class MediaMTXClient:
    def __init__(self) -> None:
        self._base_url = settings.mediamtx_api
        self._auth = (settings.mediamtx_api_user, settings.mediamtx_api_pass)
        self._timeout = 5

    def path_exists(self, device_name: str) -> bool:
        response = self._get_path(device_name)
        if response.status_code == 404:
            return False
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Erro ao consultar MediaMTX")
        return True

    def get_path_info(self, device_name: str) -> dict:
        response = self._get_path(device_name)
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail="Erro ao consultar status da camera no MediaMTX",
            )
        return response.json()

    def wait_until_ready(self, device_name: str, timeout_seconds: float = 8.0) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            info = self.get_path_info(device_name)
            if info.get("ready"):
                return
            time.sleep(0.4)

        raise HTTPException(
            status_code=504,
            detail="A camera nao ficou pronta a tempo no MediaMTX",
        )

    def create_path(self, device_name: str, rtsp_source: str) -> None:
        payload = {"source": rtsp_source}
        response = requests.post(
            f"{self._base_url}/v3/config/paths/add/{device_name}",
            auth=self._auth,
            json=payload,
            timeout=self._timeout,
        )

        if response.status_code not in (200, 201, 409):
            raise HTTPException(status_code=500, detail=response.text)

    def remove_path(self, device_name: str) -> None:
        response = requests.post(
            f"{self._base_url}/v3/config/paths/remove/{device_name}",
            auth=self._auth,
            timeout=self._timeout,
        )

        if response.status_code not in (200, 404):
            raise HTTPException(status_code=500, detail=response.text)

    def get_viewer_count(self, device_name: str) -> int:
        response = requests.get(
            f"{self._base_url}/v3/paths/list",
            auth=self._auth,
            timeout=self._timeout,
        )
        if response.status_code != 200:
            return 0

        data = response.json()
        for item in data.get("items", []):
            if item.get("name") == device_name:
                return len(item.get("readers", []))
        return 0

    def _get_path(self, device_name: str) -> requests.Response:
        return requests.get(
            f"{self._base_url}/v3/paths/get/{device_name}",
            auth=self._auth,
            timeout=self._timeout,
        )
