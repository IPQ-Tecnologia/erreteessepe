from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    rtsp_url: str


class CameraView(BaseModel):
    id: str
    name: str
    room_name: str
    online: bool
    state: str
    message: str | None = None


class ViewerSessionResponse(BaseModel):
    camera_id: str
    camera_name: str
    room_name: str
    livekit_url: str
    token: str
    identity: str
