import json
import logging
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from auth import (
    SESSION_COOKIE,
    UsernameTakenError,
    authenticate_user,
    change_password,
    clear_login_attempts,
    create_account,
    create_session,
    get_current_user,
    login_rate_limit_remaining,
    record_failed_login,
    revoke_session,
    set_session_cookie,
    update_display_name,
)
from config import settings
from intake import (
    MAX_FILE_COUNT,
    MAX_UPLOAD_SIZE,
    ScannerUnavailableError,
    delete_user_document,
    get_user_document,
    list_user_documents,
    store_documents,
)
from models import ChatRequest, LoginRequest, PasswordUpdate, ProfileUpdate, RegisterRequest
from ollama_client import stream_chat
from storage import SessionNotFoundError, get_session, prepare_chat, save_assistant_message

router = APIRouter()
logger = logging.getLogger(__name__)


def _public_user(user: dict) -> dict:
    return {"id": str(user["id"]), "username": user["username"], "display_name": user["display_name"], "role": user["role"]}


@router.post("/api/auth/register", status_code=201)
async def api_register(payload: RegisterRequest, response: Response):
    username = payload.username.lower()
    try:
        user = await run_in_threadpool(create_account, username, payload.password)
    except UsernameTakenError as exc:
        raise HTTPException(status_code=409, detail="That username is already in use") from exc
    token = await run_in_threadpool(create_session, user["id"])
    set_session_cookie(response, token)
    return _public_user(user)


@router.post("/api/auth/login")
async def api_login(payload: LoginRequest, request: Request, response: Response):
    client_host = request.client.host if request.client else "unknown"
    remaining = await run_in_threadpool(login_rate_limit_remaining, payload.username, client_host)
    if remaining is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(remaining)},
        )
    user = await run_in_threadpool(authenticate_user, payload.username.lower(), payload.password)
    if user is None:
        await run_in_threadpool(record_failed_login, payload.username, client_host)
        raise HTTPException(status_code=401, detail="Username or password is incorrect")
    await run_in_threadpool(clear_login_attempts, payload.username, client_host)
    token = await run_in_threadpool(create_session, user["id"])
    set_session_cookie(response, token)
    return _public_user(user)


@router.post("/api/auth/logout")
async def api_logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await run_in_threadpool(revoke_session, token)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"status": "ok"}


@router.get("/api/auth/me")
async def api_current_user(user: dict = Depends(get_current_user)):
    return _public_user(user)


@router.patch("/api/auth/profile")
async def api_update_profile(payload: ProfileUpdate, user: dict = Depends(get_current_user)):
    updated = await run_in_threadpool(update_display_name, user["id"], payload.display_name)
    return _public_user(updated)


@router.post("/api/auth/password")
async def api_change_password(payload: PasswordUpdate, request: Request, response: Response, user: dict = Depends(get_current_user)):
    new_token = await run_in_threadpool(
        change_password,
        user["id"],
        payload.current_password,
        payload.new_password,
    )
    set_session_cookie(response, new_token)
    return {"status": "ok"}


@router.post("/api/uploads")
async def api_upload_documents(files: list[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one file")
    if len(files) > MAX_FILE_COUNT:
        raise HTTPException(status_code=413, detail=f"Upload no more than {MAX_FILE_COUNT} files at a time")

    payloads = []
    total_size = 0
    for upload in files:
        content = await upload.read(MAX_UPLOAD_SIZE + 1)
        total_size += len(content)
        if len(content) > MAX_UPLOAD_SIZE or total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Total upload size exceeds 100 MB")
        payloads.append((upload.filename or "", content))

    try:
        return await run_in_threadpool(
            store_documents,
            payloads,
            user["id"],
            settings.UPLOAD_DIR,
            settings.CLAMAV_HOST,
            settings.CLAMAV_PORT,
            settings.FILE_ENCRYPTION_ENABLED,
            settings.FILE_ENCRYPTION_KEY,
        )
    except ScannerUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Virus scanning is unavailable; no files were saved") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to save uploaded documents")
        raise HTTPException(status_code=503, detail="Uploaded files could not be saved") from exc


@router.get("/api/files")
async def api_list_files(user: dict = Depends(get_current_user)):
    return await run_in_threadpool(list_user_documents, user["id"])


@router.get("/api/files/{document_id}")
async def api_view_file(document_id: UUID, user: dict = Depends(get_current_user)):
    try:
        document = await run_in_threadpool(
            get_user_document,
            user["id"],
            document_id,
            settings.UPLOAD_DIR,
            settings.FILE_ENCRYPTION_KEY,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="File could not be opened") from exc
    if document is None:
        raise HTTPException(status_code=404, detail="File not found")
    filename = quote(Path(document["filename"]).name, safe="")
    return Response(
        content=document["content"],
        media_type=document["mime_type"],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'",
        },
    )


@router.delete("/api/files/{document_id}")
async def api_delete_file(document_id: UUID, user: dict = Depends(get_current_user)):
    deleted = await run_in_threadpool(delete_user_document, user["id"], document_id, settings.UPLOAD_DIR)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "deleted"}


@router.get("/api/health")
async def api_health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.OLLAMA_MODEL,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
    }


@router.get("/api/models")
async def api_models(user: dict = Depends(get_current_user)) -> dict[str, list[str]]:
    return {"models": [settings.OLLAMA_MODEL]}


@router.get("/api/sessions/{session_id}")
async def api_get_session(session_id: UUID, user: dict = Depends(get_current_user)):
    session = await run_in_threadpool(get_session, user["id"], session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/api/chat")
async def api_chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        session_id, messages = await run_in_threadpool(
            prepare_chat,
            user["id"],
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
                        user["id"],
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
