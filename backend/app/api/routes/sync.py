"""
Zarządzanie auto-sync GitHub.
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.services.sync_service import sync_all_repos, get_sync_status, get_user_repos
from app.core.scheduler import scheduler, add_sync_job
from app.core.config import settings

router = APIRouter()


class SyncRequest(BaseModel):
    include_forks: bool = False
    include_stars: bool = False


class ScheduleRequest(BaseModel):
    enabled: bool = True
    interval_hours: int = 24


@router.post("/trigger")
async def trigger_sync(req: SyncRequest, background: BackgroundTasks):
    """
    Uruchom sync wszystkich repo z GitHub.
    Wymaga GITHUB_TOKEN w .env
    """
    if not settings.github_token:
        return {
            "status": "error",
            "error": "Brak GITHUB_TOKEN w .env – ustaw token i zrestartuj backend",
        }

    background.add_task(sync_all_repos, req.include_forks, req.include_stars)
    return {"status": "queued", "message": "Sync uruchomiony w tle"}


@router.get("/status")
async def sync_status():
    """Status ostatniego/bieżącego sync."""
    return get_sync_status()


@router.get("/repos")
async def list_repos():
    """Lista repozytoriów z GitHub (bez ingestii)."""
    if not settings.github_token:
        return {"repos": [], "error": "Brak GITHUB_TOKEN"}
    repos = get_user_repos()
    return {"repos": repos, "total": len(repos)}


@router.post("/schedule")
async def configure_schedule(req: ScheduleRequest):
    """Konfiguruj auto-sync."""
    if req.enabled:
        add_sync_job(
            lambda: sync_all_repos(include_forks=False, include_stars=False),
            hours=req.interval_hours,
        )
        return {"status": "scheduled", "interval_hours": req.interval_hours}
    else:
        try:
            scheduler.remove_job("auto_sync")
        except Exception:
            pass
        return {"status": "disabled"}


@router.get("/schedule")
async def get_schedule():
    """Status harmonogramu."""
    job = scheduler.get_job("auto_sync")
    if job:
        return {
            "enabled": True,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        }
    return {"enabled": False, "next_run": None}
