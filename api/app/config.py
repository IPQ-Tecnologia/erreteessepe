import os

# MediaMTX (container)
MEDIAMTX_HOST = os.getenv("MEDIAMTX_HOST", "mediamtx")
MEDIAMTX_API = os.getenv("MEDIAMTX_API", "http://mediamtx:9997")

RTSP_PORT = int(os.getenv("RTSP_PORT", "8554"))
WEBRTC_PORT = int(os.getenv("WEBRTC_PORT", "8889"))

# Credenciais API MediaMTX (usuário backend)
MEDIAMTX_API_USER = os.getenv("MEDIAMTX_API_USER", "backend")
MEDIAMTX_API_PASS = os.getenv("MEDIAMTX_API_PASS", "backendpassword")

# Credenciais WebRTC (usuário viewer)
WEBRTC_USER = os.getenv("WEBRTC_USER", "viewer")
WEBRTC_PASS = os.getenv("WEBRTC_PASS", "strongpassword")

# Host público usado pelo frontend
PUBLIC_WEBRTC_HOST = os.getenv("PUBLIC_WEBRTC_HOST", "localhost")

# Regras de negócio
MAX_VIEWERS = int(os.getenv("MAX_VIEWERS", "5"))

# 📷 Dicionário de câmeras → RTSP
CAMERAS = {
    "camera01": "rtsp://admin:admin%40123@192.168.101.212:554/cam/realmonitor?channel=1&subtype=0",
    "camera02": "rtsp://admin:admin123@192.168.101.211:554/cam/realmonitor?channel=1&subtype=0",
    "camera03":  "rtsp://admin:admin%40123@192.168.101.210:554/cam/realmonitor?channel=1&subtype=0",
}
