from app.infrastructure.mediamtx_client import MediaMTXClient
from app.usecases.prepare_stream import StreamPreparationService

_service = StreamPreparationService()
_client = MediaMTXClient()


def get_rtsp_source(device_name: str) -> str:
    return _service._get_rtsp_source(device_name)


def path_exists(device_name: str) -> bool:
    return _client.path_exists(device_name)


def get_path_info(device_name: str) -> dict:
    return _client.get_path_info(device_name)


def wait_until_ready(device_name: str, timeout_seconds: float = 8.0):
    return _client.wait_until_ready(device_name, timeout_seconds=timeout_seconds)


def create_path(device_name: str, rtsp_source: str):
    return _client.create_path(device_name, rtsp_source)


def remove_path(device_name: str):
    return _client.remove_path(device_name)


def get_viewer_count(device_name: str) -> int:
    return _client.get_viewer_count(device_name)


def cleanup_if_idle(device_name: str):
    return _service.cleanup_if_idle(device_name)


def prepare_stream(
    user_id: str,
    device_name: str,
    viewer_token: str | None = None,
) -> dict:
    return _service.prepare_stream(
        user_id,
        device_name,
        viewer_token=viewer_token,
    ).model_dump()
