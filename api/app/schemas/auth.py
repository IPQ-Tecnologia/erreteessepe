from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    username: str
    expires_at: int


class MeResponse(BaseModel):
    authenticated: bool
    username: str | None = None
    access_token: str | None = None

