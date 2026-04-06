import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import github, knowledge, models, training, chat, memory, sync, intel
from app.core.config import settings
from app.core.scheduler import start_scheduler, stop_scheduler, add_intel_crawl_job, add_sync_job

logger = logging.getLogger(__name__)


async def _auto_startup():
    """
    Zadania uruchamiane w tle przy starcie:
    1. Upewnij się, że model embeddingów jest pobrany
    2. Jeśli GITHUB_TOKEN ustawiony → auto-sync GitHub
    3. Zaplanuj periodyczne zadania
    """
    await asyncio.sleep(5)  # Daj czas Ollama na pełny start

    # 1. Pull embed model jeśli nie ma
    try:
        from app.services.ollama_client import ollama
        pulled_models = await ollama.list_models()
        names = [m.get("name", "") for m in pulled_models]
        if not any(settings.embed_model in n for n in names):
            logger.info(f"Auto-pull: pobieranie modelu embeddingów '{settings.embed_model}'...")
            async for line in ollama.pull_model(settings.embed_model):
                pass  # consume stream
            logger.info(f"Model embeddingów '{settings.embed_model}' pobrany.")
    except Exception as e:
        logger.warning(f"Auto-pull embed model: {e}")

    # 2. Auto-sync GitHub jeśli token dostępny
    if settings.github_token:
        try:
            logger.info("GitHub token wykryty – uruchamiam auto-sync przy starcie...")
            from app.services.sync_service import sync_all_repos
            result = await sync_all_repos(include_stars=True)
            logger.info(
                f"Auto-sync GitHub zakończony: {result.get('repos_synced', 0)} repo, "
                f"{result.get('chunks_added', 0)} fragmentów → ChromaDB"
            )
        except Exception as e:
            logger.warning(f"Auto-sync GitHub przy starcie: {e}")
    else:
        logger.info("Brak GITHUB_TOKEN – pomiń auto-sync. Ustaw token w .env aby aktywować.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────
    start_scheduler()

    # Zaplanuj web intel crawl co 12h
    from app.services.topic_tracker_service import crawl_all_due_topics
    add_intel_crawl_job(crawl_all_due_topics, hours=12)

    # Zaplanuj GitHub sync co 24h
    if settings.github_token:
        from app.services.sync_service import sync_all_repos
        add_sync_job(sync_all_repos, hours=24)

    # Uruchom zadania startowe w tle (nie blokują API)
    asyncio.create_task(_auto_startup())

    logger.info("Backend v3.0 gotowy – Personal AI uruchomiony")
    yield

    # ── Shutdown ─────────────────────────────────
    stop_scheduler()


app = FastAPI(
    title="Free Local LLM – Backend API",
    description=(
        "Lokalny Personal AI: pamięć konwersacji, RAG na GitHub, "
        "Web Intelligence (DuckDuckGo + Wikipedia + RSS), auto-sync, fine-tuning."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(github.router,   prefix="/api/github",   tags=["GitHub"])
app.include_router(knowledge.router,prefix="/api/knowledge",tags=["Wiedza"])
app.include_router(models.router,   prefix="/api/models",   tags=["Modele"])
app.include_router(training.router, prefix="/api/training", tags=["Fine-tuning"])
app.include_router(chat.router,     prefix="/api/chat",     tags=["Chat z RAG"])
app.include_router(memory.router,   prefix="/api/memory",   tags=["Pamięć"])
app.include_router(sync.router,     prefix="/api/sync",     tags=["Auto-Sync GitHub"])
app.include_router(intel.router,    prefix="/api/intel",    tags=["Web Intelligence"])


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": "3.0.0", "service": "Free Local LLM Backend"}
