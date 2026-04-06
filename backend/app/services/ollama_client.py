from typing import AsyncGenerator, List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class OllamaClient:
    def __init__(self):
        self.base_url = settings.ollama_url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def list_models(self) -> List[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            return r.json().get("models", [])

    # BUG FIX: @retry NIE działa z async generatorami (tenacity próbuje await na generatorze
    # co rzuca TypeError). Pull ma timeout=600s więc retry nie jest potrzebny.
    async def pull_model(self, model_name: str) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield line

    async def delete_model(self, model_name: str) -> bool:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(
                f"{self.base_url}/api/delete",
                json={"name": model_name},
            )
            return r.status_code == 200

    async def embed(self, text: str) -> List[float]:
        """Embeddingi przez nowe Ollama API /api/embed (Ollama 0.1.26+).
        Fallback do /api/embeddings dla starszych wersji."""
        async with httpx.AsyncClient(timeout=120) as client:
            # Nowe API (Ollama 0.1.26+): /api/embed z polem "input"
            r = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": settings.embed_model, "input": text},
            )
            if r.status_code == 200:
                data = r.json()
                # Nowe API zwraca {"embeddings": [[...]]}, stare {"embedding": [...]}
                if "embeddings" in data and data["embeddings"]:
                    return data["embeddings"][0]
                if "embedding" in data and data["embedding"]:
                    return data["embedding"]

            # Fallback do deprecated /api/embeddings
            r2 = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": settings.embed_model, "prompt": text},
            )
            r2.raise_for_status()
            result = r2.json()
            if "embedding" not in result or not result["embedding"]:
                raise ValueError(f"Ollama zwróciło pusty embedding dla modelu {settings.embed_model}")
            return result["embedding"]

    async def generate(self, model: str, prompt: str, system: str = "") -> str:
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self.base_url}/api/generate", json=payload)
            r.raise_for_status()
            return r.json()["response"]

    async def model_info(self, model_name: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base_url}/api/show",
                json={"name": model_name},
            )
            r.raise_for_status()
            return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def health(self) -> bool:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/api/tags")
            return r.status_code == 200


ollama = OllamaClient()
