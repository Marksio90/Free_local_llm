"""
Web Intelligence API — zarządzanie automatycznym uczeniem się z internetu.
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.services.topic_tracker_service import (
    add_topic, remove_topic, list_topics, crawl_topic,
    crawl_all_due_topics, add_feed, list_feeds,
)
from app.services.web_intel_service import (
    ingest_url, search_and_ingest, fetch_wikipedia, ingest_rss_feed,
)

router = APIRouter()


class TopicRequest(BaseModel):
    name: str
    crawl_hours: int = 24


class UrlRequest(BaseModel):
    url: str
    title: str = ""
    collection: str = "web_intel"


class SearchRequest(BaseModel):
    query: str
    max_results: int = 6


class FeedRequest(BaseModel):
    url: str
    name: str = ""
    category: str = "general"


# ── Tematy ──────────────────────────────────────────────────────────────────

@router.get("/topics")
async def get_topics():
    """Lista śledzonych tematów."""
    return list_topics()


@router.post("/topics")
async def create_topic(req: TopicRequest):
    """Dodaj temat do śledzenia."""
    return add_topic(req.name, source="manual", crawl_hours=req.crawl_hours)


@router.delete("/topics/{name}")
async def delete_topic(name: str):
    ok = remove_topic(name)
    return {"deleted": ok, "name": name}


@router.post("/topics/{name}/crawl")
async def crawl_topic_now(name: str, background: BackgroundTasks):
    """Natychmiastowy crawl tematu (w tle)."""
    background.add_task(crawl_topic, name, True)
    return {"status": "queued", "topic": name}


@router.post("/crawl-all")
async def crawl_all(background: BackgroundTasks):
    """Crawl wszystkich zaległych tematów (w tle)."""
    background.add_task(crawl_all_due_topics)
    return {"status": "queued"}


# ── Bezpośrednia ingestia ────────────────────────────────────────────────────

@router.post("/ingest-url")
async def ingest_single_url(req: UrlRequest):
    """Wgraj dowolną stronę do bazy wiedzy."""
    result = await ingest_url(req.url, req.title, req.collection)
    return result


@router.post("/search-ingest")
async def search_and_ingest_topic(req: SearchRequest, background: BackgroundTasks):
    """
    Szukaj w DuckDuckGo i zaingestionuj wyniki.
    Wyniki trafiają do kolekcji 'web_intel'.
    """
    background.add_task(search_and_ingest, req.query, req.max_results)
    return {"status": "queued", "query": req.query}


@router.post("/wikipedia")
async def fetch_wiki(topic: str, background: BackgroundTasks):
    """Pobierz artykuł Wikipedii na podany temat."""
    background.add_task(fetch_wikipedia, topic)
    return {"status": "queued", "topic": topic}


# ── RSS Feeds ─────────────────────────────────────────────────────────────────

@router.get("/feeds")
async def get_feeds():
    return list_feeds()


@router.post("/feeds")
async def add_rss_feed(req: FeedRequest):
    return add_feed(req.url, req.name, req.category)


@router.post("/feeds/refresh")
async def refresh_feeds(background: BackgroundTasks):
    """Odśwież wszystkie RSS feeds."""
    async def _refresh():
        for feed in list_feeds():
            await ingest_rss_feed(feed["url"])

    background.add_task(_refresh)
    return {"status": "queued"}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def intel_stats():
    """Statystyki systemu web intelligence."""
    from app.services.rag_service import rag
    try:
        web_col = rag.collection_stats("web_intel")
    except Exception:
        web_col = {"count": 0}
    try:
        stars_col = rag.collection_stats("github_stars")
    except Exception:
        stars_col = {"count": 0}
    try:
        gists_col = rag.collection_stats("github_gists")
    except Exception:
        gists_col = {"count": 0}
    try:
        activity_col = rag.collection_stats("github_activity")
    except Exception:
        activity_col = {"count": 0}

    topics = list_topics()
    crawled = sum(1 for t in topics if t.get("last_crawled"))

    return {
        "topics_tracked": len(topics),
        "topics_crawled": crawled,
        "web_intel_chunks": web_col.get("count", 0),
        "github_stars_chunks": stars_col.get("count", 0),
        "github_gists_chunks": gists_col.get("count", 0),
        "github_activity_chunks": activity_col.get("count", 0),
        "feeds_subscribed": len(list_feeds()),
    }
