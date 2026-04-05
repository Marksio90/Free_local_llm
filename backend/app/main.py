import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import github, knowledge, models, training, chat, memory, sync
from app.core.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_scheduler()
    logger.info("Backend uruchomiony")
    yield
    # Shutdown
    stop_scheduler()
    logger.info("Backend zatrzymany")


app = FastAPI(
    title="Free Local LLM – Backend API",
    description=(
        "Lokalny system AI z pamięcią personalną, RAG na repozytoriach GitHub, "
        "auto-sync i pipeline fine-tuningu."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Oryginalne routes ──────────────────────────────────────────────────────────
app.include_router(github.router,   prefix="/api/github",   tags=["GitHub"])
app.include_router(knowledge.router,prefix="/api/knowledge",tags=["Wiedza"])
app.include_router(models.router,   prefix="/api/models",   tags=["Modele"])
app.include_router(training.router, prefix="/api/training", tags=["Fine-tuning"])

# ── Nowe routes ────────────────────────────────────────────────────────────────
app.include_router(chat.router,   prefix="/api/chat",   tags=["Chat z RAG"])
app.include_router(memory.router, prefix="/api/memory", tags=["Pamięć"])
app.include_router(sync.router,   prefix="/api/sync",   tags=["Auto-Sync GitHub"])


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": "2.0.0", "service": "Free Local LLM Backend"}
