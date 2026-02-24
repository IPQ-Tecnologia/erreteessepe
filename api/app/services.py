import requests
from requests.auth import HTTPBasicAuth
from fastapi import HTTPException
from .config import (
    MEDIAMTX_API,
    MEDIAMTX_API_USER,
    MEDIAMTX_API_PASS,
    WEBRTC_PORT,
    WEBRTC_USER,
    WEBRTC_PASS,
    PUBLIC_WEBRTC_HOST,
    MAX_VIEWERS,
    CAMERAS,
)
from .security import validate_user_access


API_AUTH = HTTPBasicAuth(WEBRTC_USER, WEBRTC_PASS)

def get_rtsp_source(device_name: str) -> str:
    rtsp = CAMERAS.get(device_name)
    if not rtsp:
        raise HTTPException(
            status_code=404,
            detail=f"Câmera '{device_name}' não cadastrada"
        )
    return rtsp


def path_exists(device_name: str) -> bool:
    print((MEDIAMTX_API_USER, MEDIAMTX_API_PASS))
    r = requests.get(
        f"{MEDIAMTX_API}/v3/paths/get/{device_name}",
        auth=(MEDIAMTX_API_USER, MEDIAMTX_API_PASS),
    )

    if r.status_code == 404:
        return False

    if r.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail="Erro ao consultar MediaMTX"
        )

    return True



def create_path(device_name: str, rtsp_source: str):
    payload = {
        "source": rtsp_source
    }
    print('create_path', f"{MEDIAMTX_API}/v3/config/paths/add/{device_name}")
    print('payload', payload)
    r = requests.post(
        f"{MEDIAMTX_API}/v3/config/paths/add/{device_name}",
        auth=(MEDIAMTX_API_USER, MEDIAMTX_API_PASS),
        json=payload
    )

    if r.status_code not in (200, 201, 409):
        raise HTTPException(status_code=500, detail=r.text)


def remove_path(device_name: str):
    """
    Remove path quando não há viewers
    """
    r = requests.post(
        f"{MEDIAMTX_API}/v3/config/paths/remove/{device_name}",
        auth=(MEDIAMTX_API_USER, MEDIAMTX_API_PASS)
    )

    if r.status_code not in (200, 404):
        raise HTTPException(status_code=500, detail=r.text)


def get_viewer_count(device_name: str) -> int:
    r = requests.get(
        f"{MEDIAMTX_API}/v3/paths/list",
        auth=(MEDIAMTX_API_USER, MEDIAMTX_API_PASS),
    )
    if r.status_code != 200:
        return 0

    data = r.json()
    for item in data.get("items", []):
        if item.get("name") == device_name:
            return len(item.get("readers", []))
    return 0


def cleanup_if_idle(device_name: str):
    viewers = get_viewer_count(device_name)
    if viewers == 0 and path_exists(device_name):
        remove_path(device_name)


def build_webrtc_payload(device_name: str) -> dict:
    return {
      # "url": f"http://{PUBLIC_WEBRTC_HOST}:{WEBRTC_PORT}/{device_name}/webrtc",
        "url": f"http://{PUBLIC_WEBRTC_HOST}:{WEBRTC_PORT}/{device_name}",
        "username": WEBRTC_USER,
        "password": WEBRTC_PASS,
    }
    # return {
    #         "url": (
    #             f"http://{WEBRTC_USER}:{WEBRTC_PASS}"
    #             f"@{PUBLIC_WEBRTC_HOST}:{WEBRTC_PORT}"
    #             f"/{device_name}/webrtc"
    #         )
    #     }


def prepare_stream(user_id: str, device_name: str) -> dict:
    if not validate_user_access(user_id, device_name):
        raise HTTPException(status_code=403, detail="Sem permissão")

    rtsp_source = get_rtsp_source(device_name)
    print('rtsp_source', rtsp_source)
    viewers = get_viewer_count(device_name)
    print('viewers', viewers)
    if viewers >= MAX_VIEWERS:
        raise HTTPException(
            status_code=429,
            detail="Limite de viewers atingido"
        )

    # 🔄 Recria path sob demanda (reload sem restart)
    if not path_exists(device_name):
        create_path(device_name, rtsp_source)

    return {
        "device": device_name,
        "viewers": viewers,
        "webrtc": build_webrtc_payload(device_name),
    }
