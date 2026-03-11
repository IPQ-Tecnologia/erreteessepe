from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import settings


@dataclass(frozen=True)
class VerifiedPrincipal:
    subject: str
    username: str
    roles: frozenset[str]
    external_token: str


def _extract_path(payload: dict, path: str):
    current = payload
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current

# as roles estão dentro do path: resource_access.inteligencia_back.roles[]
def extract_roles(payload: dict) -> frozenset[str]:
    roles: set[str] = set()
    for path in settings.stream_roles_claim_path.split(","):
        raw_roles = _extract_path(payload, path.strip())
        if not isinstance(raw_roles, list):
            continue
        roles.update(
            role.strip()
            for role in raw_roles
            if isinstance(role, str) and role.strip()
        )
    return frozenset(roles)


def principal_from_payload(payload: dict, token: str) -> VerifiedPrincipal:
    subject = str(payload.get("sub") or "").strip()
    username = str(
        payload.get("preferred_username")
        or payload.get("username")
        or subject
    ).strip()

    return VerifiedPrincipal(
        subject=subject or username,
        username=username or subject,
        roles=extract_roles(payload),
        external_token=token,
    )
