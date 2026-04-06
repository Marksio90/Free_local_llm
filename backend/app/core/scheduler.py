"""
Globalny scheduler dla background jobów:
- auto-sync repo GitHub co 24h
- auto-uczenie (learning) na nowych repo — co 1h sprawdzenie
- auto-generowanie datasetu po ingestii
- web intel crawl co 12h
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
    """Dodaj zadanie auto-sync GitHub co 24h."""
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(hours=hours),
        id="auto_sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"Auto-sync GitHub zaplanowany co {hours}h")


def add_auto_learn_job(func, hours: int = 1):
    """
    Sprawdzaj nowe repo i uruchamiaj auto-uczenie co godzinę.
    Model uczy się RAZ na każdym repo — nowe repo → auto re-learn.
    """
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(hours=hours),
        id="auto_learn",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info(f"Auto-learn (ciągłe uczenie) zaplanowane co {hours}h")


def add_training_check_job(func, hours: int = 6):
    """Sprawdzaj czy jest wystarczająco danych do treningu LoRA."""
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(hours=hours),
        id="training_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"Sprawdzanie treningu zaplanowane co {hours}h")


def add_intel_crawl_job(func, hours: int = 12):
    """Crawler web intelligence — co 12h zbiera nową wiedzę z internetu."""
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(hours=hours),
        id="intel_crawl",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"Web intel crawler zaplanowany co {hours}h")
