#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Free Local LLM – Instalator v3.0
# Uruchomienie: chmod +x install.sh && ./install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo -e "${BOLD}  Free Local LLM – Personal AI${NC}"
echo "  ─────────────────────────────────────────────────────"
echo ""

# ── 1. Sprawdź zależności ─────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || err "Docker nie jest zainstalowany. https://docs.docker.com/get-docker/"
command -v docker-compose >/dev/null 2>&1 || err "docker-compose nie jest zainstalowany. https://docs.docker.com/compose/install/"
log "Docker i docker-compose dostępne"

# ── 2. Skopiuj .env ───────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn "Utworzono plik .env z domyślnych ustawień."
    echo ""
    echo -e "  ${CYAN}Ważne:${NC} Aby aktywować auto-sync GitHub wpisz swój token:"
    echo -e "  ${BOLD}  echo 'GITHUB_TOKEN=ghp_twój_token' >> .env${NC}"
    echo ""
else
    log ".env już istnieje"
fi

# ── 3. Utwórz katalogi danych ─────────────────────────────────────────────────
mkdir -p data/{documents,uploads,topics}
log "Katalogi danych gotowe"

# ── 4. Wykryj GPU ─────────────────────────────────────────────────────────────
GPU_COMPOSE=""
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    log "Wykryto GPU NVIDIA – aktywuję tryb GPU (szybsze generowanie)"
    GPU_COMPOSE="-f docker-compose.gpu.yml"
else
    warn "Brak GPU NVIDIA – tryb CPU (modele 3-4B działają sprawnie)"
fi

# ── 5. Uruchom stos ───────────────────────────────────────────────────────────
echo ""
info "Budowanie i uruchamianie kontenerów..."
docker-compose -f docker-compose.yml $GPU_COMPOSE up -d --build
echo ""

# ── 6. Poczekaj na Ollama ─────────────────────────────────────────────────────
info "Czekam na uruchomienie Ollama..."
attempt=0
while [ $attempt -lt 40 ]; do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        break
    fi
    attempt=$((attempt+1))
    echo -n "."
    sleep 3
done
echo ""

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    warn "Ollama nie odpowiada po 2 minutach. Modele zostaną pobrane przez ollama-init w tle."
else
    log "Ollama gotowa"
fi

# ── 7. Pobierz modele (bezpośrednio jeśli osiągalne) ─────────────────────────
DEFAULT_MODEL="${DEFAULT_MODEL:-$(grep DEFAULT_MODEL .env 2>/dev/null | cut -d= -f2 || echo 'qwen3:4b')}"
EMBED_MODEL="${EMBED_MODEL:-$(grep EMBED_MODEL .env 2>/dev/null | cut -d= -f2 || echo 'nomic-embed-text')}"

if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    info "Pobieram model czatu: ${DEFAULT_MODEL}  (może zająć kilka minut)"
    docker exec llm-ollama ollama pull "$DEFAULT_MODEL" || warn "Nie udało się pobrać $DEFAULT_MODEL – kontener ollama-init dokończy w tle"

    info "Pobieram model embeddingów: ${EMBED_MODEL}"
    docker exec llm-ollama ollama pull "$EMBED_MODEL" || warn "Nie udało się pobrać $EMBED_MODEL"

    log "Modele gotowe"
else
    info "Modele zostaną pobrane automatycznie przez serwis ollama-init"
fi

# ── 8. Sprawdź GitHub token ───────────────────────────────────────────────────
GITHUB_TOKEN_VALUE=$(grep '^GITHUB_TOKEN=' .env 2>/dev/null | cut -d= -f2 || true)
if [ -n "$GITHUB_TOKEN_VALUE" ] && [ "$GITHUB_TOKEN_VALUE" != "" ]; then
    log "GitHub token wykryty – backend uruchomi auto-sync przy starcie"
else
    warn "Brak GITHUB_TOKEN w .env – auto-sync GitHub wyłączony"
    echo -e "     Dodaj token: ${BOLD}echo 'GITHUB_TOKEN=ghp_xxx' >> .env${NC}"
fi

# ── 9. Gotowe ─────────────────────────────────────────────────────────────────
echo ""
echo "  ─────────────────────────────────────────────────────"
echo -e "  ${GREEN}${BOLD}System gotowy!${NC}"
echo ""
echo -e "  ${CYAN}Chat (główny interfejs):${NC}  http://localhost:3001"
echo -e "  ${CYAN}Backend API:${NC}              http://localhost:8080"
echo -e "  ${CYAN}API Docs:${NC}                 http://localhost:8080/docs"
echo ""
echo "  Pipeline aktywny:"
echo "    Wpisujesz pytanie → RAG przeszukuje wiedzę → LLM odpowiada"
echo "    → w tle: nauka z rozmowy + crawl DuckDuckGo + Wikipedia"
echo "    → GitHub sync co 24h · Web Intel crawl co 12h"
echo ""
echo "  Aby zatrzymać:   docker-compose down"
echo "  Logi:            docker-compose logs -f"
echo "  Logi backendu:   docker-compose logs -f backend"
echo "  ─────────────────────────────────────────────────────"
echo ""
