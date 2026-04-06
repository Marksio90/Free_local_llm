"""
Hybrydowy builder kontekstu RAG — wersja Enterprise z RRF.

Architektura:
1. Vector search (ChromaDB)  ──┐
                                ├── Reciprocal Rank Fusion (RRF)
2. BM25 search (niezależny) ──┘
3. Pamięć personalna (user_memories)
4. Profil użytkownika

Kluczowa różnica od prostego re-rankingu:
  - BM25 DZIAŁA NIEZALEŻNIE od vector search
  - Jeśli wektor nie znajdzie fragmentu (inny sens semantyczny),
    BM25 nadal go znajdzie po słowach kluczowych
  - RRF łączy obie listy: wyniki w TOP obu algorytmów dostają
    najwyższy scoring końcowy
  - Koszt obliczeniowy: minimalny (BM25 na małym próbce z ChromaDB)
"""

import asyncio
import re
from typing import Dict, List, Tuple

import chromadb
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.services.memory_service import memory
from app.services.rag_service import rag, _parse_chroma_host_port

# Kolekcje "wiedzy" (nie pamięciowe)
IGNORED_COLLECTIONS = {"user_memories", "user_profile"}

# Parametry wyszukiwania
TOP_K_VECTOR = 8         # więcej kandydatów z wektora (było 4)
BM25_CANDIDATE_POOL = 150  # ile doc-ów ładujemy z każdej kolekcji do BM25
BM25_TOP_K = 6           # ile wyników bierzemy z BM25 (niezależnie od wektora)
RRF_K = 60               # standard Robertson et al. — im większe, tym mniejsza różnica między pozycjami
TOP_K_FINAL = 8          # ile wyników po RRF wchodzi do promptu
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
    """Tokenizacja: małe litery, tylko słowa alfanumeryczne."""
    return re.findall(r"\w+", text.lower())


# ── Agent 1: Vector Search ────────────────────────────────────────────────────

async def _vector_search_all(query: str, collections: List[str]) -> List[Tuple[str, float, str]]:
    """
    Semantyczne wyszukiwanie we wszystkich kolekcjach ChromaDB.
    Zwraca [(doc, score, collection_name)] posortowane malejąco po score.
    """
    tasks = []
    for col_name in collections:
        tasks.append(_vector_search_one(col_name, query))
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    for r in results_nested:
        if isinstance(r, list):
            all_results.extend(r)

    all_results.sort(key=lambda x: x[1], reverse=True)
    return all_results[:TOP_K_VECTOR]


async def _vector_search_one(col_name: str, query: str) -> List[Tuple[str, float, str]]:
    """Wyszukiwanie wektorowe w jednej kolekcji."""
    try:
        hits = await rag.search(col_name, query, n_results=TOP_K_VECTOR)
        return [(h["content"], h["score"], col_name) for h in hits]
    except Exception:
        return []


# ── Agent 2: Niezależny BM25 Search ──────────────────────────────────────────

async def _bm25_search_all(query: str, collections: List[str]) -> List[Tuple[str, int, str]]:
    """
    Niezależny BM25 search — działa na innym zbiorze kandydatów niż vector.
    Dzięki temu BM25 może znaleźć fragmenty, które wektor pominął.

    Zwraca [(doc, bm25_rank, collection_name)].
    """
    tokenized_query = _tokenize(query)
    if not tokenized_query:
        return []

    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _bm25_search_one_sync, col_name, tokenized_query)
        for col_name in collections
    ]

    results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    merged: List[Tuple[str, int, str]] = []
    global_rank = 0
    for col_results in results_nested:
        if isinstance(col_results, list):
            for doc, col in col_results:
                merged.append((doc, global_rank, col))
                global_rank += 1

    return merged[:BM25_TOP_K]


def _bm25_search_one_sync(col_name: str, tokenized_query: List[str]) -> List[Tuple[str, str]]:
    """
    Synchroniczny BM25 na próbce dokumentów z jednej kolekcji.
    Działa w ThreadPoolExecutor (nie blokuje event loop).
    Zwraca [(doc, col_name)] posortowane malejąco.
    """
    try:
        host, port = _parse_chroma_host_port(settings.chroma_url)
        client = chromadb.HttpClient(host=host, port=port)
        col = client.get_or_create_collection(col_name)
        total = col.count()
        if total == 0:
            return []

        # Pobierz próbkę dokumentów do BM25
        sample_size = min(total, BM25_CANDIDATE_POOL)
        result = col.get(limit=sample_size, include=["documents"])
        docs = result.get("documents", [])
        docs = [d for d in docs if d and len(d.strip()) > 20]
        if not docs:
            return []

        # Oblicz BM25
        tokenized_corpus = [_tokenize(d) for d in docs]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)

        # Wybierz top wyniki z pozytywnym score
        top_indices = sorted(
            (i for i in range(len(scores)) if scores[i] > 0),
            key=lambda i: scores[i],
            reverse=True,
        )[:BM25_TOP_K]

        return [(docs[i], col_name) for i in top_indices]
    except Exception:
        return []


# ── Reciprocal Rank Fusion ─────────────────────────────────────────────────────

def _reciprocal_rank_fusion(
    vector_results: List[Tuple[str, float, str]],
    bm25_results: List[Tuple[str, int, str]],
    k: int = RRF_K,
) -> List[Tuple[str, float, str]]:
    """
    Reciprocal Rank Fusion (Robertson et al., 2009).

    Wzór: score(d) = Σ 1/(k + rank_i)
      dla każdej listy rankingowej w której dokument d się pojawia.

    Dlaczego k=60?
      Dokumenty na pozycjach > 60 mają mały wpływ na wynik końcowy,
      co zmniejsza ryzyko "przeciągania" przez jeden bardzo wysoko rankowany
      ale błędnie trafiony wynik.

    Wynik: lista (doc, rrf_score, col) posortowana malejąco.
    """
    rrf_scores: Dict[str, float] = {}
    doc_meta: Dict[str, Tuple[str, str]] = {}  # key → (doc, col)

    # Dodaj wyniki z vector search
    for rank, (doc, _score, col) in enumerate(vector_results):
        key = doc[:120]  # klucz deduplicacji
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        if key not in doc_meta:
            doc_meta[key] = (doc, col)

    # Dodaj wyniki z BM25 (niezależna lista rankingowa)
    for bm25_rank, (doc, _int_rank, col) in enumerate(bm25_results):
        key = doc[:120]
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + bm25_rank + 1)
        if key not in doc_meta:
            doc_meta[key] = (doc, col)

    # Posortuj po RRF score malejąco
    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    return [
        (doc_meta[key][0], rrf_scores[key], doc_meta[key][1])
        for key in sorted_keys[:TOP_K_FINAL]
    ]


# ── Deduplikacja ──────────────────────────────────────────────────────────────

def _deduplicate(chunks: List[Tuple[str, float, str]]) -> List[Tuple[str, float, str]]:
    """Usuwa bardzo podobne fragmenty (pierwsze 100 znaków jako fingerprint)."""
    seen = set()
    unique = []
    for doc, score, col in chunks:
        key = doc[:100].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append((doc, score, col))
    return unique


# ── Główna funkcja ────────────────────────────────────────────────────────────

async def build_context(query: str, include_memory: bool = True) -> dict:
    """
    Buduje pełny kontekst RAG dla zapytania używając prawdziwego hybrydowego
    wyszukiwania Vector + BM25 połączonego algorytmem RRF.

    Vector i BM25 działają RÓWNOLEGLE i NIEZALEŻNIE — każde
    może znaleźć inne fragmenty, RRF scala i rankuje końcowo.
    """
    collections = _get_all_knowledge_collections()

    if collections:
        # 1. Uruchom vector search i BM25 RÓWNOLEGLE (nie sekwencyjnie!)
        vector_hits, bm25_hits = await asyncio.gather(
            _vector_search_all(query, collections),
            _bm25_search_all(query, collections),
        )

        # 2. Połącz algorytmem RRF
        rrf_results = _reciprocal_rank_fusion(vector_hits, bm25_hits)

        # 3. Deduplikacja
        knowledge_chunks = _deduplicate(rrf_results)
    else:
        vector_hits = []
        bm25_hits = []
        knowledge_chunks = []

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

    # 6. Zbuduj blok kontekstu (z limitem znaków)
    context_parts = []
    chars_used = 0

    if knowledge_chunks:
        context_parts.append("## Wyuczona wiedza (kod, dokumenty, Wikipedia):\n")
        for doc, score, col in knowledge_chunks:
            snippet = doc[:900]
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

    all_cols = list({col for _, _, col in (vector_hits or [])})

    return {
        "context_block": "\n".join(context_parts),
        "knowledge_count": len(knowledge_chunks),
        "memory_count": len(memory_chunks),
        "collections_searched": all_cols,
        "user_profile": user_profile,
        # Metryki diagnostyczne
        "vector_hits": len(vector_hits),
        "bm25_hits": len(bm25_hits) if collections else 0,
        "rrf_merged": len(knowledge_chunks),
    }


def build_system_prompt(context: dict, base_system: str = "") -> str:
    """Buduje system prompt z kontekstem RAG + profilem użytkownika."""
    profile = context.get("user_profile", {})
    profile_str = ""
    if profile:
        name = profile.get("name", "")
        langs = ", ".join(profile.get("languages", []))
        style = profile.get("style", "")
        profile_str = "\n".join(filter(None, [
            "## Profil użytkownika:",
            f"Imię: {name}" if name else "",
            f"Główne języki: {langs}" if langs else "",
            f"Styl pracy: {style}" if style else "",
        ]))

    context_block = context.get("context_block", "")

    default_system = (
        "Jesteś prywatnym, lokalnym asystentem AI. "
        "Masz wyuczoną wiedzę z repozytoriów użytkownika i Wikipedii. "
        "Odpowiadaj precyzyjnie, konkretnie i w stylu dopasowanym do użytkownika. "
        "Korzystaj z dostarczonego kontekstu — to Twoja wyuczona wiedza."
    )

    parts = [base_system or default_system, profile_str, context_block]
    return "\n\n".join(p for p in parts if p).strip()
