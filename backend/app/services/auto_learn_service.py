"""
Auto-Learn Service — serce systemu ciągłego uczenia.

Filozofia:
- Model uczy się RAZ na repo (nie szuka za każdym razem).
- Gdy pojawia się nowe repo → automatycznie re-uczy się.
- Dodatkowe dane: Wikipedia (za darmo, bez klucza API).
- Wynik: JSONL dataset gotowy do LoRA fine-tuningu.
- Bez GPU: wiedza trafia do ChromaDB (RAG z "wyuczoną" bazą).
- Z GPU: automatyczny trening LoRA → rejestracja modelu w Ollama.

Pipeline:
  1. detect_new_repos()      – wykrywa nowe/zmienione repo na GitHub
  2. learn_from_repos()      – ingestion kodu → ChromaDB + budowanie datasetu
  3. enrich_with_wikipedia() – Wikipedia API na tematy z repo (za darmo)
  4. build_training_dataset() – generuje JSONL z Q&A par
  5. trigger_lora_if_gpu()   – uruchamia trening jeśli GPU dostępne
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

LEARN_STATE_FILE = Path(settings.data_dir) / "learn_state.json"
WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php"

# Stan uczenia (in-memory + plik)
_learn_state: Dict = {
    "running": False,
    "last_learn": None,
    "learned_repos": [],       # repo, na których model już się uczył
    "pending_repos": [],       # nowe repo czekające na uczenie
    "wiki_topics_learned": [], # tematy z Wikipedii już zaingestionowane
    "total_samples": 0,        # łączna liczba par Q&A w datasecie
    "last_dataset": None,      # ścieżka do ostatniego datasetu JSONL
    "gpu_training_done": False, # czy LoRA trening był uruchomiony
    "log": [],
}


def _load_state() -> dict:
    if LEARN_STATE_FILE.exists():
        try:
            data = json.loads(LEARN_STATE_FILE.read_text())
            _learn_state.update(data)
            return data
        except Exception:
            pass
    return {}


def _save_state():
    LEARN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEARN_STATE_FILE.write_text(json.dumps(_learn_state, indent=2, ensure_ascii=False, default=str))


def _log(msg: str):
    logger.info(f"[AutoLearn] {msg}")
    _learn_state["log"].append(f"{datetime.utcnow().strftime('%H:%M:%S')} {msg}")
    if len(_learn_state["log"]) > 300:
        _learn_state["log"] = _learn_state["log"][-150:]


def get_learn_status() -> dict:
    """Zwróć aktualny stan uczenia."""
    _load_state()
    return dict(_learn_state)


def mark_repos_for_learning(repo_names: List[str]):
    """
    Oznacz repo jako wymagające uczenia.
    Wywoływane przez sync_service po każdym syncu.
    """
    _load_state()
    known = set(_learn_state.get("learned_repos", []))
    pending = set(_learn_state.get("pending_repos", []))
    new_repos = [r for r in repo_names if r not in known]
    if new_repos:
        pending.update(new_repos)
        _learn_state["pending_repos"] = list(pending)
        _save_state()
        _log(f"Oznaczono {len(new_repos)} nowych repo do uczenia: {new_repos[:5]}")
    return new_repos


async def fetch_wikipedia_summary(topic: str) -> Optional[str]:
    """
    Pobierz streszczenie artykułu z Wikipedii (darmowe, bez klucza API).
    Używa REST API Wikipedii.
    """
    try:
        # Wyszukaj artykuł
        async with httpx.AsyncClient(timeout=10.0) as client:
            search_resp = await client.get(
                WIKIPEDIA_SEARCH,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": topic,
                    "format": "json",
                    "srlimit": 1,
                },
            )
            data = search_resp.json()
            results = data.get("query", {}).get("search", [])
            if not results:
                return None

            title = results[0]["title"]

            # Pobierz pełne streszczenie
            summary_resp = await client.get(
                WIKIPEDIA_API.format(title=title.replace(" ", "_")),
                headers={"Accept": "application/json"},
            )
            if summary_resp.status_code == 200:
                summary_data = summary_resp.json()
                extract = summary_data.get("extract", "")
                if extract and len(extract) > 100:
                    return f"# {title}\n\n{extract}"
    except Exception as e:
        logger.debug(f"Wikipedia fetch błąd dla '{topic}': {e}")
    return None


async def enrich_with_wikipedia(topics: List[str]) -> int:
    """
    Zaingestionuj artykuły Wikipedii na podane tematy do ChromaDB.
    Darmowe, bez klucza API — tylko publiczne API Wikipedii.
    """
    from app.services.rag_service import rag

    WIKI_COLLECTION = "wiki_knowledge"
    ingested = 0
    already_learned = set(_learn_state.get("wiki_topics_learned", []))

    for topic in topics:
        if topic.lower() in already_learned:
            continue
        try:
            content = await fetch_wikipedia_summary(topic)
            if content:
                chunks = [content[i : i + 1500] for i in range(0, min(len(content), 6000), 1500)]
                metas = [{"type": "wikipedia", "topic": topic, "source": "wikipedia.org"} for _ in chunks]
                added = await rag.add_chunks(WIKI_COLLECTION, chunks, metas)
                if added > 0:
                    ingested += 1
                    already_learned.add(topic.lower())
                    _log(f"Wikipedia: zaingestionowano '{topic}' ({len(chunks)} fragmentów)")
        except Exception as e:
            logger.debug(f"Wikipedia ingestion błąd '{topic}': {e}")
        await asyncio.sleep(0.5)  # Szanuj rate limit Wikipedii

    _learn_state["wiki_topics_learned"] = list(already_learned)
    return ingested


def _extract_topics_from_repos(repo_names: List[str]) -> List[str]:
    """
    Wyodrębnij tematy z nazw repo (języki, frameworki, biblioteki).
    Używane do wyszukiwania na Wikipedii.
    """
    topics = set()
    tech_keywords = {
        "python", "javascript", "typescript", "java", "go", "rust", "ruby",
        "react", "vue", "angular", "fastapi", "django", "flask", "express",
        "docker", "kubernetes", "terraform", "ansible", "nginx", "redis",
        "postgresql", "mongodb", "mysql", "graphql", "rest", "api",
        "machine learning", "deep learning", "neural network", "llm",
        "pytorch", "tensorflow", "transformers", "bert", "gpt",
        "linux", "git", "ci/cd", "devops", "microservices",
    }
    for repo_name in repo_names:
        # Rozbij nazwę repo na słowa
        words = repo_name.replace("-", " ").replace("_", " ").replace("/", " ").lower().split()
        for word in words:
            if word in tech_keywords or len(word) > 4:
                topics.add(word)

    # Zawsze dodaj ogólne tematy programistyczne
    topics.update(["software engineering", "programming", "algorithms"])
    return list(topics)[:20]  # max 20 tematów na raz


async def build_training_dataset(
    collection_names: List[str],
    output_name: str = "auto_dataset",
    max_samples: int = 3000,
) -> Optional[str]:
    """
    Zbuduj dataset JSONL z danych w ChromaDB.
    Generuje pary Q&A używając lokalnego modelu Ollama (darmowe, lokalne).
    Zwraca ścieżkę do pliku JSONL lub None w przypadku błędu.
    """
    from app.services.rag_service import _parse_chroma_host_port
    from app.services.ollama_client import ollama
    import chromadb

    try:
        output_dir = Path(settings.training_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{output_name}.jsonl"

        host, port = _parse_chroma_host_port(settings.chroma_url)
        client = chromadb.HttpClient(host=host, port=port)

        all_docs = []
        for col_name in collection_names:
            try:
                col = client.get_or_create_collection(col_name)
                total = col.count()
                if total == 0:
                    continue
                batch_size = 100
                offset = 0
                while offset < min(total, max_samples // len(collection_names)):
                    result = col.get(
                        limit=batch_size,
                        offset=offset,
                        include=["documents", "metadatas"],
                    )
                    for doc, meta in zip(result["documents"], result["metadatas"]):
                        if doc and len(doc.strip()) > 50:
                            all_docs.append((doc, meta, col_name))
                    offset += batch_size
            except Exception as e:
                logger.debug(f"Błąd pobierania kolekcji {col_name}: {e}")

        if not all_docs:
            _log("Brak danych do budowania datasetu")
            return None

        _log(f"Budowanie datasetu z {len(all_docs)} fragmentów...")

        system_prompt = (
            "Jesteś ekspertem programowania. Na podstawie podanego fragmentu kodu/tekstu "
            "wygeneruj jedno konkretne pytanie i pełną odpowiedź w języku polskim. "
            "Format DOKŁADNIE:\nPYTANIE: <pytanie>\nODPOWIEDZ: <odpowiedź>"
        )

        pairs = []
        for i, (doc, meta, source_col) in enumerate(all_docs[:max_samples]):
            if i % 100 == 0 and i > 0:
                _log(f"  Dataset: {i}/{min(len(all_docs), max_samples)} par wygenerowanych")
            try:
                response = await ollama.generate(
                    settings.default_model,
                    f"Fragment z '{source_col}':\n{doc[:600]}",
                    system_prompt,
                )
                if "PYTANIE:" in response and "ODPOWIEDZ:" in response:
                    parts = response.split("ODPOWIEDZ:", 1)
                    question = parts[0].replace("PYTANIE:", "").strip()
                    answer = parts[1].strip()
                    if question and answer and len(answer) > 20:
                        pairs.append({
                            "instruction": question,
                            "input": "",
                            "output": answer,
                            "source": meta.get("repo", meta.get("path", source_col)),
                        })
            except Exception:
                continue

        if not pairs:
            _log("Nie wygenerowano żadnych par Q&A")
            return None

        with open(out_file, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

        _log(f"Dataset zapisany: {out_file} ({len(pairs)} par)")
        _learn_state["total_samples"] = len(pairs)
        _learn_state["last_dataset"] = str(out_file)
        return str(out_file)

    except Exception as e:
        _log(f"Błąd budowania datasetu: {e}")
        return None


def _check_gpu_available() -> bool:
    """Sprawdź czy GPU jest dostępne (CUDA)."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        pass
    # Fallback: sprawdź czy nvidia-smi jest dostępne
    result = os.popen("nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null").read()
    return bool(result.strip())


async def trigger_lora_training(dataset_path: str) -> bool:
    """
    Uruchom LoRA trening jeśli GPU jest dostępne.
    Trening przebiega asynchronicznie w tle.
    """
    if not _check_gpu_available():
        _log("GPU niedostępne — trening LoRA pominięty. Używam wiedzy z ChromaDB.")
        return False

    script = Path("/app/scripts/run_lora.py")
    if not script.exists():
        _log("Skrypt run_lora.py nie znaleziony — pomiń trening")
        return False

    try:
        _log(f"Uruchamiam trening LoRA na GPU... (dataset: {dataset_path})")
        proc = await asyncio.create_subprocess_exec(
            "python", str(script),
            "--dataset", dataset_path,
            "--model", settings.default_model,
            "--output", str(Path(settings.training_output_dir) / "finetuned"),
            "--epochs", "3",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3600 * 4)
        if proc.returncode == 0:
            _log("Trening LoRA zakończony sukcesem!")
            _learn_state["gpu_training_done"] = True
            return True
        else:
            _log(f"Trening LoRA błąd: {stderr.decode()[:300]}")
            return False
    except asyncio.TimeoutError:
        _log("Trening LoRA przekroczył limit czasu")
        return False
    except Exception as e:
        _log(f"Błąd uruchamiania treningu: {e}")
        return False


async def learn_from_new_repos() -> dict:
    """
    Główna funkcja uczenia — uruchamiana automatycznie po syncu GitHub
    i przez scheduler gdy wykryto nowe repo.

    Pipeline:
    1. Pobierz pending_repos (nowe repo od ostatniego uczenia)
    2. Wyodrębnij tematy → Wikipedia
    3. Zbuduj dataset JSONL ze WSZYSTKICH danych
    4. Opcjonalnie: LoRA trening jeśli GPU
    """
    _load_state()

    if _learn_state["running"]:
        return {"status": "already_running"}

    pending = _learn_state.get("pending_repos", [])
    if not pending:
        return {"status": "no_new_repos"}

    _learn_state["running"] = True
    _learn_state["last_learn"] = datetime.utcnow().isoformat()
    _save_state()

    try:
        _log(f"=== Start uczenia na {len(pending)} nowych repo ===")

        # 1. Wyodrębnij tematy z nazw repo → Wikipedia
        topics = _extract_topics_from_repos(pending)
        _log(f"Tematy do Wikipedii: {topics[:5]}...")
        wiki_count = await enrich_with_wikipedia(topics)
        _log(f"Wikipedia: zaingestionowano {wiki_count} artykułów")

        # 2. Zbierz wszystkie kolekcje ChromaDB (każde repo = osobna kolekcja)
        from app.services.rag_service import _parse_chroma_host_port
        import chromadb

        host, port = _parse_chroma_host_port(settings.chroma_url)
        chroma_client = chromadb.HttpClient(host=host, port=port)
        all_collections = [c.name for c in chroma_client.list_collections()]
        _log(f"Dostępne kolekcje ChromaDB: {len(all_collections)}")

        # 3. Zbuduj dataset z WSZYSTKICH dostępnych danych
        if all_collections:
            dataset_path = await build_training_dataset(
                collection_names=all_collections,
                output_name=f"dataset_{datetime.utcnow().strftime('%Y%m%d_%H%M')}",
                max_samples=3000,
            )
        else:
            dataset_path = None
            _log("Brak kolekcji ChromaDB — pomiń budowanie datasetu")

        # 4. Przenieś pending → learned
        learned = set(_learn_state.get("learned_repos", []))
        learned.update(pending)
        _learn_state["learned_repos"] = list(learned)
        _learn_state["pending_repos"] = []

        # 5. Opcjonalnie: LoRA trening jeśli GPU i dataset gotowy
        gpu_trained = False
        if dataset_path:
            gpu_trained = await trigger_lora_training(dataset_path)

        result = {
            "status": "done",
            "repos_learned": len(pending),
            "wiki_articles": wiki_count,
            "dataset_path": dataset_path,
            "gpu_trained": gpu_trained,
            "total_samples": _learn_state.get("total_samples", 0),
        }
        _log(f"=== Uczenie zakończone: {result} ===")
        return result

    except Exception as e:
        _log(f"Błąd uczenia: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        _learn_state["running"] = False
        _save_state()


async def check_and_learn():
    """
    Wywoływane przez scheduler co godzinę.
    Sprawdza czy są nowe repo do nauczenia i uruchamia pipeline.
    """
    _load_state()
    pending = _learn_state.get("pending_repos", [])
    if pending:
        _log(f"Scheduler: wykryto {len(pending)} repo do uczenia, startuję...")
        await learn_from_new_repos()
    else:
        logger.debug("[AutoLearn] Scheduler: brak nowych repo do uczenia")


# Załaduj stan przy imporcie modułu
_load_state()
