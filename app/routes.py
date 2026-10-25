import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from config import settings
from models import ChatRequest
from ollama_client import stream_chat

router = APIRouter()


@router.get("/api/health")
async def api_health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.OLLAMA_MODEL,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
    }


@router.get("/api/models")
async def api_models() -> dict[str, list[str]]:
    return {"models": [settings.OLLAMA_MODEL]}


@router.post("/api/chat")
async def api_chat(request: ChatRequest):
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages supplied")

    async def event_generator():
        try:
            async for text_piece in stream_chat(
                [message.model_dump() for message in request.messages],
                temperature=request.temperature,
                system_prompt=request.system_prompt,
            ):
                yield f"data: {json.dumps({'content': text_piece})}\n\n"
        except Exception as exc:  # pragma: no cover - surfaced to client
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
