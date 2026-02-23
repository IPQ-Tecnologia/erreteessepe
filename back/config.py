import logging
import os
from dataclasses import dataclass
from pathlib import Path


LOGGER_NAME = "rtsp-webrtc"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure_logging(log_level: str) -> None:
    logging.basicConfig(level=log_level, format=LOG_FORMAT)


def _getenv_int(name: str, default: int, minimum: int | None = None) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError:
            logger = logging.getLogger(LOGGER_NAME)
            logger.warning("Invalid integer for %s=%r, falling back to %d", name, raw_value, default)
            value = default

    if minimum is not None:
        value = max(minimum, value)
    return value


def _getenv_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger = logging.getLogger(LOGGER_NAME)
    logger.warning("Invalid boolean for %s=%r, falling back to %s", name, raw_value, default)
    return default


@dataclass(frozen=True)
class Settings:
    log_level: str
    cors_allow_origin: str
    app_port: int
    livekit_api_url: str
    livekit_ws_url: str
    livekit_api_key: str
    livekit_api_secret: str
    viewer_token_ttl_seconds: int
    camera_room_prefix: str
    ingest_instance_tag: str
    ingest_participant_identity_prefix: str
    ingest_status_file: str
    rtsp_transport: str
    rtsp_rw_timeout_us: int
    ingest_retry_base_seconds: int
    ingest_retry_max_seconds: int
    ingest_recreate_ingress_on_retry: bool
    ingest_ffmpeg_loglevel: str
    ingest_publish_protocol: str
    ingest_publish_host_override: str
    ingest_probe_size_bytes: int
    ingest_analyze_duration_us: int
    ingest_reorder_queue_size: int
    ingest_max_delay_us: int
    ingest_transcode_bitrate: str
    ingest_transcode_bufsize: str
    ingest_transcode_gop: int
    ingest_transcode_preset: str
    ingest_transcode_threads: int
    ingest_enable_h264_passthrough: bool

    @property
    def ingest_status_path(self) -> Path:
        return Path(self.ingest_status_file)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            cors_allow_origin=os.getenv("CORS_ALLOW_ORIGIN", "*"),
            app_port=_getenv_int("APP_PORT", 8000, minimum=1),
            livekit_api_url=os.getenv("LIVEKIT_API_URL", "http://localhost:7880"),
            livekit_ws_url=os.getenv("LIVEKIT_WS_URL", "ws://localhost:7880"),
            livekit_api_key=os.getenv("LIVEKIT_API_KEY", "devkey"),
            livekit_api_secret=os.getenv("LIVEKIT_API_SECRET", "devsecret_devsecret_devsecret_2026"),
            viewer_token_ttl_seconds=_getenv_int("VIEWER_TOKEN_TTL_SECONDS", 3600, minimum=60),
            camera_room_prefix=os.getenv("CAMERA_ROOM_PREFIX", "camera"),
            ingest_instance_tag=os.getenv("INGEST_INSTANCE_TAG", "").strip(),
            ingest_participant_identity_prefix=os.getenv("INGEST_PARTICIPANT_IDENTITY_PREFIX", "ingress").strip(),
            ingest_status_file=os.getenv("INGEST_STATUS_FILE", "runtime/ingest-status.json"),
            rtsp_transport=os.getenv("RTSP_TRANSPORT", "tcp"),
            rtsp_rw_timeout_us=_getenv_int("RTSP_RW_TIMEOUT_US", 10_000_000, minimum=1_000_000),
            ingest_retry_base_seconds=_getenv_int("INGEST_RETRY_BASE_SECONDS", 2, minimum=1),
            ingest_retry_max_seconds=_getenv_int("INGEST_RETRY_MAX_SECONDS", 30, minimum=1),
            ingest_recreate_ingress_on_retry=_getenv_bool("INGEST_RECREATE_INGRESS_ON_RETRY", True),
            ingest_ffmpeg_loglevel=os.getenv("INGEST_FFMPEG_LOGLEVEL", "warning"),
            ingest_publish_protocol=os.getenv("INGEST_PUBLISH_PROTOCOL", "auto").strip().lower(),
            ingest_publish_host_override=os.getenv("INGEST_PUBLISH_HOST_OVERRIDE", "").strip(),
            ingest_probe_size_bytes=_getenv_int("INGEST_PROBE_SIZE_BYTES", 1_000_000, minimum=32),
            ingest_analyze_duration_us=_getenv_int("INGEST_ANALYZE_DURATION_US", 1_000_000, minimum=0),
            ingest_reorder_queue_size=_getenv_int("INGEST_REORDER_QUEUE_SIZE", 16, minimum=0),
            ingest_max_delay_us=_getenv_int("INGEST_MAX_DELAY_US", 500_000, minimum=0),
            ingest_transcode_bitrate=os.getenv("INGEST_TRANSCODE_BITRATE", "2500k"),
            ingest_transcode_bufsize=os.getenv("INGEST_TRANSCODE_BUFSIZE", "2500k"),
            ingest_transcode_gop=_getenv_int("INGEST_TRANSCODE_GOP", 30, minimum=10),
            ingest_transcode_preset=os.getenv("INGEST_TRANSCODE_PRESET", "ultrafast"),
            ingest_transcode_threads=_getenv_int("INGEST_TRANSCODE_THREADS", 1, minimum=1),
            ingest_enable_h264_passthrough=_getenv_bool("INGEST_ENABLE_H264_PASSTHROUGH", True),
        )
