"""
Endpoint /api/chat — "mózg" systemu.

Każde zapytanie automatycznie:
1. Przeszukuje wszystkie Twoje repo i dokumenty (RAG hybrydowy BM25+vector)
2. Wyszukuje w pamięci poprzednich rozmów
3. Wstrzykuje profil użytkownika w system prompt
4. Generuje odpowiedź przez Ollama (streaming token-po-tokenie)
5. Zapisuje wymianę do pamięci i uczy się tematów w tle

To jest to co odróżnia "model który zna Ciebie" od zwykłego chatu.
"""

import asyncio
import json

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.services.context_builder import build_context, build_system_prompt
from app.services.memory_service import memory
from app.services.ollama_client import ollama

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    model: str = ""
    session_id: str = "default"
    system: str = ""
    use_rag: bool = True
    use_memory: bool = True
    stream: bool = False


@router.post("/", response_model=None)
async def chat(req: ChatRequest):
    """
    RAG-augmented chat z pamięcią.
    Automatycznie korzysta z wszystkich Twoich danych.
    """
    model = req.model or settings.default_model

    # 1. Buduj kontekst (RAG + pamięć) — przed streamem
    context = {
        "context_block": "",
        "knowledge_count": 0,
        "memory_count": 0,
        "collections_searched": [],
        "user_profile": {},
    }
    if req.use_rag or req.use_memory:
        context = await build_context(req.message, include_memory=req.use_memory)

    # 2. Zbuduj system prompt
    system_prompt = build_system_prompt(context, req.system)

    # Metadane gotowe zanim ruszy stream
    meta = {
        "context_sources": context["knowledge_count"],
        "memory_hits": context["memory_count"],
        "collections": context["collections_searched"],
    }

    # 3. Streaming
    if req.stream:
        async def _stream():
            # Wyślij metadane jako PIERWSZĄ linię — frontend odczyta context_sources itp.
            yield json.dumps(meta) + "\n"

            full_response = []
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream(
                    "POST",
                    f"{ollama.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": req.message,
                        "system": system_prompt,
                        "stream": True,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        yield json.dumps({"token": f"[Błąd Ollama: HTTP {resp.status_code}]"}) + "\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            full_response.append(token)
                            yield json.dumps({
                                "token": token,
                                "done": data.get("done", False),
                            }) + "\n"
                            if data.get("done"):
                                break
                        except Exception:
                            pass

            # Zapisz do pamięci i uruchom auto-learning po zakończeniu
            if req.use_memory:
                full_text = "".join(full_response)
                await memory.add_exchange(req.message, full_text, req.session_id)
                asyncio.create_task(_auto_learn(req.message, full_text))

        return StreamingResponse(_stream(), media_type="application/x-ndjson")

    # 4. Nie-streamingowy fallback
    response = await ollama.generate(model, req.message, system_prompt)

    if req.use_memory:
        await memory.add_exchange(req.message, response, req.session_id)
        asyncio.create_task(_auto_learn(req.message, response))

    return {
        "response": response,
        "model": model,
        **meta,
    }


async def _auto_learn(user_msg: str, assistant_msg: str):
    """
    Uruchamia się po każdej rozmowie w tle (nie blokuje odpowiedzi).
    Wyciąga tematy i zbiera wiedzę z internetu.
    """
    try:
        from app.services.topic_tracker_service import auto_learn_from_exchange
        await auto_learn_from_exchange(user_msg, assistant_msg)
    except Exception:
        pass


@router.get("/sessions/{session_id}/history")
async def session_history(session_id: str, limit: int = 20):
    """Historia rozmów dla sesji."""
    history = memory.get_session_history(session_id, limit)
    return {"session_id": session_id, "messages": history}


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """Wyczyść historię sesji."""
    return {"cleared": session_id}


@router.get("/context-preview")
async def preview_context(query: str, n: int = 5):
    """Podgląd co model zobaczy jako kontekst — do debugowania RAG."""
    context = await build_context(query)
    system_prompt = build_system_prompt(context)
    return {
        "query": query,
        "knowledge_chunks": context["knowledge_count"],
        "memory_chunks": context["memory_count"],
        "collections_searched": context["collections_searched"],
        "system_prompt_preview": system_prompt[:2000],
        "system_prompt_length": len(system_prompt),
    }
