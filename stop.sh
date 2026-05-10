#!/bin/bash
# NoctusAI Platform — Stop all services.
#
# Companion to ./start.sh. Use this when start.sh was backgrounded or
# run from another shell (so Ctrl+C trap is unreachable). Reads the
# PRODUCTS array from start.sh — source of truth stays single — and
# kills any process bound to a registered backend or frontend port.
#
# Usage:
#   ./stop.sh                kill processes on registered product ports
#   ./stop.sh --venv         + remove venv/  (full reset)
#   ./stop.sh --node         + remove products/*/frontend/node_modules
#   ./stop.sh --all          ports + venv + node_modules
#
# Idempotent — already-stopped is a no-op.

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
START_SH="$ROOT_DIR/start.sh"

if [[ ! -f "$START_SH" ]]; then
  echo "ERRO: $START_SH nao encontrado." >&2
  exit 1
fi

MODE="${1:-ports}"

# ----- harvest PRODUCTS registry from start.sh -----
# Source the BEGIN/END_PRODUCTS_REGISTRY block so the registry has one
# canonical writer (scaffold_product) and one canonical reader (start.sh +
# stop.sh). awk emits only the array declaration so we can eval safely.
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

# ----- mode dispatch -----
case "$MODE" in
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
    echo "ERRO: modo desconhecido '$MODE'. Use: (none) | --venv | --node | --all" >&2
    exit 1
    ;;
esac

echo ""
echo "NoctusAI Platform — servicos parados."
echo "  Reiniciar:  ./start.sh"
echo ""
