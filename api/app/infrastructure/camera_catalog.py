from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote, urlsplit

from app.core.http_errors import http_error
from app.core.settings import settings
from app.domain.camera_catalog import CameraDefinition
from app.domain.cameras import CAMERAS

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError: 
    Redis = None

    class RedisError(Exception):
        pass


class CameraCatalog:
    def __init__(self) -> None:
        self._redis_client: Redis | None = None

    def get(self, device_name: str) -> CameraDefinition:
        camera = self._get_from_redis(device_name)
        if camera:
            return camera

        legacy_rtsp = CAMERAS.get(device_name)
        if legacy_rtsp:
            return self._from_legacy_rtsp(device_name, legacy_rtsp)

        raise http_error(
            status_code=404,
            code="camera_not_found",
            message=f"Camera '{device_name}' nao cadastrada.",
        )

    def list_known_ids(self) -> set[str]:
        known = set(CAMERAS.keys())

        if not settings.camera_redis_url:
            return known

        client = self._client()
        if client is None:
            return known

        try:
            for raw_key in client.scan_iter(match=f"{settings.camera_redis_prefix}*"):
                key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
                known.add(key.removeprefix(settings.camera_redis_prefix))
        except RedisError:
            return known

        return known

    def _get_from_redis(self, device_name: str) -> CameraDefinition | None:
        if not settings.camera_redis_url:
            return None

        client = self._client()
        if client is None:
            return None

        key = f"{settings.camera_redis_prefix}{device_name}"

        try:
            raw_value = client.get(key)
            if raw_value is not None:
                payload = json.loads(self._decode(raw_value))
                return self._from_mapping(device_name, payload)

            hash_value = client.hgetall(key)
            if hash_value:
                payload = {
                    self._decode(field): self._decode(value)
                    for field, value in hash_value.items()
                }
                return self._from_mapping(device_name, payload)
        except json.JSONDecodeError as exc:
            raise http_error(
                status_code=502,
                code="camera_catalog_invalid",
                message=f"Data from camera '{device_name}' is not valid JSON.",
            ) from exc
        except RedisError as exc:
            raise http_error(
                status_code=503,
                code="camera_catalog_unavailable",
                message="It was not possible to access the camera catalog because Redis is unavailable.",
            ) from exc

        return None

    def _from_mapping(self, device_name: str, payload: dict[str, Any]) -> CameraDefinition:
        manufacturer = self._required_value(payload, "manufacturer", "fabricante")
        host = self._required_value(payload, "ip", "host")
        username = self._required_value(payload, "username", "usuario", "user")
        password = self._required_value(payload, "password", "senha", "pass")

        port = self._int_value(payload, "port", default=554)
        channel = self._int_value(payload, "channel", default=1)
        subtype = self._int_value(payload, "subtype", default=0)
        rtsp_path = self._optional_value(payload, "rtsp_path", "path")
        rtsp_url = self._optional_value(payload, "rtsp_url", "url")

        return CameraDefinition(
            device_name=device_name,
            manufacturer=manufacturer,
            host=host,
            username=username,
            password=password,
            port=port,
            channel=channel,
            subtype=subtype,
            rtsp_path=rtsp_path,
            rtsp_url=rtsp_url,
        )

    @staticmethod
    def _from_legacy_rtsp(device_name: str, rtsp_url: str) -> CameraDefinition:
        parsed = urlsplit(rtsp_url)
        if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
            raise http_error(
                status_code=502,
                code="camera_url_invalid",
                message=f"Legacy RTSP URL for camera '{device_name}' is invalid.",
            )

        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")

        return CameraDefinition(
            device_name=device_name,
            manufacturer="generic",
            host=parsed.hostname,
            username=username,
            password=password,
            port=parsed.port or 554,
            rtsp_url=rtsp_url,
        )

    def _client(self) -> Redis | None:
        if Redis is None:
            return None
        if self._redis_client is None:
            self._redis_client = Redis.from_url(
                settings.camera_redis_url,
                socket_timeout=settings.camera_redis_timeout_seconds,
                decode_responses=False,
            )
        return self._redis_client

    @staticmethod
    def _decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    @staticmethod
    def _required_value(payload: dict[str, Any], *keys: str) -> str:
        value = CameraCatalog._optional_value(payload, *keys)
        if value:
            return value
        joined = ", ".join(keys)
        raise http_error(
            status_code=502,
            code="camera_catalog_invalid",
            message=f"Invalid camera registration. Required field missing: {joined}.",
        )

    @staticmethod
    def _optional_value(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _int_value(payload: dict[str, Any], key: str, default: int) -> int:
        value = payload.get(key)
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise http_error(
                status_code=502,
                code="camera_catalog_invalid",
                message=f"Field '{key}' is invalid in camera registration.",
            ) from exc

