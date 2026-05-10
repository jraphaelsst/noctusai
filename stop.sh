#!/bin/bash
# NoctusAI Platform — Stop all services.
#
# Default mode is **Docker** (mirrors start.sh). Native (legacy) mode
# requires explicit `native` arg.
#
# Usage:
#   ./stop.sh                   docker compose down (containers + network; volumes preserved)
#   ./stop.sh volumes           + remove named volumes
#   ./stop.sh prune             + remove images + volumes + orphans (full clean)
#   ./stop.sh native            kill native uvicorn/vite processes on registered ports
#   ./stop.sh native --venv     + remove venv/
#   ./stop.sh native --node     + remove products/*/frontend/node_modules
#   ./stop.sh native --all      ports + venv + node_modules
#   ./stop.sh --docker          legacy alias for default Docker stop
#   ./stop.sh --docker-volumes  legacy alias for `volumes`
#   ./stop.sh --docker-prune    legacy alias for `prune`
#
# Idempotent — already-stopped is a no-op.

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
START_SH="$ROOT_DIR/start.sh"

MODE="${1:-docker}"

# Backward-compat aliases
case "$MODE" in
  --docker)         MODE="docker" ;;
  --docker-volumes) MODE="volumes" ;;
  --docker-prune)   MODE="prune" ;;
esac

docker_pre_check() {
  command -v docker >/dev/null 2>&1 || { echo "ERRO: docker nao esta no PATH." >&2; exit 1; }
  docker info >/dev/null 2>&1 || { echo "ERRO: Docker daemon nao esta rodando (open -a Docker)." >&2; exit 1; }
}

# ──────────────────────────────────────────────────────────────────────
# Docker modes (default + explicit)
# ──────────────────────────────────────────────────────────────────────
case "$MODE" in
  docker)
    docker_pre_check
    echo "==> docker compose down (todos os profiles)"
    # --remove-orphans handles tunnel containers from a previous tunnel run
    # whose profile isn't active in the current invocation.
    cd "$ROOT_DIR" && docker compose down --remove-orphans
    echo ""
    echo "NoctusAI Platform — containers parados (volumes preservados)."
    echo "  Reiniciar:        ./start.sh"
    echo "  Remover volumes:  ./stop.sh volumes"
    echo "  Limpeza total:    ./stop.sh prune"
    exit 0
    ;;
  volumes)
    docker_pre_check
    echo "==> docker compose down -v --remove-orphans (containers + volumes)"
    cd "$ROOT_DIR" && docker compose down -v --remove-orphans
    echo "NoctusAI Platform — containers + volumes removidos."
    exit 0
    ;;
  prune)
    docker_pre_check
    echo "==> docker compose down --rmi all -v --remove-orphans (containers + imagens + volumes)"
    cd "$ROOT_DIR" && docker compose down --rmi all -v --remove-orphans
    echo "NoctusAI Platform — containers + imagens + volumes removidos."
    exit 0
    ;;
  native)
    : # fall through to native code below
    ;;
  *)
    echo "ERRO: modo desconhecido '$MODE'." >&2
    echo "       Use: (default) | volumes | prune | native | native --venv | native --node | native --all" >&2
    exit 1
    ;;
esac

# ──────────────────────────────────────────────────────────────────────
# Native mode (legacy) — kills uvicorn/vite processes on registered ports.
# ──────────────────────────────────────────────────────────────────────
if [[ ! -f "$START_SH" ]]; then
  echo "ERRO: $START_SH nao encontrado." >&2
  exit 1
fi

NATIVE_FLAG="${2:-ports}"

# ----- harvest PRODUCTS registry from start.sh -----
PRODUCTS=()
eval "$(awk '
  /^# BEGIN_PRODUCTS_REGISTRY/  {capture=1; next}
  /^# END_PRODUCTS_REGISTRY/    {capture=0}
  capture                       {print}
' "$START_SH")"

if [[ ${#PRODUCTS[@]} -eq 0 ]]; then
  echo "WARN: PRODUCTS array vazio (start.sh ainda nao escaneado?)." >&2
fi

# Compute PORTS list.
PORTS=()
for entry in "${PRODUCTS[@]}"; do
  IFS=':' read -r _slug _name bp fp <<< "$entry"
  PORTS+=("$bp" "$fp")
done

# ----- helpers -----
kill_tree() {
  local pid=$1
  local children
  children=$(pgrep -P "$pid" 2>/dev/null) || true
  for child in $children; do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

free_ports() {
  if [[ ${#PORTS[@]} -eq 0 ]]; then
    return 0
  fi
  local stale_pids
  stale_pids=$(lsof -ti :$(IFS=,; echo "${PORTS[*]}") 2>/dev/null | sort -u) || true
  if [[ -n "$stale_pids" ]]; then
    echo "==> matando processos nas portas ${PORTS[*]}"
    local count=0
    for pid in $stale_pids; do
      kill_tree "$pid"
      count=$((count + 1))
    done
    sleep 1
    echo "    $count processo(s) terminado(s)"
  else
    echo "==> nenhum processo escutando nas portas registradas"
  fi
}

# ----- native flag dispatch -----
case "$NATIVE_FLAG" in
  ports)
    free_ports
    ;;
  --venv)
    free_ports
    if [[ -d "$ROOT_DIR/venv" ]]; then
      echo "==> removendo venv/"
      rm -rf "$ROOT_DIR/venv"
    fi
    ;;
  --node)
    free_ports
    echo "==> removendo products/*/frontend/node_modules"
    find "$ROOT_DIR/products" -mindepth 3 -maxdepth 3 -type d -name node_modules -prune -exec rm -rf {} +
    ;;
  --all)
    free_ports
    if [[ -d "$ROOT_DIR/venv" ]]; then
      echo "==> removendo venv/"
      rm -rf "$ROOT_DIR/venv"
    fi
    echo "==> removendo products/*/frontend/node_modules"
    find "$ROOT_DIR/products" -mindepth 3 -maxdepth 3 -type d -name node_modules -prune -exec rm -rf {} +
    ;;
  *)
    echo "ERRO: flag desconhecido '$NATIVE_FLAG' apos 'native'. Use: (none) | --venv | --node | --all" >&2
    exit 1
    ;;
esac

echo ""
echo "NoctusAI Platform — servicos nativos parados."
echo "  Reiniciar:  ./start.sh native  (ou ./start.sh para Docker)"
echo ""
