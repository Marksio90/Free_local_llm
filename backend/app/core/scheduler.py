"""
Globalny scheduler dla background jobów:
- auto-sync repo GitHub co 24h
- auto-generowanie datasetu po ingestii
- auto-trigger fine-tuningu gdy zebrano N próbek
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler uruchomiony")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler zatrzymany")


def add_sync_job(func, hours: int = 24):
    """Dodaj zadanie auto-sync."""
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(hours=hours),
        id="auto_sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"Auto-sync zaplanowany co {hours}h")


def add_training_check_job(func, hours: int = 6):
    """Sprawdzaj czy jest wystarczająco danych do treningu."""
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(hours=hours),
        id="training_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"Sprawdzanie treningu zaplanowane co {hours}h")


def add_intel_crawl_job(func, hours: int = 12):
    """Crawler web intelligence — co 12h zbiera nową wiedzę."""
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(hours=hours),
        id="intel_crawl",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"Web intel crawler zaplanowany co {hours}h")
