from __future__ import annotations

from pydantic import BaseModel, Field
from uuid import UUID


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: UUID | None = None
    stream: bool = True
    temperature: float = 0.7
    system_prompt: str | None = None


class ChatResponse(BaseModel):
    status: str = "ok"
    content: str | None = None
    error: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    password: str = Field(..., min_length=12, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    password: str = Field(..., min_length=1, max_length=128)


class ProfileUpdate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)


class PasswordUpdate(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)
