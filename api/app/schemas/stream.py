from pydantic import BaseModel


class WebRTCConfig(BaseModel):
    url: str
    auth_type: str
    username: str | None = None
    password: str | None = None
    token: str | None = None


class StreamResponse(BaseModel):
    device: str
    viewers: int
    webrtc: WebRTCConfig
