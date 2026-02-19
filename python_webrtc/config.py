import logging
import os
from dataclasses import dataclass


LOGGER_NAME = "rtsp-webrtc"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure_logging(log_level: str) -> None:
    logging.basicConfig(level=log_level, format=LOG_FORMAT)


def _getenv_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError:
        logger = logging.getLogger(LOGGER_NAME)
        logger.warning("Invalid integer for %s=%r, falling back to %d", name, raw_value, default)
        return default


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
    tcp_check_timeout_ms: int
    probe_timeout_seconds: int
    rtsp_transport: str
    rtsp_timeout_us: int
    rtsp_max_delay_us: int
    rtsp_reorder_queue_size: int
    webrtc_relay_buffered: bool
    webrtc_video_max_bitrate_bps: int
    webrtc_video_start_bitrate_bps: int
    webrtc_video_min_bitrate_bps: int

    @classmethod
    def from_env(cls) -> "Settings":
        max_bitrate_bps = max(200_000, _getenv_int("WEBRTC_VIDEO_MAX_BITRATE_BPS", 2_500_000))
        start_bitrate_bps = max(200_000, _getenv_int("WEBRTC_VIDEO_START_BITRATE_BPS", 1_500_000))
        start_bitrate_bps = min(start_bitrate_bps, max_bitrate_bps)
        min_bitrate_bps = max(100_000, _getenv_int("WEBRTC_VIDEO_MIN_BITRATE_BPS", 500_000))
        min_bitrate_bps = min(min_bitrate_bps, start_bitrate_bps)

        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            cors_allow_origin=os.getenv("CORS_ALLOW_ORIGIN", "*"),
            tcp_check_timeout_ms=max(100, _getenv_int("TCP_CHECK_TIMEOUT_MS", 3000)),
            probe_timeout_seconds=max(1, _getenv_int("PROBE_TIMEOUT_SECONDS", 5)),
            rtsp_transport=os.getenv("RTSP_TRANSPORT", "tcp"),
            rtsp_timeout_us=max(100_000, _getenv_int("RTSP_TIMEOUT_US", 5_000_000)),
            rtsp_max_delay_us=max(0, _getenv_int("RTSP_MAX_DELAY_US", 100_000)),
            rtsp_reorder_queue_size=max(0, _getenv_int("RTSP_REORDER_QUEUE_SIZE", 0)),
            webrtc_relay_buffered=_getenv_bool("WEBRTC_RELAY_BUFFERED", False),
            webrtc_video_max_bitrate_bps=max_bitrate_bps,
            webrtc_video_start_bitrate_bps=start_bitrate_bps,
            webrtc_video_min_bitrate_bps=min_bitrate_bps,
        )
