import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from .config import LOGGER_NAME, Settings


logger = logging.getLogger(LOGGER_NAME)


async def check_tcp_reachability(rtsp_url: str, timeout_ms: int) -> bool:
    try:
        parsed = urlparse(rtsp_url)
        host = parsed.hostname
        port = parsed.port or 554
        if not host:
            return False

        conn = asyncio.open_connection(host, port)
        _reader, writer = await asyncio.wait_for(conn, timeout=timeout_ms / 1000)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def validate_camera_connection(rtsp_url: str, settings: Settings) -> dict[str, Any]:
    is_reachable = await check_tcp_reachability(rtsp_url, timeout_ms=settings.tcp_check_timeout_ms)
    logger.info("TCP reachability check for %s: %s", rtsp_url, "reachable" if is_reachable else "unreachable")
    if not is_reachable:
        return {"ok": False, "reason": "unreachable", "message": "Camera host is not reachable"}

    command = [
        "ffprobe",
        "-v",
        "error",
        "-rtsp_transport",
        settings.rtsp_transport,
        "-timeout",
        str(settings.probe_timeout_seconds * 1_000_000),
        "-i",
        rtsp_url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "reason": "stream_error",
            "message": "ffprobe not found in PATH",
        }
    except Exception as exc:
        return {"ok": False, "reason": "stream_error", "message": str(exc)}

    try:
        _, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=settings.probe_timeout_seconds + 2,
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        return {"ok": False, "reason": "unreachable", "message": "Connection timed out"}

    stderr = stderr_bytes.decode("utf-8", errors="ignore").strip()
    if process.returncode == 0:
        return {"ok": True}

    lower = stderr.lower()
    if "401" in lower or "unauthorized" in lower:
        return {"ok": False, "reason": "auth_failed", "message": "Invalid credentials"}

    unreachable_markers = [
        "connection refused",
        "network is unreachable",
        "no route to host",
        "connection timed out",
        "timeout",
    ]
    if any(marker in lower for marker in unreachable_markers):
        return {"ok": False, "reason": "unreachable", "message": "Camera is unreachable"}

    return {
        "ok": False,
        "reason": "stream_error",
        "message": stderr[:200] if stderr else "Unknown stream error",
    }
