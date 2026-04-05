import hashlib
from typing import List

import chromadb

from app.core.config import settings
from app.services.ollama_client import ollama


def _parse_chroma_host_port(url: str):
    url = url.replace("http://", "").replace("https://", "")
    parts = url.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 8000
    return host, port


class RAGService:
    def __init__(self):
        host, port = _parse_chroma_host_port(settings.chroma_url)
        self.client = chromadb.HttpClient(host=host, port=port)

    def _collection(self, name: str):
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    async def add_chunks(
        self,
        collection_name: str,
        chunks: List[str],
        metadatas: List[dict],
    ) -> int:
        collection = self._collection(collection_name)
        added = 0
        for chunk, meta in zip(chunks, metadatas):
            doc_id = hashlib.md5(chunk.encode()).hexdigest()
            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                continue
            embedding = await ollama.embed(chunk)
            collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[meta],
            )
            added += 1
        return added

    async def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
    ) -> List[dict]:
        collection = self._collection(collection_name)
        count = collection.count()
        if count == 0:
            return []
        query_embedding = await ollama.embed(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
        return [
            {"content": doc, "metadata": meta, "score": round(1 - dist, 4)}
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    def list_collections(self) -> List[dict]:
        cols = self.client.list_collections()
        return [{"name": c.name, "count": c.count()} for c in cols]

    def delete_collection(self, name: str) -> bool:
        try:
            self.client.delete_collection(name)
            return True
        except Exception:
            return False

    def collection_stats(self, name: str) -> dict:
        col = self._collection(name)
        return {"name": name, "count": col.count()}


rag = RAGService()
