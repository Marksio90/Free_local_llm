from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.services.memory_service import memory

router = APIRouter()


class AddFactRequest(BaseModel):
    fact: str
    category: str = "general"


class SearchRequest(BaseModel):
    query: str
    n: int = 10


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    languages: Optional[list] = None
    style: Optional[str] = None
    bio: Optional[str] = None


@router.get("/stats")
async def memory_stats():
    """Statystyki pamięci."""
    return memory.stats()


@router.post("/search")
async def search_memory(req: SearchRequest):
    """Szukaj w pamięci."""
    results = await memory.search(req.query, req.n)
    return {"results": results, "total": len(results)}


@router.post("/facts")
async def add_fact(req: AddFactRequest):
    """Dodaj fakt o sobie ręcznie."""
    await memory.add_fact(req.fact, req.category)
    return {"added": req.fact}


@router.get("/profile")
async def get_profile():
    """Pobierz profil użytkownika."""
    return memory.get_profile()


@router.put("/profile")
async def update_profile(req: ProfileUpdateRequest):
    """Zaktualizuj profil użytkownika."""
    current = memory.get_profile()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    current.update(updates)
    memory.update_profile(current)
    return current


@router.get("/sessions/{session_id}")
async def session_history(session_id: str, limit: int = 30):
    """Historia rozmów dla sesji."""
    history = memory.get_session_history(session_id, limit)
    return {"session_id": session_id, "messages": history, "count": len(history)}
