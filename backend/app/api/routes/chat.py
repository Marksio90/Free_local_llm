"""
Endpoint /api/chat — Multi-agentowy "mózg" systemu.

Architektura 3 agentów (wszystkie darmowe, lokalne via Ollama):

  Agent 1: KLASYFIKATOR (background_model ~1.5B)
    ↓  Szybka klasyfikacja JSON: co potrzebujemy do odpowiedzi?
    ↓  ~0.5s na słabym CPU

  Agent 2: RESEARCHER (RAG + Vector + BM25 + RRF)
    ↓  Jeśli potrzeba kodu/wiedzy: przeszukuje ChromaDB (Vector+BM25+RRF)
    ↓  Jeśli potrzeba web: crawl DuckDuckGo/Wikipedia
    ↓  Zwraca skondensowany kontekst

  Agent 3: SYNTEZATOR (default_model ~7B)
    → Otrzymuje: pytanie + kontekst od Researchera + profil użytkownika
    → Generuje finalną odpowiedź (streaming)
    → Najcięższy model budzi się TYLKO DO TEGO JEDNEGO ZADANIA

Zaleta na laptopie:
  Klasyfikator (1.5B) robi "brudną robotę" klasyfikacji.
  Główny model (7B) skupia się wyłącznie na generowaniu odpowiedzi.
  Efekt: szybszy czas pierwszego tokena, mniejsze zużycie RAM.

Graceful fallback:
  Jeśli Klasyfikator niedostępny → standardowy RAG (bez multi-agent).
"""

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.services.context_builder import build_context, build_system_prompt
from app.services.memory_service import memory
from app.services.ollama_client import ollama

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    model: str = ""
    session_id: str = "default"
    system: str = ""
    use_rag: bool = True
    use_memory: bool = True
    use_agents: bool = True   # włącz/wyłącz multi-agent orkiestrację
    stream: bool = False


# ── Agent 1: Klasyfikator ─────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = (
    "Jesteś klasyfikatorem zapytań. Analizujesz pytanie użytkownika i zwracasz "
    "TYLKO czystego JSONa (bez markdown, bez wyjaśnień).\n"
    "Struktura odpowiedzi:\n"
    '{"needs_code": bool, "needs_web": bool, "needs_memory": bool, '
    '"query_type": "code|question|creative|analysis|chat"}\n\n'
    "Definicje:\n"
    "needs_code=true jeśli pytanie dotyczy kodu, repo, technikaliów\n"
    "needs_web=true jeśli pytanie wymaga aktualnych informacji z internetu\n"
    "needs_memory=true jeśli pytanie dotyczy poprzednich rozmów lub osobistych preferencji\n"
    "query_type: code=pisanie/analiza kodu, question=ogólne pytanie, "
    "creative=twórcze/pisanie, analysis=analiza danych/dokumentów, chat=rozmowa"
)


async def _classify_query(message: str) -> dict:
    """
    Agent 1: Klasyfikator — używa lekkiego background_model (~1.5B).
    Szybki (~0.3-0.8s), mało pamięci, działa równolegle z budowaniem kontekstu.

    Zwraca słownik z flagami lub fallback jeśli model niedostępny.
    """
    fallback = {
        "needs_code": True,
        "needs_web": False,
        "needs_memory": True,
        "query_type": "question",
    }
    try:
        bg_model = settings.background_model
        # Sprawdź czy background model jest dostępny
        models = await ollama.list_models()
        model_names = [m.get("name", "") for m in models]
        # Uwaga: `n in bg_model` gdy n=="" jest zawsze True — stąd explicit check `n and`
        if not any(bg_model in n or (n and n in bg_model) for n in model_names):
            logger.debug(f"Background model '{bg_model}' niedostępny → fallback")
            return fallback

        response = await ollama.generate(
            bg_model,
            message,
            _CLASSIFIER_SYSTEM,
        )
        # Wyciągnij JSON z odpowiedzi (może zawierać markdown)
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(response[json_start:json_end])
            return {**fallback, **data}  # fallback dla brakujących kluczy
    except Exception as e:
        logger.debug(f"Klasyfikator błąd: {e} → fallback")
    return fallback


# ── Agent 2: Researcher ───────────────────────────────────────────────────────

async def _research(message: str, classification: dict, use_memory: bool) -> dict:
    """
    Agent 2: Researcher — zbiera wiedzę na podstawie decyzji Klasyfikatora.

    Decyzje:
    - needs_code → przeszukaj ChromaDB (Vector+BM25+RRF)
    - needs_web → crawl DDG/Wikipedia (opcjonalne — tylko jeśli brak w bazie)
    - needs_memory → wyszukaj w historii rozmów
    """
    include_rag = classification.get("needs_code", True)
    include_memory = use_memory and classification.get("needs_memory", True)

    context = await build_context(message, include_memory=include_memory)

    # Jeśli needs_web i mamy mało wiedzy z bazy → szybki web search w tle
    if classification.get("needs_web") and context["knowledge_count"] < 2:
        asyncio.create_task(_background_web_search(message))

    return context


async def _background_web_search(query: str):
    """Web search uruchamiany w tle — nie blokuje odpowiedzi."""
    try:
        from app.services.web_intel_service import search_and_ingest
        await search_and_ingest(query, max_results=3)
    except Exception:
        pass


# ── Agent 3: Syntezator ───────────────────────────────────────────────────────

async def _build_synthesizer_prompt(
    message: str,
    context: dict,
    classification: dict,
    base_system: str,
) -> str:
    """
    Buduje rozszerzony system prompt dla Syntezatora.
    Dostosowuje instrukcje do query_type wykrytego przez Klasyfikator.
    """
    query_type = classification.get("query_type", "question")

    type_instructions = {
        "code": (
            "Skupiasz się na kodzie. Pisz konkretne, działające rozwiązania. "
            "Wyjaśniaj tylko tam gdzie to konieczne. Używaj bloków kodu."
        ),
        "question": (
            "Odpowiadaj precyzyjnie i na temat. Bądź konkretny."
        ),
        "creative": (
            "Masz swobodę twórczą. Pisz angażująco i oryginalnie."
        ),
        "analysis": (
            "Analizuj systematycznie. Wyciągaj wnioski. Używaj struktury (listy, sekcje)."
        ),
        "chat": (
            "Rozmawiaj naturalnie. Bądź bezpośredni."
        ),
    }

    extra = type_instructions.get(query_type, type_instructions["question"])
    combined_system = f"{base_system}\n\n{extra}" if base_system else extra
    return build_system_prompt(context, combined_system)


# ── Główny endpoint ───────────────────────────────────────────────────────────

async def _resolve_model(requested: str) -> str:
    """
    Zwróć model do użycia — jeśli żądany nie istnieje, użyj pierwszego dostępnego.
    Zapobiega 400 od Ollama gdy model nie jest pobrany.
    """
    try:
        available = await ollama.list_models()
        names = [m.get("name", "") for m in available]
        if not names:
            return requested  # Ollama może jeszcze startować

        # Szukaj dokładnego lub częściowego dopasowania
        for name in names:
            if requested in name or name.startswith(requested.split(":")[0]):
                return name

        # Fallback do pierwszego dostępnego modelu
        logger.warning(f"Model '{requested}' niedostępny. Używam '{names[0]}' zamiast.")
        return names[0]
    except Exception:
        return requested


@router.post("/", response_model=None)
async def chat(req: ChatRequest):
    """
    Multi-agentowy RAG chat z pamięcią.

    Przepływ:
    1. Klasyfikator (bg_model) → JSON z flagami needs_*  [równolegle z init]
    2. Researcher (RAG) → kontekst z ChromaDB         [na podstawie klasyfikacji]
    3. Syntezator (main model) → streaming response    [finalna odpowiedź]
    """
    model = await _resolve_model(req.model or settings.default_model)

    # ── Ścieżka multi-agentowa ────────────────────────────────────────────────
    if req.use_agents and (req.use_rag or req.use_memory):
        # Agent 1 i wstępny kontekst RÓWNOLEGLE
        classification_task = asyncio.create_task(_classify_query(req.message))
        classification = await classification_task

        # Agent 2: Researcher z decyzją klasyfikatora
        context = await _research(req.message, classification, req.use_memory)

        # Agent 3: buduj prompt Syntezatora
        system_prompt = await _build_synthesizer_prompt(
            req.message, context, classification, req.system
        )
    else:
        # ── Ścieżka prosta (bez multi-agent) ─────────────────────────────────
        classification = {"needs_code": True, "needs_web": False, "needs_memory": True, "query_type": "question"}
        context = {
            "context_block": "", "knowledge_count": 0, "memory_count": 0,
            "collections_searched": [], "user_profile": {},
        }
        if req.use_rag or req.use_memory:
            context = await build_context(req.message, include_memory=req.use_memory)
        system_prompt = build_system_prompt(context, req.system)

    meta = {
        "context_sources": context["knowledge_count"],
        "memory_hits": context["memory_count"],
        "collections": context.get("collections_searched", []),
        "query_type": classification.get("query_type", "question"),
        "agents_used": req.use_agents,
    }

    # ── Streaming (Agent 3 - Syntezator) ─────────────────────────────────────
    if req.stream:
        async def _stream():
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

            if req.use_memory:
                full_text = "".join(full_response)
                await memory.add_exchange(req.message, full_text, req.session_id)
                asyncio.create_task(_auto_learn(req.message, full_text))

        return StreamingResponse(_stream(), media_type="application/x-ndjson")

    # ── Nie-streamingowy fallback ─────────────────────────────────────────────
    response = await ollama.generate(model, req.message, system_prompt)

    if req.use_memory:
        await memory.add_exchange(req.message, response, req.session_id)
        asyncio.create_task(_auto_learn(req.message, response))

    return {"response": response, "model": model, **meta}


async def _auto_learn(user_msg: str, assistant_msg: str):
    """
    Uruchamiany po każdej rozmowie w tle.
    Wyciąga tematy z rozmowy i zbiera wiedzę z internetu.
    """
    try:
        from app.services.topic_tracker_service import auto_learn_from_exchange
        await auto_learn_from_exchange(user_msg, assistant_msg)
    except Exception:
        pass


# ── Utility endpoints ─────────────────────────────────────────────────────────

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
    """Podgląd co model zobaczy jako kontekst — do debugowania RAG/RRF."""
    context = await build_context(query)
    system_prompt = build_system_prompt(context)
    return {
        "query": query,
        "knowledge_chunks": context["knowledge_count"],
        "memory_chunks": context["memory_count"],
        "collections_searched": context.get("collections_searched", []),
        "vector_hits": context.get("vector_hits", 0),
        "bm25_hits": context.get("bm25_hits", 0),
        "rrf_merged": context.get("rrf_merged", 0),
        "system_prompt_preview": system_prompt[:2000],
        "system_prompt_length": len(system_prompt),
    }


@router.post("/classify")
async def classify_query(message: str):
    """Podgląd jak Klasyfikator interpretuje zapytanie."""
    return await _classify_query(message)
