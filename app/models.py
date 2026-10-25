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
