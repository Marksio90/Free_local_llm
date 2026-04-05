# Free Local LLM

Prywatny, lokalny system AI – bez chmury, bez abonamentu, bez wysyłania danych.

## Architektura

```
┌─────────────────────────────────────────────────────┐
│                     Docker Compose                  │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Ollama  │  │ Open     │  │  Admin Panel     │  │
│  │  :11434  │  │ WebUI    │  │  React  :3001    │  │
│  │  (LLM)   │  │  :3000   │  └────────┬─────────┘  │
│  └────┬─────┘  └──────────┘           │             │
│       │                      ┌────────▼─────────┐   │
│       └──────────────────────► FastAPI  :8080   │   │
│                               │  (Backend API)  │   │
│                               └────────┬────────┘   │
│                                        │             │
│                               ┌────────▼────────┐   │
│                               │   ChromaDB      │   │
│                               │   :8001         │   │
│                               │  (Wektory RAG)  │   │
│                               └─────────────────┘   │
└─────────────────────────────────────────────────────┘
```

| Serwis | Port | Opis |
|---|---|---|
| Ollama | 11434 | Silnik modeli LLM |
| Open WebUI | 3000 | Interfejs czatu |
| Admin Panel | 3001 | Zarządzanie: modele, wiedza, trening |
| Backend API | 8080 | FastAPI + RAG + GitHub ingestia |
| ChromaDB | 8001 | Baza wektorowa (embeddingi) |

## Szybki start

```bash
# 1. Sklonuj repo
git clone https://github.com/marksio90/free_local_llm.git
cd free_local_llm

# 2. Uruchom instalator (Docker wymagany)
chmod +x install.sh
./install.sh
```

Po instalacji:
- **Czat**: http://localhost:3000
- **Panel admina**: http://localhost:3001
- **API Docs**: http://localhost:8080/docs

## Wymagania

| Komponent | Minimum | Rekomendowane |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Dysk | 20 GB | 50 GB |
| GPU (opcjonalny) | NVIDIA 8 GB VRAM | NVIDIA 16+ GB |
| Docker | 24+ | latest |

## Modele

```bash
# Domyślny (CPU-friendly)
docker exec llm-ollama ollama pull qwen3:4b

# Mocniejszy dialog
docker exec llm-ollama ollama pull qwen2.5:7b

# Kodowanie
docker exec llm-ollama ollama pull qwen2.5-coder:7b

# Wymagany do RAG (embeddingi)
docker exec llm-ollama ollama pull nomic-embed-text
```

## Własny asystent z Modelfile

```bash
# Asystent ogólny
docker exec llm-ollama ollama create asystent -f /path/to/models/Modelfile.assistant

# Asystent kodu
docker exec llm-ollama ollama create koder -f /path/to/models/Modelfile.coder
```

## RAG – Ingestia GitHub

Podłącz repozytoria GitHub do modelu – zyska kontekst ich kodu:

```bash
# Przez panel admina (http://localhost:3001 → GitHub)
# LUB przez API:

curl -X POST http://localhost:8080/api/github/ingest \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/owner/repo"}'

# Sprawdź status
curl http://localhost:8080/api/github/jobs
```

Repo zostaje sklonowane lokalnie, podzielone na fragmenty i zaindeksowane w ChromaDB.
Model korzysta z tych danych jako kontekstu RAG.

## Wgrywanie dokumentów

```bash
# Przez panel admina → Wiedza → Wgraj plik
# LUB przez API:

curl -X POST http://localhost:8080/api/knowledge/upload \
  -F "file=@moje-notatki.md" \
  -F "collection_name=dokumenty"
```

## Fine-tuning (GPU)

**Krok 1:** Zaingestionuj repozytoria (GitHub → panel admina)

**Krok 2:** Wygeneruj dataset Q&A z kodu:
```bash
curl -X POST http://localhost:8080/api/training/dataset/build \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "owner__repo", "output_name": "moj-dataset", "max_samples": 500}'
```

**Krok 3:** Uruchom trening LoRA (wymaga GPU NVIDIA):
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trainer \
  python scripts/run_lora.py \
    --dataset /app/output/moj-dataset.jsonl \
    --model qwen3:4b \
    --epochs 3
```

**Krok 4:** Eksportuj do GGUF i zarejestruj w Ollama:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trainer \
  python scripts/export_gguf.py \
    --model /app/output/finetuned/merged \
    --name moj-model
```

**Krok 5:** Użyj modelu:
```bash
docker exec llm-ollama ollama run moj-model
```

## GPU (NVIDIA)

```bash
# Zainstaluj nvidia-container-toolkit
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

# Uruchom z GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Konfiguracja (.env)

```env
DEFAULT_MODEL=qwen3:4b       # Model domyślny
EMBED_MODEL=nomic-embed-text  # Model do embeddingów
GITHUB_TOKEN=ghp_...          # Opcjonalny – do prywatnych repo
WEBUI_SECRET_KEY=zmien-mnie   # Klucz sesji WebUI
```

## Komendy

```bash
# Zatrzymaj wszystko
docker compose down

# Zatrzymaj i usuń dane (!)
docker compose down -v

# Logi
docker compose logs -f backend
docker compose logs -f ollama

# Restart jednego serwisu
docker compose restart backend

# Shell w kontenerze
docker exec -it llm-backend bash
docker exec -it llm-ollama bash
```

## API

Pełna dokumentacja Swagger: http://localhost:8080/docs

| Endpoint | Metoda | Opis |
|---|---|---|
| `/api/models/` | GET | Lista modeli |
| `/api/models/pull` | POST | Pobierz model |
| `/api/github/ingest` | POST | Zaingestionuj repo |
| `/api/github/search` | POST | Szukaj w repo |
| `/api/knowledge/collections` | GET | Lista kolekcji |
| `/api/knowledge/search` | POST | Wyszukaj semantycznie |
| `/api/knowledge/upload` | POST | Wgraj dokument |
| `/api/training/dataset/build` | POST | Generuj dataset |
| `/api/training/datasets` | GET | Lista datasetów |

## Struktura projektu

```
Free_local_llm/
├── docker-compose.yml          # Główny stos Docker
├── docker-compose.gpu.yml      # Nadpisanie GPU + serwis trenera
├── install.sh                  # Jednolinijkowy instalator
├── .env.example                # Szablon konfiguracji
│
├── backend/                    # FastAPI
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── core/config.py
│       ├── api/routes/
│       │   ├── github.py       # Ingestia repo GitHub
│       │   ├── knowledge.py    # Baza wiedzy CRUD
│       │   ├── models.py       # Zarządzanie modelami Ollama
│       │   └── training.py     # Generowanie datasetów
│       └── services/
│           ├── ollama_client.py
│           ├── rag_service.py  # ChromaDB + embeddingi
│           └── github_service.py
│
├── frontend/                   # React + Vite + Tailwind
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
│       ├── pages/              # Dashboard, Models, GitHub, Knowledge, Training
│       ├── components/Layout.tsx
│       └── api/client.ts
│
├── training/                   # Fine-tuning LoRA
│   ├── Dockerfile
│   ├── scripts/
│   │   ├── run_lora.py         # Trening LoRA/QLoRA
│   │   └── export_gguf.py      # Eksport GGUF → Ollama
│   └── configs/
│       └── lora_config.yaml    # Referencyjna konfiguracja
│
└── models/                     # Gotowe Modelfiles
    ├── Modelfile.assistant     # Personalny asystent
    └── Modelfile.coder         # Asystent kodu
```

## Ścieżka rozwoju

1. **Uruchom** – `./install.sh`, sprawdź model w Open WebUI
2. **Dodaj wiedzę** – zaingestionuj swoje repo lub wgraj dokumenty
3. **Testuj RAG** – pytaj model o zawartość swoich plików
4. **Customizuj** – stwórz własny Modelfile z system promptem
5. **Fine-tuning** – jeśli masz GPU, dotrenuj model na własnym datasecie

## Licencja

MIT
