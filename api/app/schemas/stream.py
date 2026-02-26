from pydantic import BaseModel


class WebRTCConfig(BaseModel):
    url: str
    username: str
    password: str


class StreamResponse(BaseModel):
    device: str
    viewers: int
    webrtc: WebRTCConfig
