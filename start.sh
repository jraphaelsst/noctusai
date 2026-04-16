#!/bin/bash
# NoctusAI Platform — Start all services (Core + ERP Imobiliario + Personal Finance)
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

PORTS=(8000 8001 8002 8003 8005 5173 8080 8090 8095 8110)
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

# --- Core Backend (porta 8000) ---
CORE_BACKEND="$ROOT_DIR/core/backend"
echo "[Core Backend] Iniciando na porta 8000..."
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir "$CORE_BACKEND" &
PIDS+=($!)

# --- ERP Backend (porta 8001) ---
ERP_BACKEND="$ROOT_DIR/products/erp-imobiliario/backend"
echo "[ERP Backend] Iniciando na porta 8001..."
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8001 --reload --app-dir "$ERP_BACKEND" &
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

# --- Personal Finance Backend (porta 8002) ---
PF_BACKEND="$ROOT_DIR/products/personal-finance/backend"
echo "[PF Backend] Iniciando na porta 8002..."
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8002 --reload --app-dir "$PF_BACKEND" &
PIDS+=($!)

# --- Personal Finance Frontend (porta 8090) ---
PF_FRONTEND="$ROOT_DIR/products/personal-finance/frontend"
if [ ! -d "$PF_FRONTEND/node_modules" ]; then
  echo "[PF Frontend] Instalando dependencias..."
  (cd "$PF_FRONTEND" && npm install)
fi

echo "[PF Frontend] Iniciando na porta 8090..."
(cd "$PF_FRONTEND" && exec npx vite --host 0.0.0.0 --port 8090) &
PIDS+=($!)

# --- Therapy Backend (porta 8003) ---
THERAPY_BACKEND="$ROOT_DIR/products/therapy-platform/backend"
echo "[Therapy Backend] Iniciando na porta 8003..."
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8003 --reload --app-dir "$THERAPY_BACKEND" &
PIDS+=($!)

# --- Therapy Frontend (porta 8095) ---
THERAPY_FRONTEND="$ROOT_DIR/products/therapy-platform/frontend"
if [ ! -d "$THERAPY_FRONTEND/node_modules" ]; then
  echo "[Therapy Frontend] Instalando dependencias..."
  (cd "$THERAPY_FRONTEND" && npm install)
fi

echo "[Therapy Frontend] Iniciando na porta 8095..."
(cd "$THERAPY_FRONTEND" && exec npx vite --host 0.0.0.0 --port 8095) &
PIDS+=($!)

# --- Seed Backend (porta 8004) ---
SEED_BACKEND="$ROOT_DIR/products/seed/backend"
if [ -d "$SEED_BACKEND" ]; then
  echo "[Seed Backend] Iniciando na porta 8004..."
  "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8004 --reload --app-dir "$SEED_BACKEND" &
  PIDS+=($!)
fi

# --- Seed Frontend (porta 8100) ---
SEED_FRONTEND="$ROOT_DIR/products/seed/frontend"
if [ -d "$SEED_FRONTEND" ]; then
  if [ ! -d "$SEED_FRONTEND/node_modules" ]; then
    echo "[Seed Frontend] Instalando dependencias..."
    (cd "$SEED_FRONTEND" && npm install)
  fi
  echo "[Seed Frontend] Iniciando na porta 8100..."
  (cd "$SEED_FRONTEND" && exec npx vite --host 0.0.0.0 --port 8100) &
  PIDS+=($!)
fi

# --- Daily Life Backend (porta 8005) ---
DL_BACKEND="$ROOT_DIR/products/daily-life/backend"
if [ -d "$DL_BACKEND" ]; then
  echo "[Daily Life Backend] Iniciando na porta 8005..."
  "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8005 --reload --app-dir "$DL_BACKEND" &
  PIDS+=($!)
fi

# --- Daily Life Frontend (porta 8110) ---
DL_FRONTEND="$ROOT_DIR/products/daily-life/frontend"
if [ -d "$DL_FRONTEND" ]; then
  if [ ! -d "$DL_FRONTEND/node_modules" ]; then
    echo "[Daily Life Frontend] Instalando dependencias..."
    (cd "$DL_FRONTEND" && npm install)
  fi
  echo "[Daily Life Frontend] Iniciando na porta 8110..."
  (cd "$DL_FRONTEND" && exec npx vite --host 0.0.0.0 --port 8110) &
  PIDS+=($!)
fi

# --- Mailing Backend (porta 8006) ---
MAIL_BACKEND="$ROOT_DIR/products/mailing/backend"
if [ -d "$MAIL_BACKEND" ]; then
  echo "[Mailing Backend] Iniciando na porta 8006..."
  "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8006 --reload --app-dir "$MAIL_BACKEND" &
  PIDS+=($!)
fi

# --- Mailing Frontend (porta 8120) ---
MAIL_FRONTEND="$ROOT_DIR/products/mailing/frontend"
if [ -d "$MAIL_FRONTEND" ] && [ -f "$MAIL_FRONTEND/package.json" ]; then
  if [ ! -d "$MAIL_FRONTEND/node_modules" ]; then
    echo "[Mailing Frontend] Instalando dependencias..."
    (cd "$MAIL_FRONTEND" && npm install)
  fi
  echo "[Mailing Frontend] Iniciando na porta 8120..."
  (cd "$MAIL_FRONTEND" && exec npx vite --host 0.0.0.0 --port 8120) &
  PIDS+=($!)
fi

echo ""
echo "============================================"
echo "  Servicos iniciados:"
echo "  Core Backend       → http://localhost:8000"
echo "  ERP Backend        → http://localhost:8001"
echo "  PF Backend         → http://localhost:8002"
echo "  Therapy Backend    → http://localhost:8003"
echo "  Seed Backend       → http://localhost:8004"
echo "  Daily Life Backend → http://localhost:8005"
echo "  Core Frontend      → http://localhost:5173"
echo "  ERP Frontend       → http://localhost:8080"
echo "  PF Frontend        → http://localhost:8090"
echo "  Therapy Frontend   → http://localhost:8095"
echo "  Seed Frontend      → http://localhost:8100"
echo "  Daily Life Frontend→ http://localhost:8110"
echo "  Mailing Backend   → http://localhost:8006"
echo "  Mailing Frontend  → http://localhost:8120"
echo "============================================"
echo ""
echo "Pressione Ctrl+C para parar todos os servicos."
echo ""

# Wait for all background processes
wait
