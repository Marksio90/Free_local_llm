"""
Topic Tracker — serce systemu uczenia się.

Śledzi tematy które Cię interesują i automatycznie
zbiera na ich temat wiedzę z internetu.

Jak rośnie lista tematów:
  1. Ręcznie dodane przez Ciebie
  2. Auto-ekstrakcja z Twoich rozmów (chat → tematy)
  3. Ze statystyk GitHub (języki, biblioteki, tematy repo)
  4. Z commit messages i README

Co robi z tematami:
  → DuckDuckGo top wyniki → ingestia
  → Wikipedia artykuł → ingestia
  → RSS feed jeśli skonfigurowany
  → Powtarza co X godzin

Efekt: po kilku tygodniach model zna dogłębnie
wszystko co Cię kiedykolwiek interesowało.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.services.web_intel_service import search_and_ingest, fetch_wikipedia, ingest_rss_feed

logger = logging.getLogger(__name__)

TOPICS_FILE = Path(settings.data_dir) / "topics.json"
FEEDS_FILE = Path(settings.data_dir) / "rss_feeds.json"

# Tematy domyślne do bootstrapu (usuwalne)
DEFAULT_TOPICS = [
    "large language models",
    "ollama local llm",
    "RAG retrieval augmented generation",
    "python fastapi",
    "docker containers",
]

# Domyślne RSS feeds (techniczne, darmowe)
DEFAULT_FEEDS = [
    {"url": "https://hnrss.org/frontpage", "name": "Hacker News", "category": "tech"},
    {"url": "https://feeds.feedburner.com/PythonInsider", "name": "Python Blog", "category": "python"},
]


def _load_topics() -> list[dict]:
    try:
        return json.loads(TOPICS_FILE.read_text())
    except FileNotFoundError:
        # Bootstrap z domyślnymi tematami tylko przy pierwszym uruchomieniu
        topics = [_make_topic(t) for t in DEFAULT_TOPICS]
        _save_topics(topics)
        return topics
    except json.JSONDecodeError:
        logger.error("topics.json uszkodzony — nie nadpisuję, zwracam pustą listę")
        return []


def _save_topics(topics: list[dict]):
    TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOPICS_FILE.write_text(json.dumps(topics, indent=2, ensure_ascii=False))


def _make_topic(name: str, source: str = "manual", crawl_hours: int = 24) -> dict:
    return {
        "name": name,
        "query": name,
        "source": source,
        "enabled": True,
        "crawl_interval_hours": crawl_hours,
        "last_crawled": None,
        "crawl_count": 0,
        "added_at": datetime.utcnow().isoformat(),
    }


def _load_feeds() -> list[dict]:
    if FEEDS_FILE.exists():
        try:
            return json.loads(FEEDS_FILE.read_text())
        except Exception:
            pass
    _save_feeds(DEFAULT_FEEDS)
    return DEFAULT_FEEDS


def _save_feeds(feeds: list[dict]):
    FEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEEDS_FILE.write_text(json.dumps(feeds, indent=2, ensure_ascii=False))


# ── Public API ───────────────────────────────────────────────────────────────

def add_topic(name: str, source: str = "manual", crawl_hours: int = 24) -> dict:
    topics = _load_topics()
    name = name.strip().lower()
    # Sprawdź duplikaty
    for t in topics:
        if t["name"].lower() == name:
            return t
    topic = _make_topic(name, source, crawl_hours)
    topics.append(topic)
    _save_topics(topics)
    logger.info(f"Dodano temat: '{name}' (źródło: {source})")
    return topic


def remove_topic(name: str) -> bool:
    topics = _load_topics()
    before = len(topics)
    topics = [t for t in topics if t["name"].lower() != name.lower()]
    _save_topics(topics)
    return len(topics) < before


def list_topics() -> list[dict]:
    return _load_topics()


def add_feed(url: str, name: str = "", category: str = "general") -> dict:
    feeds = _load_feeds()
    for f in feeds:
        if f["url"] == url:
            return f
    feed = {"url": url, "name": name or url, "category": category}
    feeds.append(feed)
    _save_feeds(feeds)
    return feed


def list_feeds() -> list[dict]:
    return _load_feeds()


# ── Topic crawl ──────────────────────────────────────────────────────────────

async def crawl_topic(topic_name: str, force: bool = False) -> dict:
    """Crawl jednego tematu: DuckDuckGo + Wikipedia."""
    topics = _load_topics()
    topic = next((t for t in topics if t["name"].lower() == topic_name.lower()), None)

    if not topic:
        topic = _make_topic(topic_name, "auto")
        topics.append(topic)

    # Sprawdź czy już niedawno crawlowany
    if not force and topic.get("last_crawled"):
        last = datetime.fromisoformat(topic["last_crawled"])
        hours_since = (datetime.utcnow() - last).total_seconds() / 3600
        if hours_since < topic.get("crawl_interval_hours", 24):
            return {"topic": topic_name, "status": "skipped", "reason": f"crawled {hours_since:.1f}h ago"}

    results = {"topic": topic_name, "ddg": {}, "wikipedia": {}}

    # 1. DuckDuckGo
    try:
        ddg = await search_and_ingest(topic["query"])
        results["ddg"] = ddg
        logger.info(f"DDG '{topic_name}': +{ddg.get('ingested', 0)} stron")
    except Exception as e:
        logger.warning(f"DDG crawl '{topic_name}': {e}")

    # 2. Wikipedia
    try:
        wiki = await fetch_wikipedia(topic["query"])
        results["wikipedia"] = wiki
    except Exception as e:
        logger.debug(f"Wikipedia '{topic_name}': {e}")

    # Aktualizuj stan
    for t in topics:
        if t["name"].lower() == topic_name.lower():
            t["last_crawled"] = datetime.utcnow().isoformat()
            t["crawl_count"] = t.get("crawl_count", 0) + 1
            break
    _save_topics(topics)

    return results


async def crawl_all_due_topics() -> dict:
    """Crawl wszystkich tematów które wymagają odświeżenia. Wywoływany przez scheduler."""
    topics = _load_topics()
    crawled = 0
    skipped = 0

    for topic in topics:
        if not topic.get("enabled", True):
            continue
        result = await crawl_topic(topic["name"])
        if result.get("status") == "skipped":
            skipped += 1
        else:
            crawled += 1

    # Refresh RSS feeds
    feeds = _load_feeds()
    for feed in feeds:
        try:
            await ingest_rss_feed(feed["url"], max_articles=10)
        except Exception as e:
            logger.warning(f"RSS {feed['url']}: {e}")

    logger.info(f"Crawler: {crawled} tematów odświeżono, {skipped} pominięto")
    return {"crawled": crawled, "skipped": skipped}


# ── Auto-ekstrakcja tematów z tekstu ─────────────────────────────────────────

_STOP_WORDS = {
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "for",
    "of", "and", "or", "but", "with", "from", "by", "as", "this",
    "that", "are", "was", "be", "have", "do", "jak", "co", "czy",
    "nie", "tak", "się", "to", "że", "w", "z", "do", "na", "i",
    "o", "po", "przez", "ale", "więc", "więcej", "mnie", "mi",
}

# Wzorce techniczne — warto zawsze wyciągać
_TECH_PATTERN = re.compile(
    r"\b(python|fastapi|docker|kubernetes|react|typescript|javascript|"
    r"golang|rust|llm|gpt|ollama|rag|chromadb|redis|postgresql|mongodb|"
    r"langchain|huggingface|transformers|lora|gguf|quantization|"
    r"embedding|vector|fine.?tun|machine.?learning|deep.?learning|"
    r"neural|attention|transformer|bert|qwen|llama|mistral|"
    r"git|github|linux|nginx|fastapi|flask|django|nextjs|tailwind|"
    r"pytorch|tensorflow|numpy|pandas|sklearn|opencv)\b",
    re.IGNORECASE,
)


def extract_topics_from_text(text: str, max_topics: int = 5) -> list[str]:
    """
    Wyciąga tematy z tekstu.

    Najpierw szuka znanych terminów technicznych,
    potem wyciąga rzeczowniki wielowyrazowe (n-gramy).
    """
    topics = set()

    # 1. Znane techniczne terminy
    for match in _TECH_PATTERN.finditer(text):
        topics.add(match.group(0).lower())

    # 2. Wielowyrazowe frazy (2-3 słowa po wielkich literach lub w cudzysłowie)
    quoted = re.findall(r'"([^"]{5,50})"', text)
    for q in quoted:
        if len(q.split()) <= 4:
            topics.add(q.lower())

    # 3. Frazy po "o", "pytanie o", "jak", "co to", "czym jest"
    patterns = [
        r"(?:czym jest|co to|jak działa|pytanie o|więcej o)\s+([a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ ]{3,40}?)(?:\?|,|\.|\n|$)",
        r"(?:how|what is|explain|about)\s+([a-zA-Z ]{3,40}?)(?:\?|,|\.|\n|$)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            phrase = m.group(1).strip().lower()
            if phrase and len(phrase.split()) <= 4:
                words = phrase.split()
                if not all(w in _STOP_WORDS for w in words):
                    topics.add(phrase)

    return list(topics)[:max_topics]


async def auto_learn_from_exchange(user_msg: str, assistant_msg: str):
    """
    Wywoływane po każdej rozmowie.
    Wyciąga tematy i w tle zbiera o nich wiedzę z internetu.
    """
    combined = f"{user_msg} {assistant_msg}"
    topics = extract_topics_from_text(combined)

    for topic in topics:
        if len(topic) < 4:
            continue
        # Dodaj do trackera z niskim priorytetem (crawl co 48h)
        add_topic(topic, source="chat_auto", crawl_hours=48)
        # Crawl asynchronicznie (nie czekamy na wynik)
        try:
            await crawl_topic(topic)
        except Exception as e:
            logger.debug(f"auto_learn crawl '{topic}': {e}")
