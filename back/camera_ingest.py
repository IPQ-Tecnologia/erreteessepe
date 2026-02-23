import asyncio
import logging
import shlex
import signal
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from livekit import api

from .cameras import build_room_name, load_cameras
from .config import LOGGER_NAME, Settings, configure_logging
from .ingest_status import IngestStatusStore
from .models import Camera

logger = logging.getLogger(f"{LOGGER_NAME}.ingest")

try:
    from livekit.protocol.ingress import (
        CreateIngressRequest as ProtoCreateIngressRequest,
        DeleteIngressRequest as ProtoDeleteIngressRequest,
        IngressInput as ProtoIngressInput,
        ListIngressRequest as ProtoListIngressRequest,
    )
except Exception:  # pragma: no cover - fallback for environments with different package layout
    ProtoCreateIngressRequest = None
    ProtoDeleteIngressRequest = None
    ProtoIngressInput = None
    ProtoListIngressRequest = None


@dataclass(frozen=True)
class CameraPipeline:
    camera: Camera
    room_name: str
    ingress_name: str
    participant_identity: str
    ingest_protocol: str


def _resolve_ingress_input_enum(ingest_protocol: str) -> Any:
    enum_name = "WHIP_INPUT" if ingest_protocol == "whip" else "RTMP_INPUT"
    ingress_input = getattr(api, "IngressInput", None)
    if ingress_input is not None and hasattr(ingress_input, enum_name):
        return getattr(ingress_input, enum_name)

    if ProtoIngressInput is not None and hasattr(ProtoIngressInput, enum_name):
        return getattr(ProtoIngressInput, enum_name)

    fallback = getattr(api, f"IngressInput_{enum_name}", None)
    if fallback is not None:
        return fallback

    raise RuntimeError(f"Could not resolve {enum_name} enum in livekit-api package")


async def _ffmpeg_supports_whip() -> bool:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-muxers",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, _ = await process.communicate()
    if process.returncode != 0:
        return False

    output = stdout_bytes.decode("utf-8", errors="ignore").lower()
    return " whip" in output


def _extract_ingress_url(ingress_info: Any) -> str:
    base_url = str(getattr(ingress_info, "url", "") or getattr(ingress_info, "whip_url", ""))
    stream_key = str(getattr(ingress_info, "stream_key", ""))

    if not base_url:
        return ""

    if stream_key and stream_key not in base_url:
        if base_url.endswith("/"):
            return f"{base_url}{stream_key}"
        return f"{base_url}/{stream_key}"

    return base_url


def _rewrite_publish_url_host(publish_url: str, host_override: str) -> str:
    if not publish_url:
        return publish_url

    target_host = host_override.strip()
    if not target_host:
        return publish_url

    try:
        parsed = urlsplit(publish_url)
    except ValueError:
        return publish_url

    if not parsed.scheme or not parsed.netloc:
        return publish_url

    userinfo = ""
    hostport = parsed.netloc
    if "@" in hostport:
        userinfo, hostport = hostport.rsplit("@", 1)

    port = ""
    if hostport.startswith("["):
        end = hostport.find("]")
        if end != -1:
            suffix = hostport[end + 1 :]
            if suffix.startswith(":"):
                port = suffix[1:]
    elif ":" in hostport:
        _, port = hostport.rsplit(":", 1)

    new_hostport = f"{target_host}:{port}" if port else target_host
    new_netloc = f"{userinfo}@{new_hostport}" if userinfo else new_hostport
    return urlunsplit((parsed.scheme, new_netloc, parsed.path, parsed.query, parsed.fragment))


async def _ensure_ingress(
    livekit_api: api.LiveKitAPI,
    pipeline: CameraPipeline,
    recreate_existing: bool = False,
) -> Any:
    list_request_cls = getattr(api, "ListIngressRequest", None) or ProtoListIngressRequest
    create_request_cls = getattr(api, "CreateIngressRequest", None) or ProtoCreateIngressRequest
    delete_request_cls = getattr(api, "DeleteIngressRequest", None) or ProtoDeleteIngressRequest

    if list_request_cls is None or create_request_cls is None:
        raise RuntimeError("Could not resolve ingress request classes in livekit-api package")

    list_request = list_request_cls(room_name=pipeline.room_name)
    listed = await livekit_api.ingress.list_ingress(list_request)
    items = list(getattr(listed, "items", []) or [])

    existing = None
    for ingress in items:
        ingress_name = str(getattr(ingress, "name", ""))
        if ingress_name == pipeline.ingress_name:
            existing = ingress
            break

    if existing is not None and recreate_existing:
        ingress_id = str(getattr(existing, "ingress_id", ""))
        if not ingress_id:
            logger.warning(
                "Ingress '%s' for room '%s' has no ingress_id; reusing existing ingress",
                pipeline.ingress_name,
                pipeline.room_name,
            )
            return existing

        if delete_request_cls is None:
            logger.warning(
                "Could not resolve DeleteIngressRequest class; reusing existing ingress '%s'",
                ingress_id,
            )
            return existing

        try:
            await livekit_api.ingress.delete_ingress(delete_request_cls(ingress_id=ingress_id))
            logger.info(
                "Deleted existing ingress '%s' for room '%s' before recreate",
                ingress_id,
                pipeline.room_name,
            )
        except api.TwirpError as exc:
            if getattr(exc, "code", None) != api.TwirpErrorCode.NOT_FOUND:
                raise
        existing = None

    if existing is not None:
        return existing

    create_request = create_request_cls(
        input_type=_resolve_ingress_input_enum(pipeline.ingest_protocol),
        name=pipeline.ingress_name,
        room_name=pipeline.room_name,
        participant_identity=pipeline.participant_identity,
        participant_name=pipeline.camera.name,
        enable_transcoding=(pipeline.ingest_protocol == "rtmp"),
    )
    return await livekit_api.ingress.create_ingress(create_request)


async def _evict_stale_ingress_participant(
    livekit_api: api.LiveKitAPI,
    room_name: str,
    participant_identity: str,
) -> None:
    request = api.RoomParticipantIdentity(room=room_name, identity=participant_identity)
    try:
        await livekit_api.room.remove_participant(request)
        logger.info(
            "Removed stale participant identity='%s' from room='%s' before ingest reconnect",
            participant_identity,
            room_name,
        )
    except api.TwirpError as exc:
        if getattr(exc, "code", None) == api.TwirpErrorCode.NOT_FOUND:
            return
        logger.warning(
            "Failed to remove stale participant identity='%s' room='%s': %s",
            participant_identity,
            room_name,
            exc,
        )
    except Exception as exc:
        logger.warning(
            "Unexpected error removing stale participant identity='%s' room='%s': %s",
            participant_identity,
            room_name,
            exc,
        )


async def _probe_source_codec(camera: Camera, settings: Settings) -> str:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-probesize",
        str(settings.ingest_probe_size_bytes),
        "-analyzeduration",
        str(settings.ingest_analyze_duration_us),
        "-rtsp_transport",
        settings.rtsp_transport,
    ]
    if settings.ingest_max_delay_us > 0:
        command.extend(["-max_delay", str(settings.ingest_max_delay_us)])
    if settings.ingest_reorder_queue_size > 0:
        command.extend(["-reorder_queue_size", str(settings.ingest_reorder_queue_size)])

    command.extend(
        [
            # RTSP demuxer socket timeout (microseconds).
            "-timeout",
            str(settings.rtsp_rw_timeout_us),
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            camera.rtsp_url,
        ]
    )

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()

    if process.returncode != 0:
        stderr = stderr_bytes.decode("utf-8", errors="ignore").strip()
        logger.warning("ffprobe failed for camera '%s': %s", camera.id, stderr)
        return "unknown"

    codec = stdout_bytes.decode("utf-8", errors="ignore").strip().lower()
    return codec or "unknown"


def _build_ffmpeg_command(
    camera: Camera,
    ingress_url: str,
    settings: Settings,
    mode: str,
    ingest_protocol: str,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        settings.ingest_ffmpeg_loglevel,
        # Generate timestamps when RTSP sources provide broken/non-monotonic PTS.
        "-fflags",
        "+genpts",
        "-probesize",
        str(settings.ingest_probe_size_bytes),
        "-analyzeduration",
        str(settings.ingest_analyze_duration_us),
        "-rtsp_transport",
        settings.rtsp_transport,
    ]
    if settings.ingest_max_delay_us > 0:
        command.extend(["-max_delay", str(settings.ingest_max_delay_us)])
    if settings.ingest_reorder_queue_size > 0:
        command.extend(["-reorder_queue_size", str(settings.ingest_reorder_queue_size)])

    command.extend(
        [
            # RTSP demuxer socket timeout (microseconds).
            "-timeout",
            str(settings.rtsp_rw_timeout_us),
            "-use_wallclock_as_timestamps",
            "1",
            "-i",
            camera.rtsp_url,
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
        ]
    )

    if mode == "copy":
        command.extend(
            [
                "-c:v",
                "copy",
            ]
        )
    else:
        command.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                settings.ingest_transcode_preset,
                "-tune",
                "zerolatency",
                "-profile:v",
                "baseline",
                "-pix_fmt",
                "yuv420p",
                "-threads",
                str(settings.ingest_transcode_threads),
                "-x264-params",
                "rc-lookahead=0:sync-lookahead=0:scenecut=0:repeat-headers=1",
                "-g",
                str(settings.ingest_transcode_gop),
                "-keyint_min",
                str(settings.ingest_transcode_gop),
                "-sc_threshold",
                "0",
                "-bf",
                "0",
                "-b:v",
                settings.ingest_transcode_bitrate,
                "-maxrate",
                settings.ingest_transcode_bitrate,
                "-bufsize",
                settings.ingest_transcode_bufsize,
            ]
        )

    command.extend(["-flush_packets", "1"])

    if ingest_protocol == "whip":
        command.extend(["-f", "whip", ingress_url])
    else:
        command.extend(
            [
                "-flvflags",
                "no_duration_filesize",
                "-rtmp_live",
                "live",
                "-f",
                "flv",
                ingress_url,
            ]
        )

    return command


async def _log_ffmpeg_output(camera_id: str, stream: asyncio.StreamReader | None) -> None:
    if stream is None:
        return

    while True:
        line = await stream.readline()
        if not line:
            return

        text = line.decode("utf-8", errors="ignore").strip()
        if text:
            logger.info("[%s ffmpeg] %s", camera_id, text)


async def _run_camera_loop(
    livekit_api: api.LiveKitAPI,
    settings: Settings,
    pipeline: CameraPipeline,
    status_store: IngestStatusStore,
    stop_event: asyncio.Event,
) -> None:
    backoff_seconds = settings.ingest_retry_base_seconds
    recreate_ingress_next_attempt = False

    while not stop_event.is_set():
        ffmpeg_process: asyncio.subprocess.Process | None = None
        ffmpeg_logs_task: asyncio.Task[None] | None = None
        wait_task: asyncio.Task[int] | None = None
        stop_wait_task: asyncio.Task[bool] | None = None

        try:
            await status_store.update_camera(
                pipeline.camera.id,
                room_name=pipeline.room_name,
                state="starting",
                online=False,
                message="creating or reusing ingress",
            )

            ingress_info = await _ensure_ingress(
                livekit_api,
                pipeline,
                recreate_existing=recreate_ingress_next_attempt,
            )
            recreate_ingress_next_attempt = False
            ingress_id = str(getattr(ingress_info, "ingress_id", ""))
            ingress_url = _extract_ingress_url(ingress_info)
            rewritten_ingress_url = _rewrite_publish_url_host(
                ingress_url,
                settings.ingest_publish_host_override,
            )
            if rewritten_ingress_url != ingress_url:
                logger.info(
                    "Rewriting ingress publish URL host for camera '%s': %s -> %s",
                    pipeline.camera.id,
                    ingress_url,
                    rewritten_ingress_url,
                )
                ingress_url = rewritten_ingress_url

            if not ingress_url:
                raise RuntimeError("Ingress did not expose publish URL")

            await _evict_stale_ingress_participant(
                livekit_api=livekit_api,
                room_name=pipeline.room_name,
                participant_identity=pipeline.participant_identity,
            )

            codec = await _probe_source_codec(pipeline.camera, settings)
            mode = "copy" if settings.ingest_enable_h264_passthrough and codec == "h264" else "transcode"

            ffmpeg_command = _build_ffmpeg_command(
                camera=pipeline.camera,
                ingress_url=ingress_url,
                settings=settings,
                mode=mode,
                ingest_protocol=pipeline.ingest_protocol,
            )

            logger.info(
                "Starting camera '%s' room='%s' mode=%s protocol=%s ingress='%s' cmd=%s",
                pipeline.camera.id,
                pipeline.room_name,
                mode,
                pipeline.ingest_protocol,
                ingress_id,
                shlex.join(ffmpeg_command),
            )

            await status_store.update_camera(
                pipeline.camera.id,
                room_name=pipeline.room_name,
                ingress_id=ingress_id,
                publish_url=ingress_url,
                publish_protocol=pipeline.ingest_protocol,
                codec=codec,
                mode=mode,
                state="starting",
                online=False,
                message="starting ffmpeg",
                last_error=None,
            )

            ffmpeg_process = await asyncio.create_subprocess_exec(
                *ffmpeg_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            ffmpeg_logs_task = asyncio.create_task(_log_ffmpeg_output(pipeline.camera.id, ffmpeg_process.stdout))

            await status_store.update_camera(
                pipeline.camera.id,
                room_name=pipeline.room_name,
                ingress_id=ingress_id,
                publish_url=ingress_url,
                publish_protocol=pipeline.ingest_protocol,
                codec=codec,
                mode=mode,
                state="online",
                online=True,
                message="streaming",
                last_error=None,
            )

            wait_task = asyncio.create_task(ffmpeg_process.wait())
            stop_wait_task = asyncio.create_task(stop_event.wait())

            done, pending = await asyncio.wait(
                {wait_task, stop_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for pending_task in pending:
                pending_task.cancel()

            if stop_wait_task in done and not wait_task.done():
                logger.info("Stopping FFmpeg for camera '%s'", pipeline.camera.id)
                ffmpeg_process.terminate()
                try:
                    await asyncio.wait_for(wait_task, timeout=5)
                except asyncio.TimeoutError:
                    ffmpeg_process.kill()
                    await wait_task

            return_code = wait_task.result() if wait_task.done() else await wait_task

            if stop_event.is_set():
                await status_store.update_camera(
                    pipeline.camera.id,
                    room_name=pipeline.room_name,
                    state="offline",
                    online=False,
                    message="stopped",
                )
                break

            error_message = f"ffmpeg exited with code {return_code}"
            logger.warning("Camera '%s' loop ended: %s", pipeline.camera.id, error_message)
            if (
                settings.ingest_recreate_ingress_on_retry
                and return_code in {152, 224}
            ):
                recreate_ingress_next_attempt = True
                logger.warning(
                    "Camera '%s' will recreate ingress on next retry due to exit code %s",
                    pipeline.camera.id,
                    return_code,
                )
            await status_store.update_camera(
                pipeline.camera.id,
                room_name=pipeline.room_name,
                state="error",
                online=False,
                message=error_message,
                last_error=error_message,
            )

        except Exception as exc:
            logger.exception("Camera '%s' ingest error", pipeline.camera.id)
            await status_store.update_camera(
                pipeline.camera.id,
                room_name=pipeline.room_name,
                state="error",
                online=False,
                message="camera ingest failed",
                last_error=str(exc),
            )

        finally:
            if ffmpeg_logs_task is not None:
                ffmpeg_logs_task.cancel()
                try:
                    await ffmpeg_logs_task
                except asyncio.CancelledError:
                    pass

            if wait_task is not None and not wait_task.done():
                wait_task.cancel()

            if stop_wait_task is not None and not stop_wait_task.done():
                stop_wait_task.cancel()

        if stop_event.is_set():
            break

        await status_store.update_camera(
            pipeline.camera.id,
            room_name=pipeline.room_name,
            state="restarting",
            online=False,
            message=f"retrying in {backoff_seconds}s",
        )
        await asyncio.sleep(backoff_seconds)
        backoff_seconds = min(backoff_seconds * 2, settings.ingest_retry_max_seconds)


async def run_ingest_service() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    cameras = load_cameras()
    if not cameras:
        raise RuntimeError("No cameras configured for ingest")

    status_store = IngestStatusStore(settings.ingest_status_path)
    await status_store.set_all_offline(list(cameras.keys()))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, _stop)
        except NotImplementedError:
            pass

    ingest_protocol = settings.ingest_publish_protocol
    if ingest_protocol not in {"auto", "whip", "rtmp"}:
        logger.warning(
            "Invalid INGEST_PUBLISH_PROTOCOL=%r, using auto detection",
            settings.ingest_publish_protocol,
        )
        ingest_protocol = "auto"

    if ingest_protocol == "auto":
        ingest_protocol = "whip" if await _ffmpeg_supports_whip() else "rtmp"

    logger.info("Starting camera ingest for %d camera(s)", len(cameras))
    logger.info("Selected publish protocol: %s", ingest_protocol)
    identity_prefix = settings.ingest_participant_identity_prefix or "ingress"
    identity_prefix = identity_prefix.strip("-")
    if not identity_prefix:
        identity_prefix = "ingress"
    instance_tag = settings.ingest_instance_tag.strip("-")

    pipelines = [
        CameraPipeline(
            camera=camera,
            room_name=build_room_name(camera.id, settings.camera_room_prefix),
            ingress_name=(
                f"{build_room_name(camera.id, settings.camera_room_prefix)}-ingress-{ingest_protocol}-{instance_tag}"
                if instance_tag
                else f"{build_room_name(camera.id, settings.camera_room_prefix)}-ingress-{ingest_protocol}"
            ),
            participant_identity=f"{identity_prefix}-{camera.id}",
            ingest_protocol=ingest_protocol,
        )
        for camera in cameras.values()
    ]

    async with api.LiveKitAPI(
        url=settings.livekit_api_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    ) as livekit_api:
        tasks = [
            asyncio.create_task(
                _run_camera_loop(
                    livekit_api=livekit_api,
                    settings=settings,
                    pipeline=pipeline,
                    status_store=status_store,
                    stop_event=stop_event,
                )
            )
            for pipeline in pipelines
        ]

        await stop_event.wait()

        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Camera ingest service stopped")


def main() -> None:
    asyncio.run(run_ingest_service())


if __name__ == "__main__":
    main()
