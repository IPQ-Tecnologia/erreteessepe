from datetime import timedelta

from livekit import api

from .config import Settings


def build_viewer_token(settings: Settings, room_name: str, identity: str) -> str:
    access_token_cls = getattr(api, "AccessToken", None)
    video_grants_cls = getattr(api, "VideoGrants", None)
    if access_token_cls is None or video_grants_cls is None:
        raise RuntimeError("Could not resolve AccessToken / VideoGrants from livekit-api package")

    try:
        grants = video_grants_cls(
            room_join=True,
            room=room_name,
            can_subscribe=True,
            can_publish=False,
        )
    except TypeError:
        grants = video_grants_cls(room_join=True, room=room_name)

    token = (
        access_token_cls(api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grants)
    )

    if hasattr(token, "with_ttl"):
        token = token.with_ttl(timedelta(seconds=settings.viewer_token_ttl_seconds))

    return token.to_jwt()
