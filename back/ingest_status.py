import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_ingest_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"updated_at": None, "cameras": {}}

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {"updated_at": None, "cameras": {}}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"updated_at": None, "cameras": {}}

    if not isinstance(parsed, dict):
        return {"updated_at": None, "cameras": {}}

    cameras = parsed.get("cameras")
    if not isinstance(cameras, dict):
        parsed["cameras"] = {}

    if "updated_at" not in parsed:
        parsed["updated_at"] = None

    return parsed


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp_path.replace(path)


class IngestStatusStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = asyncio.Lock()
        self._state = load_ingest_status(path)

    async def update_camera(self, camera_id: str, **fields: Any) -> None:
        async with self._lock:
            cameras = self._state.setdefault("cameras", {})
            camera_state = cameras.get(camera_id, {})
            camera_state.update(fields)
            camera_state["camera_id"] = camera_id
            camera_state["updated_at"] = utc_now_iso()
            cameras[camera_id] = camera_state
            self._state["updated_at"] = utc_now_iso()
            _write_json_atomic(self._path, self._state)

    async def set_all_offline(self, camera_ids: list[str]) -> None:
        async with self._lock:
            cameras = self._state.setdefault("cameras", {})
            now = utc_now_iso()
            for camera_id in camera_ids:
                camera_state = cameras.get(camera_id, {})
                camera_state.update(
                    {
                        "camera_id": camera_id,
                        "state": "offline",
                        "online": False,
                        "message": "ingest service not started",
                        "updated_at": now,
                    }
                )
                cameras[camera_id] = camera_state

            self._state["updated_at"] = now
            _write_json_atomic(self._path, self._state)
