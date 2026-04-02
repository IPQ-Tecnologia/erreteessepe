from __future__ import annotations

from collections import defaultdict
import logging

from fastapi import HTTPException

from app.core.http_errors import http_error
from app.core.whep_session_store import WHEPSessionStore
from app.domain.access_control import validate_user_access
from app.infrastructure.camera_catalog import CameraCatalog
from app.infrastructure.mediamtx_client import MediaMTXClient
from app.infrastructure.principal_claims import VerifiedPrincipal
from app.schemas.stream import (
    RoomInspectionResponse,
    RoomInspectionSubscriber,
    RoomState,
    StaleRoomSessions,
)

logger = logging.getLogger(__name__)


class RoomInspectionService:
    def __init__(
        self,
        mediamtx: MediaMTXClient | None = None,
        camera_catalog: CameraCatalog | None = None,
        session_store: WHEPSessionStore | None = None,
    ) -> None:
        self._mediamtx = mediamtx or MediaMTXClient()
        self._camera_catalog = camera_catalog or CameraCatalog()
        self._session_store = session_store or WHEPSessionStore()

    def list_rooms(self, principal: VerifiedPrincipal) -> RoomInspectionResponse:
        if not validate_user_access(principal.roles, ""):
            raise http_error(
                status_code=403,
                code="camera_access_denied",
                message="Denied access to cameras",
            )

        subscribers_by_room: dict[str, list[RoomInspectionSubscriber]] = defaultdict(list)
        for session in self._session_store.list_active():
            if not validate_user_access(principal.roles, session.device_name):
                continue
            subscribers_by_room[session.device_name].append(
                RoomInspectionSubscriber(
                    session_id=session.session_id,
                    subject=session.subject,
                    username=session.username or None,
                    connected_at=session.created_at,
                    expires_at=session.expires_at,
                )
            )

        mediamtx_available = True
        mediamtx_error: str | None = None
        path_items: dict[str, dict] = {}
        try:
            for item in self._mediamtx.list_paths():
                name = str(item.get("name") or "").strip()
                if name:
                    path_items[name] = item
        except HTTPException as exc:
            logger.warning(
                "MediaMTX path listing failed while building /api/rooms response",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            mediamtx_available = False
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            mediamtx_error = str(detail.get("message") or detail or exc)

        room_names = set(self._camera_catalog.list_known_ids())
        room_names.update(path_items.keys())
        room_names.update(subscribers_by_room.keys())

        open_rooms: list[RoomState] = []
        closed_rooms: list[RoomState] = []
        stale_sessions: list[StaleRoomSessions] = []

        for room_name in sorted(room_names):
            if not validate_user_access(principal.roles, room_name):
                continue

            path_info = path_items.get(room_name)
            subscribers = sorted(
                subscribers_by_room.get(room_name, []),
                key=lambda item: ((item.username or ""), item.subject, item.session_id),
            )
            if path_info is not None:
                readers = path_info.get("readers")
                reader_count = len(readers) if isinstance(readers, list) else len(subscribers)
                open_rooms.append(
                    RoomState(
                        name=room_name,
                        status="open",
                        has_active_path=True,
                        ready=bool(path_info.get("ready")),
                        reader_count=reader_count,
                        subscriber_count=len(subscribers),
                        subscribers=subscribers,
                    )
                )
                continue

            closed_rooms.append(
                RoomState(
                    name=room_name,
                    status="closed",
                    has_active_path=False,
                    ready=False,
                    reader_count=0,
                    subscriber_count=0,
                    subscribers=[],
                )
            )

            if subscribers:
                stale_sessions.append(
                    StaleRoomSessions(
                        name=room_name,
                        subscriber_count=len(subscribers),
                        subscribers=subscribers,
                    )
                )

        return RoomInspectionResponse(
            mediamtx_available=mediamtx_available,
            mediamtx_error=mediamtx_error,
            open_count=len(open_rooms),
            closed_count=len(closed_rooms),
            stale_count=len(stale_sessions),
            open_rooms=open_rooms,
            closed_rooms=closed_rooms,
            stale_sessions=stale_sessions,
        )
