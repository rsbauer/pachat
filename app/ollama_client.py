import json

import httpx

from config import settings


def _build_messages(messages: list[dict], system_prompt: str | None = None) -> list[dict]:
    payload: list[dict] = []

    if system_prompt:
        payload.append({"role": "system", "content": system_prompt})

    for message in messages:
        payload.append({"role": message["role"], "content": message["content"]})

    return payload


async def stream_chat(messages: list[dict], temperature: float = 0.7, system_prompt: str | None = None):
    base_url = settings.OLLAMA_BASE_URL.rstrip("/")
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": _build_messages(messages, system_prompt),
        "stream": True,
        "options": {"temperature": temperature},
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", f"{base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "error" in item:
                    raise RuntimeError(item["error"])

                if "message" in item and isinstance(item["message"], dict):
                    content = item["message"].get("content")
                    if content:
                        yield content
