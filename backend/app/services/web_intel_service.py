"""
Web Intelligence Service — darmowe zbieranie wiedzy z internetu.

Źródła:
  • DuckDuckGo (bez API key, całkowicie bezpłatny)
  • Wikipedia (API bezpłatne)
  • RSS/Atom feeds
  • Bezpośrednie URL

Ekstrakcja treści: trafilatura — wycina reklamy, nawigację, boilerplate,
zostawia sam merytoryczny tekst.

Wynik trafia do ChromaDB kolekcja "web_intel" i jest automatycznie
dostępny jako kontekst RAG przy każdej rozmowie.
"""

import asyncio
import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from app.services.rag_service import rag
from app.services.github_service import CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

WEB_COLLECTION = "web_intel"
_executor = ThreadPoolExecutor(max_workers=4)

# ── Ekstrakcja treści ────────────────────────────────────────────────────────

def _extract_text_sync(url: str, html: Optional[str] = None) -> str:
    """Wyciąga czysty tekst ze strony. Uruchom w executor (synchroniczna)."""
    try:
        if html is None:
            html = trafilatura.fetch_url(url)
        if html:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_precision=True,
            )
            if text and len(text) > 200:
                return text

        # Fallback: BeautifulSoup
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            # Usuń puste linie
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            return "\n".join(lines)
    except Exception as e:
        logger.debug(f"Ekstrakcja {url} błąd: {e}")
    return ""


async def fetch_and_extract(url: str) -> str:
    """Asynchroniczne pobranie i ekstrakcja tekstu ze strony."""
    loop = asyncio.get_event_loop()
    try:
        text = await loop.run_in_executor(_executor, _extract_text_sync, url, None)
        return text
    except Exception as e:
        logger.warning(f"fetch_and_extract {url}: {e}")
        return ""


def _chunk_web_text(text: str, url: str, title: str = "") -> tuple[list[str], list[dict]]:
    """Dzieli tekst webowy na fragmenty z metadanymi."""
    header = f"Źródło: {url}\n{f'Tytuł: {title}' if title else ''}\n\n"
    chunks, metas = [], []

    if len(text) <= CHUNK_SIZE:
        chunks.append(header + text)
        metas.append({"url": url, "title": title, "chunk": 0, "source": "web"})
    else:
        start, idx = 0, 0
        while start < len(text):
            chunk = text[start:start + CHUNK_SIZE]
            chunks.append(header + chunk)
            metas.append({"url": url, "title": title, "chunk": idx, "source": "web"})
            start += CHUNK_SIZE - CHUNK_OVERLAP
            idx += 1

    return chunks, metas


async def ingest_url(url: str, title: str = "", collection: str = WEB_COLLECTION) -> dict:
    """Pobierz stronę, wyciągnij tekst, zaingestionuj do ChromaDB."""
    text = await fetch_and_extract(url)
    if not text or len(text) < 100:
        return {"url": url, "status": "empty", "chunks": 0}

    chunks, metas = _chunk_web_text(text, url, title)
    added = await rag.add_chunks(collection, chunks, metas)
    return {"url": url, "status": "ok", "chunks": added, "text_len": len(text)}


# ── DuckDuckGo Search ─────────────────────────────────────────────────────────

def _ddg_search_sync(query: str, max_results: int = 8) -> list[dict]:
    """DuckDuckGo text search. Synchroniczna — uruchom w executor."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                max_results=max_results,
                safesearch="moderate",
            ))
        return results
    except Exception as e:
        logger.warning(f"DDG search '{query}': {e}")
        return []


async def search_and_ingest(query: str, max_results: int = 6, collection: str = WEB_COLLECTION) -> dict:
    """
    Szukaj w DuckDuckGo i zaingestionuj wyniki.
    Główna funkcja auto-rozszerzania wiedzy.
    """
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_executor, _ddg_search_sync, query, max_results)

    ingested = 0
    failed = 0
    urls = []

    for result in results:
        url = result.get("href", "")
        title = result.get("title", "")
        body = result.get("body", "")

        if not url:
            continue

        # Pomijaj domeny które rzadko dają wartościowy tekst
        domain = urlparse(url).netloc
        if any(skip in domain for skip in ["youtube.com", "twitter.com", "x.com", "facebook.com", "instagram.com"]):
            continue

        try:
            # Najpierw sprawdź czy już mamy ten URL
            url_hash = hashlib.md5(url.encode()).hexdigest()

            # Jeśli DuckDuckGo dał nam snippet, możemy użyć go jako mini-doc
            if body and len(body) > 100:
                snippet_chunks = [f"Źródło: {url}\nTytuł: {title}\n\nFragment: {body}"]
                snippet_metas = [{"url": url, "title": title, "chunk": 0, "source": "ddg_snippet", "query": query}]
                await rag.add_chunks(collection, snippet_chunks, snippet_metas)

            # Pełna ingestia strony
            result_data = await ingest_url(url, title, collection)
            if result_data["status"] == "ok":
                ingested += 1
                urls.append(url)
            else:
                failed += 1
        except Exception as e:
            logger.debug(f"Ingestia {url}: {e}")
            failed += 1

    return {
        "query": query,
        "results_found": len(results),
        "ingested": ingested,
        "failed": failed,
        "urls": urls[:10],
    }


# ── Wikipedia ────────────────────────────────────────────────────────────────

async def fetch_wikipedia(topic: str, lang: str = "pl", collection: str = WEB_COLLECTION) -> dict:
    """
    Pobierz artykuł Wikipedii na dany temat.
    Bezpłatne MediaWiki API.
    """
    # Najpierw szukaj angielskiej wersji (bogatsze artykuły techniczne)
    for wiki_lang in [lang, "en"] if lang != "en" else ["en"]:
        api_url = f"https://{wiki_lang}.wikipedia.org/api/rest_v1/page/summary/{topic.replace(' ', '_')}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(api_url, follow_redirects=True)
                if r.status_code != 200:
                    continue
                data = r.json()
                title = data.get("title", topic)
                extract = data.get("extract", "")
                page_url = data.get("content_urls", {}).get("desktop", {}).get("page", api_url)

                if extract and len(extract) > 200:
                    # Pobierz pełny artykuł
                    full_url = f"https://{wiki_lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    result = await ingest_url(full_url, f"Wikipedia: {title}", collection)
                    return {"topic": topic, "title": title, "url": full_url, **result}
        except Exception as e:
            logger.debug(f"Wikipedia '{topic}' ({wiki_lang}): {e}")

    return {"topic": topic, "status": "not_found"}


# ── RSS Feeds ─────────────────────────────────────────────────────────────────

def _parse_feed_sync(feed_url: str) -> list[dict]:
    """Parsuj RSS feed synchronicznie."""
    import feedparser
    try:
        feed = feedparser.parse(feed_url)
        items = []
        for entry in feed.entries[:20]:
            items.append({
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "summary": getattr(entry, "summary", ""),
                "published": getattr(entry, "published", ""),
            })
        return items
    except Exception as e:
        logger.warning(f"RSS parse {feed_url}: {e}")
        return []


async def ingest_rss_feed(feed_url: str, max_articles: int = 10, collection: str = WEB_COLLECTION) -> dict:
    """Ingestion RSS feed — nowe artykuły trafiają do ChromaDB."""
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(_executor, _parse_feed_sync, feed_url)

    ingested = 0
    for item in items[:max_articles]:
        url = item.get("url", "")
        title = item.get("title", "")
        if url:
            r = await ingest_url(url, title, collection)
            if r.get("status") == "ok":
                ingested += 1

    return {"feed_url": feed_url, "items_found": len(items), "ingested": ingested}
