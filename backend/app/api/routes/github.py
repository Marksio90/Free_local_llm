import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.services import github_service
from app.services.rag_service import rag

router = APIRouter()

# Prosty in-memory status zadań (w produkcji: Redis/baza)
_jobs: dict = {}


class IngestRequest(BaseModel):
    repo_url: str
    collection_name: str = ""


class SearchRequest(BaseModel):
    query: str
    collection_name: str
    n_results: int = 5


def _collection_name(repo_url: str) -> str:
    clean = repo_url.rstrip("/").replace(".git", "").replace("https://github.com/", "")
    return clean.replace("/", "__").replace("-", "_")


async def _ingest_job(job_id: str, repo_url: str, collection: str):
    _jobs[job_id] = {"status": "running", "repo": repo_url, "ingested": 0, "error": None}
    try:
        repo_path = github_service.clone_or_update(repo_url)
        files = github_service.extract_files(repo_path)
        _jobs[job_id]["total_files"] = len(files)

        total_chunks = 0
        for f in files:
            chunks, metas = github_service.chunk_file(f)
            added = await rag.add_chunks(collection, chunks, metas)
            total_chunks += added

        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["ingested"] = total_chunks
    except Exception as exc:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(exc)


@router.post("/ingest")
async def ingest_repo(req: IngestRequest, background: BackgroundTasks):
    """Klonuje repo GitHub i wgrywa zawartość do bazy wektorowej."""
    if not req.repo_url.startswith("https://github.com/"):
        raise HTTPException(400, "Tylko repozytoria github.com są obsługiwane (HTTPS URL)")
    collection = req.collection_name or _collection_name(req.repo_url)
    job_id = f"ingest_{uuid.uuid4().hex[:8]}"
    background.add_task(_ingest_job, job_id, req.repo_url, collection)
    return {"job_id": job_id, "collection": collection, "status": "queued"}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    """Status zadania ingestii."""
    if job_id not in _jobs:
        raise HTTPException(404, "Nie znaleziono zadania")
    return _jobs[job_id]


@router.get("/jobs")
async def list_jobs():
    return list(_jobs.values())


@router.post("/search")
async def search_knowledge(req: SearchRequest):
    """Wyszukaj fragmenty kodu/tekstu z zaingestionowanych repozytoriów."""
    results = await rag.search(req.collection_name, req.query, req.n_results)
    return {"results": results, "total": len(results)}
