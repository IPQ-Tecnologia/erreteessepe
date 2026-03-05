from pydantic import BaseModel, Field


class ICEServer(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None


class WebRTCConfig(BaseModel):
    url: str
    auth_type: str
    username: str | None = None
    password: str | None = None
    token: str | None = None
    ice_servers: list[ICEServer] = Field(default_factory=list)


class StreamResponse(BaseModel):
    device: str
    viewers: int
    webrtc: WebRTCConfig
