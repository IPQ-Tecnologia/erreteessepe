from __future__ import annotations

from collections.abc import Set

from app.core.settings import settings


def validate_user_access(roles: Set[str], device_name: str) -> bool:
    del device_name # todo: validar posteriormente se o usuário pode acessar aquela câmera
    return settings.stream_access_role in roles
