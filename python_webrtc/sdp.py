from .config import Settings


def apply_video_bitrate_caps(answer_sdp: str, settings: Settings) -> str:
    lines = answer_sdp.splitlines()
    tuned_lines: list[str] = []
    in_video_section = False

    for line in lines:
        if line.startswith("m="):
            in_video_section = line.startswith("m=video ")
            tuned_lines.append(line)
            if in_video_section:
                tuned_lines.append(f"b=AS:{max(1, settings.webrtc_video_max_bitrate_bps // 1000)}")
                tuned_lines.append(f"b=TIAS:{settings.webrtc_video_max_bitrate_bps}")
            continue

        if in_video_section:
            if line.startswith("b=AS:") or line.startswith("b=TIAS:"):
                continue
            if line.startswith("a=fmtp:"):
                line = append_google_bitrate_hints(line, settings)

        tuned_lines.append(line)

    return "\r\n".join(tuned_lines) + "\r\n"


def append_google_bitrate_hints(fmtp_line: str, settings: Settings) -> str:
    if " " not in fmtp_line:
        return fmtp_line

    prefix, raw_params = fmtp_line.split(" ", 1)
    params = [param.strip() for param in raw_params.split(";") if param.strip()]

    if any(param.lower().startswith("apt=") for param in params):
        return fmtp_line

    existing_keys = {
        param.split("=", 1)[0].strip().lower()
        for param in params
        if "=" in param
    }
    additions = [
        ("x-google-min-bitrate", max(1, settings.webrtc_video_min_bitrate_bps // 1000)),
        ("x-google-start-bitrate", max(1, settings.webrtc_video_start_bitrate_bps // 1000)),
        ("x-google-max-bitrate", max(1, settings.webrtc_video_max_bitrate_bps // 1000)),
    ]
    for key, value in additions:
        if key not in existing_keys:
            params.append(f"{key}={value}")

    return f"{prefix} {';'.join(params)}"
