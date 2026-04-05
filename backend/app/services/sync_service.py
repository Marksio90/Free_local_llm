"""
Serwis auto-sync GitHub.

Łączy się z kontem GitHub użytkownika przez token API,
pobiera listę wszystkich repo (własnych + forków),
klonuje je lokalnie i ingestionuje do ChromaDB.

Uruchamia się:
- manualnie (POST /api/sync/trigger)
- automatycznie co 24h przez scheduler
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from github import Github, GithubException

from app.core.config import settings
from app.services import github_service
from app.services.rag_service import rag

logger = logging.getLogger(__name__)

SYNC_STATE_FILE = Path(settings.data_dir) / "sync_state.json"

# In-memory status sync
_sync_status = {
    "running": False,
    "last_run": None,
    "repos_found": 0,
    "repos_synced": 0,
    "repos_failed": 0,
    "chunks_added": 0,
    "log": [],
    "error": None,
}


def _load_state() -> dict:
    if SYNC_STATE_FILE.exists():
        try:
            return json.loads(SYNC_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _collection_name(repo_full_name: str) -> str:
    """github.com/owner/repo → owner__repo"""
    return repo_full_name.replace("/", "__").replace("-", "_").lower()


async def sync_all_repos(include_forks: bool = False, include_stars: bool = False) -> dict:
    """
    Główna funkcja sync — pobiera i ingestionuje wszystkie repo z GitHub.
    """
    global _sync_status

    if _sync_status["running"]:
        return {"status": "already_running"}

    if not settings.github_token:
        return {"status": "error", "error": "GITHUB_TOKEN nie ustawiony w .env"}

    _sync_status = {
        "running": True,
        "last_run": datetime.utcnow().isoformat(),
        "repos_found": 0,
        "repos_synced": 0,
        "repos_failed": 0,
        "chunks_added": 0,
        "log": [],
        "error": None,
    }

    def log(msg: str):
        logger.info(msg)
        _sync_status["log"].append(f"{datetime.utcnow().strftime('%H:%M:%S')} {msg}")
        if len(_sync_status["log"]) > 200:
            _sync_status["log"] = _sync_status["log"][-100:]

    try:
        gh = Github(settings.github_token)
        user = gh.get_user()
        log(f"Zalogowano jako: {user.login}")

        # Pobierz wszystkie repo użytkownika
        repos = []
        for repo in user.get_repos(type="owner"):
            if not include_forks and repo.fork:
                continue
            repos.append(repo)

        if include_stars:
            for repo in user.get_starred():
                repos.append(repo)

        _sync_status["repos_found"] = len(repos)
        log(f"Znaleziono {len(repos)} repozytoriów")

        # Ingestion każdego repo
        for repo in repos:
            try:
                log(f"Syncing: {repo.full_name}")
                repo_url = repo.clone_url  # HTTPS URL

                # Klonuj/aktualizuj
                repo_path = github_service.clone_or_update(repo_url)

                # Wyodrębnij pliki
                files = github_service.extract_files(repo_path)
                log(f"  {repo.full_name}: {len(files)} plików")

                # Ingestion do ChromaDB
                collection = _collection_name(repo.full_name)
                chunks_added = 0
                for f in files:
                    chunks, metas = github_service.chunk_file(f)
                    # Dodaj metadane repo
                    for m in metas:
                        m["repo"] = repo.full_name
                        m["language"] = repo.language or "unknown"
                        m["stars"] = repo.stargazers_count
                    added = await rag.add_chunks(collection, chunks, metas)
                    chunks_added += added

                # Ingestion opisu repo (README + description)
                if repo.description:
                    desc_chunks = [f"Repo: {repo.full_name}\nOpis: {repo.description}"]
                    desc_metas = [{"type": "description", "repo": repo.full_name}]
                    await rag.add_chunks(collection, desc_chunks, desc_metas)

                _sync_status["repos_synced"] += 1
                _sync_status["chunks_added"] += chunks_added
                log(f"  ✓ {repo.full_name}: +{chunks_added} fragmentów")

            except GithubException as e:
                _sync_status["repos_failed"] += 1
                log(f"  ✗ {repo.full_name}: GitHub API error {e.status}")
            except Exception as e:
                _sync_status["repos_failed"] += 1
                log(f"  ✗ {repo.full_name}: {str(e)[:100]}")

        # ── GitHub Stars → README każdej zainteresowanej biblioteki ──────────
        if include_stars:
            log("Ingestuję GitHub Stars (README + opisy)...")
            await _ingest_stars(gh, user, log)

        # ── Gisty → fragmenty kodu i notatki ─────────────────────────────────
        log("Ingestuję Gists...")
        await _ingest_gists(user, log)

        # ── Issue comments i PR opisy — styl myślenia ────────────────────────
        log("Ingestuję komentarze Issues/PR...")
        await _ingest_activity(user, repos[:20], log)  # tylko top 20 repo

        # Zaktualizuj profil użytkownika na podstawie repo
        await _update_user_profile(user, repos)

        # Dodaj języki/tematy do topic trackera
        await _seed_topics_from_repos(repos, log)

        log(f"Sync zakończony: {_sync_status['repos_synced']}/{_sync_status['repos_found']} repo, "
            f"+{_sync_status['chunks_added']} fragmentów")

        # Zapisz stan
        _save_state(_sync_status)

    except Exception as e:
        _sync_status["error"] = str(e)
        log(f"Błąd krytyczny: {e}")

    finally:
        _sync_status["running"] = False

    return _sync_status


async def _ingest_stars(gh, user, log) -> int:
    """Ingestion README każdego zrepozytoriowanego repo (GitHub Stars).
    Pokazuje co użytkownik uważa za wartościowe w open source."""
    from app.services.web_intel_service import ingest_url
    from app.services.topic_tracker_service import add_topic

    STARS_COLLECTION = "github_stars"
    ingested = 0
    try:
        for repo in user.get_starred()[:100]:  # max 100 starred
            try:
                # README jako główna wiedza o bibliotece
                try:
                    readme = repo.get_readme()
                    content = readme.decoded_content.decode("utf-8", errors="ignore")
                    if content and len(content) > 200:
                        chunks, metas = [], []
                        header = f"# GitHub Star: {repo.full_name}\n{repo.description or ''}\n\n"
                        chunk = header + content[:3000]
                        metas_item = {
                            "type": "star_readme",
                            "repo": repo.full_name,
                            "language": repo.language or "",
                            "stars": repo.stargazers_count,
                        }
                        await rag.add_chunks(STARS_COLLECTION, [chunk], [metas_item])
                        ingested += 1
                except Exception:
                    pass

                # Temat = język + nazwa (np. "python httpx")
                if repo.language:
                    topic_name = f"{repo.language.lower()} {repo.name.lower()}"
                    add_topic(topic_name, source="github_star", crawl_hours=72)

            except Exception:
                continue
        log(f"  Stars: +{ingested} README zaingestionowanych")
    except Exception as e:
        log(f"  Stars błąd: {e}")
    return ingested


async def _ingest_gists(user, log) -> int:
    """Ingestion Gistów użytkownika — często prywatne notatki i snippety."""
    GISTS_COLLECTION = "github_gists"
    ingested = 0
    try:
        for gist in user.get_gists():
            try:
                for filename, gist_file in gist.files.items():
                    content = gist_file.content or ""
                    if len(content) < 50:
                        continue
                    header = f"# Gist: {gist.description or filename}\n\n"
                    chunk = header + content[:2000]
                    meta = {
                        "type": "gist",
                        "filename": filename,
                        "gist_id": gist.id,
                        "description": gist.description or "",
                    }
                    await rag.add_chunks(GISTS_COLLECTION, [chunk], [meta])
                    ingested += 1
            except Exception:
                continue
        log(f"  Gists: +{ingested} fragmentów")
    except Exception as e:
        log(f"  Gists błąd: {e}")
    return ingested


async def _ingest_activity(user, repos: List, log) -> int:
    """
    Ingestion komentarzy Issues i PR — pokazuje styl myślenia i pisania.
    To jest najbardziej "personalny" zbiór danych.
    """
    ACTIVITY_COLLECTION = "github_activity"
    ingested = 0
    try:
        # Issue comments użytkownika we własnych repo
        for repo in repos[:10]:
            try:
                for issue in repo.get_issues(state="all")[:20]:
                    try:
                        # Treść issue (jeśli autor to użytkownik)
                        if issue.user.login == user.login:
                            content = f"Issue #{issue.number}: {issue.title}\n\n{issue.body or ''}"
                            if len(content) > 100:
                                meta = {
                                    "type": "issue",
                                    "repo": repo.full_name,
                                    "issue_number": issue.number,
                                    "title": issue.title,
                                }
                                await rag.add_chunks(ACTIVITY_COLLECTION, [content[:2000]], [meta])
                                ingested += 1

                        # Komentarze użytkownika
                        for comment in issue.get_comments():
                            if comment.user.login == user.login and comment.body:
                                meta = {
                                    "type": "issue_comment",
                                    "repo": repo.full_name,
                                    "issue_number": issue.number,
                                }
                                await rag.add_chunks(ACTIVITY_COLLECTION, [comment.body[:1000]], [meta])
                                ingested += 1
                    except Exception:
                        continue
            except Exception:
                continue

        log(f"  Activity: +{ingested} komentarzy/issues")
    except Exception as e:
        log(f"  Activity błąd: {e}")
    return ingested


async def _seed_topics_from_repos(repos: List, log):
    """Dodaj języki i tematy z repo do topic trackera."""
    from app.services.topic_tracker_service import add_topic

    lang_counts: dict = {}
    for repo in repos:
        if repo.language:
            lang_counts[repo.language] = lang_counts.get(repo.language, 0) + 1
        # Tematy z opisu repo
        if repo.description:
            # Proste wyciąganie słów kluczowych z opisu
            words = repo.description.lower().split()
            for word in words:
                if len(word) > 5 and word.isalpha():
                    add_topic(word, source="repo_description", crawl_hours=72)

    # Języki jako tematy
    for lang, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        add_topic(lang.lower(), source="github_language", crawl_hours=48)

    log(f"  Dodano tematy z {len(repos)} repo do topic trackera")


async def _update_user_profile(user, repos: List):
    """Aktualizuje profil użytkownika na podstawie danych GitHub."""
    from app.services.memory_service import memory

    # Statystyki języków
    lang_counts: dict = {}
    for repo in repos:
        if repo.language:
            lang_counts[repo.language] = lang_counts.get(repo.language, 0) + 1

    top_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    profile = {
        "name": user.name or user.login,
        "github_login": user.login,
        "languages": [lang for lang, _ in top_langs],
        "total_repos": len(repos),
        "bio": user.bio or "",
        "location": user.location or "",
        "last_updated": datetime.utcnow().isoformat(),
    }

    memory.update_profile(profile)


def get_sync_status() -> dict:
    state = _load_state()
    current = _sync_status.copy()
    if state and not current.get("last_run"):
        current["last_run"] = state.get("last_run")
    return current


def get_user_repos() -> List[dict]:
    """Pobiera listę repo bez ingestii (szybki podgląd)."""
    if not settings.github_token:
        return []
    try:
        gh = Github(settings.github_token)
        user = gh.get_user()
        repos = []
        for repo in user.get_repos(type="owner"):
            repos.append({
                "full_name": repo.full_name,
                "description": repo.description or "",
                "language": repo.language or "",
                "stars": repo.stargazers_count,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else "",
                "fork": repo.fork,
                "private": repo.private,
            })
        return repos
    except Exception as e:
        logger.error(f"get_user_repos error: {e}")
        return []
