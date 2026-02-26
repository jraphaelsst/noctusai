#!/bin/bash
# NoctusAI Platform — Start all services (Core + ERP Imobiliario)
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Verify root .env exists (all backends read from it)
if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "ERRO: Arquivo .env nao encontrado na raiz do repositorio."
  echo ""
  echo "  Crie o arquivo .env com as variaveis necessarias (veja CLAUDE.md)."
  echo ""
  echo "Preencha as variaveis (Supabase, JWT, etc.) e tente novamente."
  exit 1
fi

PORTS=(8001 8000 5173 8080)
PIDS=()

# Kill a process and all its descendants
kill_tree() {
  local pid=$1
  local children
  children=$(pgrep -P "$pid" 2>/dev/null) || true
  for child in $children; do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

# Free ports by killing any leftover processes from previous runs
free_ports() {
  local stale_pids
  stale_pids=$(lsof -ti :$(IFS=,; echo "${PORTS[*]}") 2>/dev/null | sort -u) || true
  if [ -n "$stale_pids" ]; then
    echo "[cleanup] Matando processos orfaos nas portas ${PORTS[*]}..."
    for pid in $stale_pids; do
      kill_tree "$pid"
    done
    sleep 1
  fi
}

cleanup() {
  echo ""
  echo "Parando todos os servicos..."
  for pid in "${PIDS[@]}"; do
    kill_tree "$pid"
  done
  wait 2>/dev/null
  echo "Todos os servicos parados."
  exit 0
}

trap cleanup SIGINT SIGTERM

echo "============================================"
echo "  NoctusAI Platform — Iniciando servicos"
echo "============================================"
echo ""

# Kill leftover processes from previous runs
free_ports

# --- Single root venv (shared by all backends) ---
VENV="$ROOT_DIR/venv"
if [ ! -d "$VENV" ]; then
  echo "[venv] Criando venv na raiz do repositorio..."
  python3 -m venv "$VENV"
fi
echo "[venv] Instalando dependencias..."
"$VENV/bin/pip" install -q -r "$ROOT_DIR/requirements.txt"

# --- Core Backend (porta 8001) ---
CORE_BACKEND="$ROOT_DIR/core/backend"
echo "[Core Backend] Iniciando na porta 8001..."
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8001 --app-dir "$CORE_BACKEND" &
PIDS+=($!)

# --- ERP Backend (porta 8000) ---
ERP_BACKEND="$ROOT_DIR/products/erp-imobiliario/backend"
echo "[ERP Backend] Iniciando na porta 8000..."
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --app-dir "$ERP_BACKEND" &
PIDS+=($!)

# --- Core Frontend (porta 5173) ---
CORE_FRONTEND="$ROOT_DIR/core/frontend"
if [ ! -d "$CORE_FRONTEND/node_modules" ]; then
  echo "[Core Frontend] Instalando dependencias..."
  (cd "$CORE_FRONTEND" && npm install)
fi

echo "[Core Frontend] Iniciando na porta 5173..."
(cd "$CORE_FRONTEND" && exec npx vite --host 0.0.0.0 --port 5173) &
PIDS+=($!)

# --- ERP Frontend (porta 8080) ---
ERP_FRONTEND="$ROOT_DIR/products/erp-imobiliario/frontend"
if [ ! -d "$ERP_FRONTEND/node_modules" ]; then
  echo "[ERP Frontend] Instalando dependencias..."
  (cd "$ERP_FRONTEND" && npm install)
fi

echo "[ERP Frontend] Iniciando na porta 8080..."
(cd "$ERP_FRONTEND" && exec npx vite --host 0.0.0.0 --port 8080) &
PIDS+=($!)

echo ""
echo "============================================"
echo "  Servicos iniciados:"
echo "  Core Backend  → http://localhost:8001"
echo "  ERP Backend   → http://localhost:8000"
echo "  Core Frontend → http://localhost:5173"
echo "  ERP Frontend  → http://localhost:8080"
echo "============================================"
echo ""
echo "Pressione Ctrl+C para parar todos os servicos."
echo ""

# Wait for all background processes
wait
