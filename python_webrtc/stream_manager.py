import asyncio
import logging

from aiortc.contrib.media import MediaPlayer, MediaRelay

from .config import LOGGER_NAME, Settings
from .models import Camera


logger = logging.getLogger(LOGGER_NAME)


class CameraStreamManager:
    def __init__(self, cameras: dict[str, Camera], settings: Settings):
        self._cameras = cameras
        self._settings = settings
        self._relay = MediaRelay()
        self._players: dict[str, MediaPlayer] = {}
        self._lock = asyncio.Lock()

    def list_cameras(self) -> list[dict[str, str]]:
        return [{"id": camera.id, "name": camera.name} for camera in self._cameras.values()]

    def get_camera(self, camera_id: str) -> Camera:
        camera = self._cameras.get(camera_id)
        if camera is None:
            raise KeyError(camera_id)
        return camera

    async def get_video_track(self, camera_id: str):
        camera = self.get_camera(camera_id)

        async with self._lock:
            player = self._players.get(camera_id)
            if player is None:
                logger.info("Opening RTSP stream for camera '%s'", camera_id)
                player = MediaPlayer(
                    camera.rtsp_url,
                    format="rtsp",
                    options=self._build_rtsp_options(),
                )
                self._players[camera_id] = player

        if player.video is None:
            raise RuntimeError(f"Camera '{camera_id}' has no video track")

        return self._relay.subscribe(player.video, buffered=self._settings.webrtc_relay_buffered)

    async def close(self) -> None:
        async with self._lock:
            for camera_id, player in self._players.items():
                logger.info("Closing player for camera '%s'", camera_id)
                player.stop()
            self._players.clear()

    def _build_rtsp_options(self) -> dict[str, str]:
        return {
            "rtsp_transport": self._settings.rtsp_transport,
            "stimeout": str(self._settings.rtsp_timeout_us),
            "fflags": "nobuffer",
            "flags": "low_delay",
            "max_delay": str(self._settings.rtsp_max_delay_us),
            "reorder_queue_size": str(self._settings.rtsp_reorder_queue_size),
        }
