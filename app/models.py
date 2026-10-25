from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = True
    temperature: float = 0.7
    system_prompt: str | None = None


class ChatResponse(BaseModel):
    status: str = "ok"
    content: str | None = None
    error: str | None = None
