import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.rag_service import rag

router = APIRouter()

_jobs: dict = {}


class DatasetRequest(BaseModel):
    collection_name: str
    output_name: str = "dataset"
    max_samples: int = 5000
    model: str = ""  # model do generowania par Q&A


class LoraConfig(BaseModel):
    base_model: str = "qwen3:4b"
    dataset_file: str = "dataset.jsonl"
    output_name: str = "my-model"
    epochs: int = 3
    learning_rate: float = 2e-4
    batch_size: int = 4
    rank: int = 16


async def _build_dataset_job(job_id: str, req: DatasetRequest):
    _jobs[job_id] = {"status": "running", "step": "Pobieranie fragmentów z ChromaDB"}
    try:
        output_dir = Path(settings.training_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Pobierz wszystkie dokumenty z kolekcji
        from app.services.rag_service import _parse_chroma_host_port
        import chromadb

        host, port = _parse_chroma_host_port(settings.chroma_url)
        client = chromadb.HttpClient(host=host, port=port)
        collection = client.get_or_create_collection(req.collection_name)
        total = collection.count()

        if total == 0:
            _jobs[job_id] = {"status": "error", "error": "Kolekcja jest pusta"}
            return

        _jobs[job_id]["step"] = f"Pobrano {total} fragmentów, generuję pary Q&A"

        # Pobierz dokumenty partiami
        batch_size = 100
        all_docs = []
        offset = 0
        while offset < min(total, req.max_samples * 2):
            result = collection.get(
                limit=batch_size,
                offset=offset,
                include=["documents", "metadatas"],
            )
            all_docs.extend(zip(result["documents"], result["metadatas"]))
            offset += batch_size

        # Generuj pary instrukcja → odpowiedź
        use_model = req.model or settings.default_model
        pairs = []
        from app.services.ollama_client import ollama

        system_prompt = (
            "Jesteś ekspertem w analizie kodu i dokumentacji. "
            "Na podstawie poniższego fragmentu kodu/tekstu wygeneruj jedno pytanie "
            "i pełną, pomocną odpowiedź. Format:\n"
            "PYTANIE: ...\nODPOWIEDZ: ..."
        )

        for i, (doc, meta) in enumerate(all_docs[: req.max_samples]):
            if i % 50 == 0:
                _jobs[job_id]["step"] = f"Przetwarzam fragment {i}/{min(len(all_docs), req.max_samples)}"
            try:
                response = await ollama.generate(
                    use_model,
                    f"Fragment:\n{doc[:800]}",
                    system_prompt,
                )
                if "PYTANIE:" in response and "ODPOWIEDZ:" in response:
                    parts = response.split("ODPOWIEDZ:", 1)
                    question = parts[0].replace("PYTANIE:", "").strip()
                    answer = parts[1].strip()
                    pairs.append(
                        {
                            "instruction": question,
                            "input": "",
                            "output": answer,
                            "source": meta.get("path", "unknown"),
                        }
                    )
            except Exception:
                continue

        # Zapisz jako JSONL (format Alpaca)
        out_file = output_dir / f"{req.output_name}.jsonl"
        with open(out_file, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

        _jobs[job_id] = {
            "status": "done",
            "pairs_generated": len(pairs),
            "file": str(out_file),
        }
    except Exception as exc:
        _jobs[job_id] = {"status": "error", "error": str(exc)}


@router.post("/dataset/build")
async def build_dataset(req: DatasetRequest, background: BackgroundTasks):
    """
    Buduje dataset treningowy (JSONL) z danych w bazie wektorowej.
    Używa modelu do generowania par pytanie-odpowiedź ze fragmentów kodu.
    """
    job_id = f"dataset_{len(_jobs) + 1}"
    background.add_task(_build_dataset_job, job_id, req)
    return {"job_id": job_id, "status": "queued"}


@router.get("/datasets")
async def list_datasets():
    """Lista plików JSONL gotowych do treningu."""
    output_dir = Path(settings.training_output_dir)
    if not output_dir.exists():
        return []
    files = []
    for f in output_dir.glob("*.jsonl"):
        size = f.stat().st_size
        lines = sum(1 for _ in open(f, encoding="utf-8"))
        files.append({"name": f.name, "path": str(f), "size_kb": round(size / 1024, 1), "samples": lines})
    return files


@router.get("/jobs/{job_id}")
async def training_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "Nie znaleziono zadania")
    return _jobs[job_id]


@router.get("/jobs")
async def list_training_jobs():
    return list(_jobs.values())


@router.get("/instructions")
async def fine_tuning_instructions():
    """Instrukcja uruchomienia fine-tuningu (LoRA z Unsloth)."""
    return {
        "info": "Fine-tuning z GPU wymaga uruchomienia osobnego kontenera",
        "steps": [
            "1. Upewnij się, że masz GPU i nvidia-container-toolkit",
            "2. Uruchom: docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trainer",
            "3. Wewnątrz kontenera: python /app/scripts/run_lora.py --dataset dataset.jsonl --model qwen3:4b",
            "4. Po treningu: python /app/scripts/export_gguf.py --model output/ --name my-model",
            "5. Zarejestruj w Ollama: ollama create my-model -f /app/output/Modelfile",
        ],
        "without_gpu": "Bez GPU możesz używać RAG (baza wektorowa) zamiast fine-tuningu – to praktyczniejsze podejście dla CPU.",
    }
