from app.core.settings import settings
from app.domain.cameras import CAMERAS

MEDIAMTX_HOST = settings.mediamtx_host
MEDIAMTX_API = settings.mediamtx_api
RTSP_PORT = settings.rtsp_port
WEBRTC_PORT = settings.webrtc_port
MEDIAMTX_API_USER = settings.mediamtx_api_user
MEDIAMTX_API_PASS = settings.mediamtx_api_pass
WEBRTC_USER = settings.webrtc_user
WEBRTC_PASS = settings.webrtc_pass
PUBLIC_WEBRTC_HOST = settings.public_webrtc_host
MAX_VIEWERS = settings.max_viewers
MEDIAMTX_READY_TIMEOUT_SECONDS = settings.mediamtx_ready_timeout_seconds
IDLE_ROOM_CLEANUP_SECONDS = settings.idle_room_cleanup_seconds
MEDIAMTX_SOURCE_CLOSE_AFTER = settings.mediamtx_source_close_after
AUTH_PROVIDER = settings.auth_provider
KEYCLOAK_BASE_URL = settings.keycloak_base_url
KEYCLOAK_REALM = settings.keycloak_realm
KEYCLOAK_CLIENT_ID = settings.keycloak_client_id
KEYCLOAK_CLIENT_SECRET = settings.keycloak_client_secret
