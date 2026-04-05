#!/usr/bin/env bash
# ─────────────────────────────────────────────
# Free Local LLM – Instalator
# Uruchomienie: chmod +x install.sh && ./install.sh
# ─────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!!]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

echo ""
echo "  Free Local LLM – Instalator"
echo "  ─────────────────────────────────────────────"
echo ""

# ── 1. Sprawdź zależności ──────────────────────
command -v docker >/dev/null 2>&1 || err "Docker nie jest zainstalowany. Zainstaluj: https://docs.docker.com/get-docker/"
command -v docker-compose >/dev/null 2>&1 || err "docker-compose nie jest zainstalowany. Zainstaluj: https://docs.docker.com/compose/install/"
log "Docker i docker-compose są dostępne"

# ── 2. Skopiuj .env ────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn "Utworzono plik .env z domyślnych ustawień. Dostosuj go przed uruchomieniem."
else
    log ".env już istnieje"
fi

# ── 3. Utwórz katalogi danych ──────────────────
mkdir -p data/{documents,uploads}
log "Katalogi danych gotowe"

# ── 4. Wykryj GPU ──────────────────────────────
GPU_COMPOSE=""
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    log "Wykryto GPU NVIDIA – aktywuję tryb GPU"
    GPU_COMPOSE="-f docker-compose.gpu.yml"
else
    warn "Brak GPU NVIDIA – działam w trybie CPU (wolniejszy)"
fi

# ── 5. Uruchom stos ────────────────────────────
log "Buduję i uruchamiam kontenery..."
docker-compose -f docker-compose.yml $GPU_COMPOSE up -d --build

# ── 6. Poczekaj na Ollama ─────────────────────
log "Czekam na uruchomienie Ollama..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        break
    fi
    sleep 2
    echo -n "."
done
echo ""

# ── 7. Pobierz domyślne modele ─────────────────
DEFAULT_MODEL="${DEFAULT_MODEL:-qwen3:4b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"

log "Pobieram model domyślny: $DEFAULT_MODEL"
docker exec llm-ollama ollama pull "$DEFAULT_MODEL"

log "Pobieram model embeddingów: $EMBED_MODEL"
docker exec llm-ollama ollama pull "$EMBED_MODEL"

# ── 8. Gotowe ──────────────────────────────────
echo ""
echo "  ─────────────────────────────────────────────"
echo -e "  ${GREEN}System gotowy!${NC}"
echo ""
echo "  Chat (Open WebUI):    http://localhost:3000"
echo "  Panel admina:         http://localhost:3001"
echo "  Backend API:          http://localhost:8080"
echo "  API docs:             http://localhost:8080/docs"
echo ""
echo "  Aby zatrzymać:  docker-compose down"
echo "  Logi:           docker-compose logs -f"
echo "  ─────────────────────────────────────────────"
echo ""
