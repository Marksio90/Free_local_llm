"""
Serwis pamięci personalnej.

Przechowuje i przeszukuje:
- historię rozmów (każda sesja)
- kluczowe fakty wyekstrahowane z rozmów
- preferencje użytkownika

Każda wiadomość → podsumowanie → wektor → ChromaDB kolekcja "user_memories"
Model z czasem "zna" Cię coraz lepiej.
"""

import hashlib
import json
from datetime import datetime
from typing import List

from app.core.config import settings
from app.services.rag_service import _parse_chroma_host_port
from app.services.ollama_client import ollama
import chromadb

MEMORY_COLLECTION = "user_memories"
PROFILE_COLLECTION = "user_profile"
MAX_MEMORIES = 10_000


def _chroma_client():
    host, port = _parse_chroma_host_port(settings.chroma_url)
    return chromadb.HttpClient(host=host, port=port)


class MemoryService:
    def _col(self, name: str):
        client = _chroma_client()
        return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})

    # ── Dodaj wymianę do pamięci ────────────────────────────────────────────
    async def add_exchange(self, user_msg: str, assistant_msg: str, session_id: str = "default"):
        """Zapisuje parę pytanie-odpowiedź jako wspomnienie."""
        col = self._col(MEMORY_COLLECTION)

        combined = f"Użytkownik: {user_msg}\nAsystent: {assistant_msg}"
        doc_id = hashlib.md5(f"{session_id}:{user_msg[:100]}".encode()).hexdigest()

        existing = col.get(ids=[doc_id])
        if existing["ids"]:
            return

        embedding = await ollama.embed(combined[:1000])
        col.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[combined],
            metadatas=[{
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "type": "exchange",
                "user_msg_preview": user_msg[:200],
            }],
        )

    # ── Dodaj fakt/preferencję wprost ────────────────────────────────────────
    async def add_fact(self, fact: str, category: str = "general"):
        """Zapisuje pojedynczy fakt o użytkowniku."""
        col = self._col(MEMORY_COLLECTION)
        doc_id = hashlib.md5(fact.encode()).hexdigest()

        existing = col.get(ids=[doc_id])
        if existing["ids"]:
            return

        embedding = await ollama.embed(fact)
        col.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[fact],
            metadatas=[{
                "type": "fact",
                "category": category,
                "timestamp": datetime.utcnow().isoformat(),
            }],
        )

    # ── Szukaj wspomnień pasujących do zapytania ─────────────────────────────
    async def search(self, query: str, n: int = 5) -> List[dict]:
        col = self._col(MEMORY_COLLECTION)
        if col.count() == 0:
            return []

        embedding = await ollama.embed(query)
        results = col.query(
            query_embeddings=[embedding],
            n_results=min(n, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "content": doc,
                "metadata": meta,
                "score": round(1 - dist, 4),
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    # ── Pobierz historię sesji ───────────────────────────────────────────────
    def get_session_history(self, session_id: str, limit: int = 20) -> List[dict]:
        col = self._col(MEMORY_COLLECTION)
        results = col.get(
            where={"session_id": session_id},
            limit=limit,
            include=["documents", "metadatas"],
        )
        if not results["ids"]:
            return []
        pairs = sorted(
            zip(results["documents"], results["metadatas"]),
            key=lambda x: x[1].get("timestamp", ""),
        )
        return [{"content": doc, "metadata": meta} for doc, meta in pairs]

    # ── Profil użytkownika ───────────────────────────────────────────────────
    def update_profile(self, profile: dict):
        """Zapisuje/aktualizuje profil użytkownika."""
        col = self._col(PROFILE_COLLECTION)
        profile_str = json.dumps(profile, ensure_ascii=False)
        col.upsert(
            ids=["user_profile_v1"],
            documents=[profile_str],
            metadatas=[{"updated": datetime.utcnow().isoformat()}],
        )

    def get_profile(self) -> dict:
        col = self._col(PROFILE_COLLECTION)
        results = col.get(ids=["user_profile_v1"], include=["documents"])
        if not results["ids"]:
            return {}
        try:
            return json.loads(results["documents"][0])
        except Exception:
            return {}

    def stats(self) -> dict:
        mem_col = self._col(MEMORY_COLLECTION)
        return {
            "total_memories": mem_col.count(),
            "profile_set": bool(self.get_profile()),
        }


memory = MemoryService()
