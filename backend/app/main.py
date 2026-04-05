from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import github, knowledge, models, training

app = FastAPI(
    title="Free Local LLM – Backend API",
    description="Backend dla lokalnego centrum AI: RAG, ingestia GitHub, fine-tuning",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(github.router, prefix="/api/github", tags=["GitHub"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Wiedza"])
app.include_router(models.router, prefix="/api/models", tags=["Modele"])
app.include_router(training.router, prefix="/api/training", tags=["Fine-tuning"])


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "Free Local LLM Backend"}
