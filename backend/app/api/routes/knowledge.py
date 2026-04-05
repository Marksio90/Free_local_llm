from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
import aiofiles
from pathlib import Path

from app.core.config import settings
from app.services.rag_service import rag
from app.services.github_service import chunk_file

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    collection_name: str = "documents"
    n_results: int = 5


class AddTextRequest(BaseModel):
    text: str
    source: str = "manual"
    collection_name: str = "documents"


@router.get("/collections")
async def list_collections():
    """Lista wszystkich kolekcji wiedzy."""
    return rag.list_collections()


@router.get("/collections/{name}")
async def collection_info(name: str):
    return rag.collection_stats(name)


@router.delete("/collections/{name}")
async def delete_collection(name: str):
    ok = rag.delete_collection(name)
    if not ok:
        raise HTTPException(404, f"Kolekcja '{name}' nie istnieje")
    return {"deleted": name}


@router.post("/search")
async def search(req: SearchRequest):
    """Wyszukiwanie semantyczne w bazie wiedzy."""
    results = await rag.search(req.collection_name, req.query, req.n_results)
    return {"results": results}


@router.post("/add-text")
async def add_text(req: AddTextRequest):
    """Dodaj fragment tekstu do bazy wiedzy."""
    file_info = {"path": req.source, "content": req.text, "extension": ".txt"}
    chunks, metas = chunk_file(file_info)
    added = await rag.add_chunks(req.collection_name, chunks, metas)
    return {"added": added, "total_chunks": len(chunks)}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection_name: str = "documents",
):
    """Wgraj dokument tekstowy do bazy wiedzy."""
    allowed = {".txt", ".md", ".py", ".js", ".ts", ".yaml", ".yml", ".json", ".toml"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Nieobsługiwany typ pliku: {ext}")

    upload_dir = Path(settings.data_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename

    async with aiofiles.open(dest, "wb") as out:
        content = await file.read()
        await out.write(content)

    text = content.decode("utf-8", errors="ignore")
    file_info = {"path": file.filename, "content": text, "extension": ext}
    chunks, metas = chunk_file(file_info)
    added = await rag.add_chunks(collection_name, chunks, metas)

    return {"filename": file.filename, "chunks_added": added, "collection": collection_name}
