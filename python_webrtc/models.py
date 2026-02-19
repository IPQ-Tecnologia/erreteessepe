from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    rtsp_url: str


class OfferRequest(BaseModel):
    sdp: str
    type: str
    camera_id: str = Field(default="cam1")


class AnswerResponse(BaseModel):
    sdp: str
    type: str
