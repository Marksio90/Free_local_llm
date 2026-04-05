from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.ollama_client import ollama

router = APIRouter()


class PullRequest(BaseModel):
    model_name: str


class GenerateRequest(BaseModel):
    model: str
    prompt: str
    system: str = ""


@router.get("/")
async def list_models():
    """Lista zainstalowanych modeli."""
    models = await ollama.list_models()
    return {"models": models}


@router.get("/{model_name}/info")
async def model_info(model_name: str):
    """Szczegóły modelu."""
    try:
        info = await ollama.model_info(model_name)
        return info
    except Exception:
        raise HTTPException(404, f"Model '{model_name}' nie istnieje")


@router.post("/pull")
async def pull_model(req: PullRequest):
    """Pobierz model z Ollama Hub (streaming progress)."""
    async def _stream():
        async for line in ollama.pull_model(req.model_name):
            yield line + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@router.delete("/{model_name}")
async def delete_model(model_name: str):
    ok = await ollama.delete_model(model_name)
    if not ok:
        raise HTTPException(404, f"Nie można usunąć modelu '{model_name}'")
    return {"deleted": model_name}


@router.post("/generate")
async def generate(req: GenerateRequest):
    """Wygeneruj odpowiedź z podanego modelu."""
    try:
        response = await ollama.generate(req.model, req.prompt, req.system)
        return {"response": response}
    except Exception as exc:
        raise HTTPException(500, str(exc))
