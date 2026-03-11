from __future__ import annotations

from typing import Any

from app.core.settings import settings

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:
    Redis = None

    class RedisError(Exception):
        pass


class RedisClient:
    def __init__(self) -> None:
        self._client: Redis | None = None

    def get(self) -> Redis | None:
        if Redis is None or not settings.camera_redis_url:
            return None
        if self._client is None:
            self._client = Redis.from_url(
                settings.camera_redis_url,
                socket_timeout=settings.camera_redis_timeout_seconds,
                decode_responses=False,
            )
        return self._client

    @staticmethod
    def decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return str(value)


redis_client = RedisClient()
