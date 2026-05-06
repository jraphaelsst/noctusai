#!/bin/bash
# NoctusAI Platform — Start all services
#
# Products are registered in the PRODUCTS array below. The
# `noctus.dev.scaffold_product` MCP tool auto-appends a new entry between
# the BEGIN/END_PRODUCTS_REGISTRY sentinels — DO NOT remove or rename the
# sentinels (the injection regex depends on them). Manual edits inside the
# block are safe; the tool is idempotent (skips if the slug is already there).
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

# Product registry — format: "slug:Display Name:backend_port:frontend_port"
# Auto-extended by `noctus.dev.scaffold_product`. Edit by hand only when you
# know what you're doing; the tool is the canonical writer.
# BEGIN_PRODUCTS_REGISTRY
PRODUCTS=(
  "core:Core:8000:5173"
  "erp-imobiliario:ERP Imobiliario:8001:8080"
  "personal-finance:Personal Finance:8002:8090"
  "therapy-platform:Therapy Platform:8003:8095"
  "seed:Seed:8004:8100"
  "daily-life:Daily Life:8005:8110"
  "mailing:Mailing:8006:8120"
  "adconnect:AdConnect:8007:8130"
  "dev-team:Dev Team:8009:8123"
  "media-scheduling:Media Scheduling:8096:8140"
)
# END_PRODUCTS_REGISTRY

# Compute PORTS list (backends + frontends) for the cleanup sweeper.
PORTS=()
for entry in "${PRODUCTS[@]}"; do
  IFS=':' read -r _slug _name bp fp <<< "$entry"
  PORTS+=("$bp" "$fp")
done

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

# Install frontend deps if node_modules is missing or package.json changed since last install
ensure_frontend_deps() {
  local dir="$1"
  local name="$2"
  if [ ! -d "$dir/node_modules" ] || [ "$dir/package.json" -nt "$dir/node_modules/.package-lock.json" ]; then
    echo "[$name] Instalando dependencias..."
    (cd "$dir" && npm install --prefer-offline --no-audit --no-fund -q)
  fi
}

# --- Single root venv (shared by all backends) ---
VENV="$ROOT_DIR/venv"
if [ ! -d "$VENV" ]; then
  echo "[venv] Criando venv na raiz do repositorio..."
  python3 -m venv "$VENV"
fi
echo "[venv] Instalando dependencias..."
"$VENV/bin/pip" install -q -r "$ROOT_DIR/requirements.txt"

# Stamp seed version before any backend imports noctusai_seed / noctusai_lib.
# Surfaces drift when devs pull new commits but forget to restart services.
# Idempotent; fast; fails-open (script exits 1 if git is missing).
if [ -x "$ROOT_DIR/scripts/stamp-seed-version.sh" ]; then
  bash "$ROOT_DIR/scripts/stamp-seed-version.sh" || true
fi

# --- Start each product (backend + frontend) ---
URLS=()
for entry in "${PRODUCTS[@]}"; do
  IFS=':' read -r slug name bp fp <<< "$entry"
  backend_dir="$ROOT_DIR/products/$slug/backend"
  frontend_dir="$ROOT_DIR/products/$slug/frontend"

  if [ -d "$backend_dir" ] && [ -f "$backend_dir/app/main.py" ]; then
    echo "[$name Backend] Iniciando na porta $bp..."
    "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$bp" --reload --app-dir "$backend_dir" &
    PIDS+=($!)
    URLS+=("  $name Backend → http://localhost:$bp")
  fi

  if [ -d "$frontend_dir" ] && [ -f "$frontend_dir/package.json" ]; then
    ensure_frontend_deps "$frontend_dir" "$name Frontend"
    echo "[$name Frontend] Iniciando na porta $fp..."
    (cd "$frontend_dir" && exec npx vite --host 0.0.0.0 --port "$fp") &
    PIDS+=($!)
    URLS+=("  $name Frontend → http://localhost:$fp")
  fi
done

echo ""
echo "============================================"
echo "  Servicos iniciados:"
for url in "${URLS[@]}"; do
  echo "$url"
done
echo "============================================"
echo ""
echo "Pressione Ctrl+C para parar todos os servicos."
echo ""

# Wait for all background processes
wait
