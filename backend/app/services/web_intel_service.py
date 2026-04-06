"""
Web Intelligence Service — darmowe zbieranie wiedzy z internetu.

Źródła:
  • DuckDuckGo (bez API key, całkowicie bezpłatny)
  • Wikipedia (API bezpłatne)
  • RSS/Atom feeds
  • Bezpośrednie URL

Zabezpieczenia przed blokadą IP:
  • User-Agent rotation (pula 8 różnych przeglądarek)
  • Exponential backoff przy błędach HTTP 429/503
  • Naturalne opóźnienia między żądaniami (0.5–2s)

Ekstrakcja treści: trafilatura — wycina reklamy, nawigację, boilerplate,
zostawia sam merytoryczny tekst.
"""

import asyncio
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from app.services.rag_service import rag
from app.services.github_service import CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

WEB_COLLECTION = "web_intel"
_executor = ThreadPoolExecutor(max_workers=2)  # zmniejszone z 4 → laptop-friendly

# ── User-Agent rotation ───────────────────────────────────────────────────────
# Pula realistycznych User-Agentów różnych przeglądarek/OS.
# Losowe wybieranie sprawia, że ruch wygląda jak normalny ruch użytkowników.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
]


def _get_random_headers() -> dict:
    """Zwróć losowe nagłówki HTTP imitujące prawdziwą przeglądarkę."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


# ── Exponential Backoff dla DuckDuckGo ───────────────────────────────────────

def _ddg_search_sync(query: str, max_results: int = 5) -> list:
    """
    DuckDuckGo text search z exponential backoff i rotacją User-Agent.
    Przy błędzie 202/429/rate-limit: czeka i ponawia (max 3 próby).
    Synchroniczna — uruchom w executor.
    """
    wait = 2.0
    for attempt in range(3):
        try:
            if attempt > 0:
                # Exponential backoff z jitter: 2s → ~4-6s → ~8-12s
                jitter = random.uniform(0.8, 1.5)
                sleep_time = wait * jitter
                logger.info(f"DDG retry {attempt}/3: czekam {sleep_time:.1f}s")
                time.sleep(sleep_time)
                wait *= 2

            with DDGS(headers={"User-Agent": random.choice(_USER_AGENTS)}) as ddgs:
                results = list(ddgs.text(
                    query,
                    max_results=max_results,
                    safesearch="moderate",
                ))
            # Naturalne opóźnienie po wyszukiwaniu
            time.sleep(random.uniform(0.5, 1.5))
            return results
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(kw in err_str for kw in ["202", "429", "rate", "blocked", "ratelimit"])
            if is_rate_limit:
                logger.warning(f"DDG rate limit (próba {attempt + 1}/3)")
            else:
                logger.warning(f"DDG search '{query}' błąd (próba {attempt + 1}/3): {e}")
            if attempt == 2:
                return []
    return []


# ── Ekstrakcja treści ────────────────────────────────────────────────────────

def _extract_text_sync(url: str, html: Optional[str] = None) -> str:
    """Wyciąga czysty tekst ze strony z losowymi nagłówkami."""
    try:
        if html is None:
            import urllib.request
            req = urllib.request.Request(url, headers=_get_random_headers())
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
            except Exception:
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
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            return "\n".join(lines)
    except Exception as e:
        logger.debug(f"Ekstrakcja {url}: {e}")
    return ""


async def fetch_and_extract(url: str) -> str:
    """Asynchroniczne pobranie i ekstrakcja tekstu ze strony."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_executor, _extract_text_sync, url, None)
    except Exception as e:
        logger.warning(f"fetch_and_extract {url}: {e}")
        return ""


def _chunk_web_text(text: str, url: str, title: str = "") -> tuple:
    """Dzieli tekst webowy na fragmenty z metadanymi."""
    header = f"Źródło: {url}\n{f'Tytuł: {title}' if title else ''}\n\n"
    chunks, metas = [], []

    if len(text) <= CHUNK_SIZE:
        chunks.append(header + text)
        metas.append({"url": url, "title": title, "chunk": 0, "source": "web"})
    else:
        start, idx = 0, 0
        while start < len(text):
            chunk = text[start : start + CHUNK_SIZE]
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

async def search_and_ingest(query: str, max_results: int = 5, collection: str = WEB_COLLECTION) -> dict:
    """
    Szukaj w DuckDuckGo i zaingestionuj wyniki.
    Używa exponential backoff i rotacji User-Agent — odporne na blokadę IP.
    """
    loop = asyncio.get_running_loop()
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

        domain = urlparse(url).netloc
        if any(skip in domain for skip in ["youtube.com", "twitter.com", "x.com", "facebook.com", "instagram.com"]):
            continue

        try:
            if body and len(body) > 100:
                snippet_chunks = [f"Źródło: {url}\nTytuł: {title}\n\nFragment: {body}"]
                snippet_metas = [{"url": url, "title": title, "chunk": 0, "source": "ddg_snippet", "query": query}]
                await rag.add_chunks(collection, snippet_chunks, snippet_metas)

            # Naturalne opóźnienie między stronami (0.3–1.0s)
            await asyncio.sleep(random.uniform(0.3, 1.0))
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
    Pobierz artykuł Wikipedii. Darmowe MediaWiki API — brak limitów przy normalnym użyciu.
    """
    for wiki_lang in ([lang, "en"] if lang != "en" else ["en"]):
        api_url = f"https://{wiki_lang}.wikipedia.org/api/rest_v1/page/summary/{topic.replace(' ', '_')}"
        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": random.choice(_USER_AGENTS)}
            ) as client:
                r = await client.get(api_url, follow_redirects=True)
                if r.status_code != 200:
                    continue
                data = r.json()
                title = data.get("title", topic)
                extract = data.get("extract", "")

                if extract and len(extract) > 200:
                    full_url = f"https://{wiki_lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    result = await ingest_url(full_url, f"Wikipedia: {title}", collection)
                    return {"topic": topic, "title": title, "url": full_url, **result}
        except Exception as e:
            logger.debug(f"Wikipedia '{topic}' ({wiki_lang}): {e}")

    return {"topic": topic, "status": "not_found"}


# ── RSS Feeds ─────────────────────────────────────────────────────────────────

def _parse_feed_sync(feed_url: str) -> list:
    """Parsuj RSS feed synchronicznie."""
    import feedparser
    try:
        feed = feedparser.parse(feed_url)
        return [
            {
                "title": getattr(e, "title", ""),
                "url": getattr(e, "link", ""),
                "summary": getattr(e, "summary", ""),
                "published": getattr(e, "published", ""),
            }
            for e in feed.entries[:20]
        ]
    except Exception as e:
        logger.warning(f"RSS parse {feed_url}: {e}")
        return []


async def ingest_rss_feed(feed_url: str, max_articles: int = 10, collection: str = WEB_COLLECTION) -> dict:
    """Ingestion RSS feed — nowe artykuły trafiają do ChromaDB."""
    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(_executor, _parse_feed_sync, feed_url)

    ingested = 0
    for item in items[:max_articles]:
        url = item.get("url", "")
        title = item.get("title", "")
        if url:
            r = await ingest_url(url, title, collection)
            if r.get("status") == "ok":
                ingested += 1
            await asyncio.sleep(random.uniform(0.2, 0.8))

    return {"feed_url": feed_url, "items_found": len(items), "ingested": ingested}
