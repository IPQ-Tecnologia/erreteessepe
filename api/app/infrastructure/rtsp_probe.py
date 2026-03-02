from __future__ import annotations

import shutil
import subprocess
from urllib.parse import urlsplit

from app.core.http_errors import http_error


class RTSPProbe:
    def __init__(self, timeout_seconds: float = 5.0, ffprobe_bin: str = "ffprobe") -> None:
        self._timeout_seconds = timeout_seconds
        self._ffprobe_bin = ffprobe_bin

    def ensure_source_available(self, rtsp_source: str) -> None:
        parsed = urlsplit(rtsp_source)
        if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
            raise http_error(
                status_code=502,
                code="camera_url_invalid",
                message="A URL RTSP configurada para a camera esta invalida.",
            )

        if not shutil.which(self._ffprobe_bin):
            return

        command = [
            self._ffprobe_bin,
            "-v",
            "error",
            "-timeout",
            str(int(self._timeout_seconds * 1_000_000)),
            "-rtsp_transport",
            "tcp",
            "-show_streams",
            "-of",
            "json",
            rtsp_source,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds + 1,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise http_error(
                status_code=503,
                code="camera_offline",
                message="A camera esta offline ou nao respondeu na rede.",
            ) from exc
        except OSError:
            return

        if result.returncode == 0:
            return

        stderr = (result.stderr or "").strip()
        raise self._map_error(stderr)

    @staticmethod
    def _map_error(stderr: str):
        error_text = stderr.lower()

        if any(
            token in error_text
            for token in (
                "401 unauthorized",
                "403 forbidden",
                "authorization failed",
            )
        ):
            return http_error(
                status_code=502,
                code="camera_auth_failed",
                message="Nao foi possivel autenticar na camera. Verifique as credenciais da URL RTSP.",
            )

        if any(
            token in error_text
            for token in (
                "404 not found",
                "454 session not found",
                "invalid data found when processing input",
                "method describe failed",
                "method options failed: 404",
                "server returned 400",
            )
        ):
            return http_error(
                status_code=502,
                code="camera_url_invalid",
                message="A URL RTSP configurada para a camera nao existe ou esta incorreta.",
            )

        if any(
            token in error_text
            for token in (
                "connection timed out",
                "connection refused",
                "no route to host",
                "network is unreachable",
                "host is unreachable",
            )
        ):
            return http_error(
                status_code=503,
                code="camera_offline",
                message="A camera esta offline ou inacessivel na rede.",
            )

        if any(
            token in error_text
            for token in (
                "failed to resolve hostname",
                "name or service not known",
                "nodename nor servname provided",
                "temporary failure in name resolution",
            )
        ):
            return http_error(
                status_code=502,
                code="camera_url_invalid",
                message="O host configurado na URL RTSP da camera nao existe.",
            )

        return http_error(
            status_code=502,
            code="camera_stream_unavailable",
            message="Nao foi possivel abrir a fonte RTSP da camera.",
        )
