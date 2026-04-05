"""
Hybrydowy builder kontekstu RAG.

Łączy:
1. Wyszukiwanie wektorowe (semantyczne) — ChromaDB
2. Wyszukiwanie BM25 (słowa kluczowe) — rank_bm25
3. Pamięć personalna — user_memories
4. Profil użytkownika

Wynik: kompaktowy blok kontekstu do wstrzyknięcia w system prompt.
"""

import re
from typing import List, Tuple

from rank_bm25 import BM25Okapi

from app.services.rag_service import rag, _parse_chroma_host_port
from app.services.memory_service import memory
from app.core.config import settings
import chromadb

# Kolekcje które są "wiedzą" (nie pamięcią)
KNOWLEDGE_COLLECTION_PREFIXES = ["documents", "github_", "upload_"]
IGNORED_COLLECTIONS = {"user_memories", "user_profile"}

# Ile chunków z każdego źródła
TOP_K_VECTOR = 4
TOP_K_BM25 = 3
TOP_K_MEMORY = 3
MAX_CONTEXT_CHARS = 6000


def _get_all_knowledge_collections() -> List[str]:
    """Pobiera wszystkie kolekcje wiedzy (nie pamięciowe)."""
    try:
        host, port = _parse_chroma_host_port(settings.chroma_url)
        client = chromadb.HttpClient(host=host, port=port)
        all_cols = client.list_collections()
        return [c.name for c in all_cols if c.name not in IGNORED_COLLECTIONS]
    except Exception:
        return []


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


async def _vector_search_all(query: str) -> List[Tuple[str, float, str]]:
    """Przeszukuje wszystkie kolekcje wiedzy wektorowo."""
    collections = _get_all_knowledge_collections()
    results = []
    for col_name in collections:
        try:
            hits = await rag.search(col_name, query, n_results=TOP_K_VECTOR)
            for h in hits:
                results.append((h["content"], h["score"], col_name))
        except Exception:
            continue
    # Posortuj po score malejąco
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:TOP_K_VECTOR * 2]


def _bm25_rerank(query: str, candidates: List[Tuple[str, float, str]]) -> List[Tuple[str, float, str]]:
    """Re-ranking BM25 na kandydatach z vector search."""
    if not candidates:
        return []
    tokenized_query = _tokenize(query)
    corpus = [_tokenize(doc) for doc, _, _ in candidates]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenized_query)
    # Kombinuj score BM25 + vector (normalizuj BM25 do 0-1)
    max_bm25 = max(scores) if max(scores) > 0 else 1
    combined = []
    for i, (doc, vec_score, col) in enumerate(candidates):
        bm25_norm = scores[i] / max_bm25
        combined_score = 0.6 * vec_score + 0.4 * bm25_norm
        combined.append((doc, combined_score, col))
    combined.sort(key=lambda x: x[1], reverse=True)
    return combined[:TOP_K_BM25 + TOP_K_VECTOR]


def _deduplicate(chunks: List[Tuple[str, float, str]]) -> List[Tuple[str, float, str]]:
    """Usuwa bardzo podobne fragmenty."""
    seen = []
    unique = []
    for doc, score, col in chunks:
        key = doc[:100].lower()
        if key not in seen:
            seen.append(key)
            unique.append((doc, score, col))
    return unique


async def build_context(query: str, include_memory: bool = True) -> dict:
    """
    Główna funkcja: buduje pełny kontekst dla zapytania.
    Zwraca słownik z sekcjami kontekstu i metadanymi.
    """
    # 1. Wyszukiwanie wektorowe we wszystkich kolekcjach
    vector_hits = await _vector_search_all(query)

    # 2. Re-ranking BM25
    reranked = _bm25_rerank(query, vector_hits)

    # 3. Deduplikacja
    knowledge_chunks = _deduplicate(reranked)

    # 4. Pamięć personalna
    memory_chunks = []
    if include_memory:
        try:
            memory_chunks = await memory.search(query, n=TOP_K_MEMORY)
        except Exception:
            pass

    # 5. Profil użytkownika
    user_profile = {}
    try:
        user_profile = memory.get_profile()
    except Exception:
        pass

    # 6. Zbuduj blok kontekstu
    context_parts = []
    chars_used = 0

    if knowledge_chunks:
        context_parts.append("## Kontekst z Twoich repozytoriów i dokumentów:\n")
        for doc, score, col in knowledge_chunks:
            snippet = doc[:800]
            if chars_used + len(snippet) > MAX_CONTEXT_CHARS:
                break
            context_parts.append(f"[{col}] {snippet}\n---")
            chars_used += len(snippet)

    if memory_chunks:
        context_parts.append("\n## Poprzednie rozmowy (pamięć):\n")
        for m in memory_chunks:
            snippet = m["content"][:400]
            if chars_used + len(snippet) > MAX_CONTEXT_CHARS:
                break
            context_parts.append(f"{snippet}\n---")
            chars_used += len(snippet)

    return {
        "context_block": "\n".join(context_parts),
        "knowledge_count": len(knowledge_chunks),
        "memory_count": len(memory_chunks),
        "collections_searched": list({col for _, _, col in (vector_hits or [])}),
        "user_profile": user_profile,
    }


def build_system_prompt(context: dict, base_system: str = "") -> str:
    """
    Buduje system prompt z kontekstem RAG + profilem.
    """
    profile = context.get("user_profile", {})
    profile_str = ""
    if profile:
        name = profile.get("name", "")
        langs = ", ".join(profile.get("languages", []))
        style = profile.get("style", "")
        profile_str = f"""
## Profil użytkownika:
{f"Imię: {name}" if name else ""}
{f"Główne języki: {langs}" if langs else ""}
{f"Styl pracy: {style}" if style else ""}
""".strip()

    context_block = context.get("context_block", "")

    parts = [
        base_system or (
            "Jesteś prywatnym, lokalnym asystentem AI wytrenowanym na danych użytkownika. "
            "Odpowiadaj precyzyjnie, konkretnie i w stylu dopasowanym do użytkownika. "
            "Korzystaj z dostarczonego kontekstu z repozytoriów i wcześniejszych rozmów."
        ),
        profile_str,
        context_block,
    ]

    return "\n\n".join(p for p in parts if p).strip()
