import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from config import settings
from models import ChatRequest
from ollama_client import stream_chat
from storage import SessionNotFoundError, get_session, prepare_chat, save_assistant_message

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.get("/api/sessions/{session_id}")
async def api_get_session(session_id: UUID):
    session = await run_in_threadpool(get_session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/api/chat")
async def api_chat(request: ChatRequest):
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        session_id, messages = await run_in_threadpool(
            prepare_chat,
            request.session_id,
            user_message,
            settings.OLLAMA_MODEL,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except Exception as exc:
        logger.exception("Failed to prepare chat session")
        raise HTTPException(status_code=503, detail="Chat storage is unavailable") from exc

    async def event_generator():
        response_parts: list[str] = []
        yield f"data: {json.dumps({'session_id': str(session_id)})}\n\n"
        try:
            async for text_piece in stream_chat(
                messages,
                temperature=request.temperature,
                system_prompt=request.system_prompt,
            ):
                response_parts.append(text_piece)
                yield f"data: {json.dumps({'content': text_piece})}\n\n"
        except Exception as exc:  # pragma: no cover - surfaced to client
            logger.exception("Ollama chat stream failed")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        else:
            if response_parts:
                try:
                    await run_in_threadpool(
                        save_assistant_message,
                        session_id,
                        "".join(response_parts),
                        settings.OLLAMA_MODEL,
                    )
                except Exception:
                    logger.exception("Failed to persist assistant response")
                    yield f"data: {json.dumps({'error': 'The response could not be saved'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
