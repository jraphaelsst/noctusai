#!/bin/bash
# Post-fleet-up smoke test.
#
# Hits /api/health on every backend, verifies frontend serves index, and
# prints a status table. Exit code 0 if every backend returns 200, else 1.
#
# Run AFTER `./start.sh` (or `./start.sh --docker`) — assumes the fleet
# is up. Idempotent; safe to re-run.
set -e

cd "$(dirname "$0")/.."

# Source the registry from start.sh — single source of truth.
PRODUCTS=()
eval "$(awk '
  /^# BEGIN_PRODUCTS_REGISTRY/  {capture=1; next}
  /^# END_PRODUCTS_REGISTRY/    {capture=0}
  capture                       {print}
' start.sh)"

if [[ ${#PRODUCTS[@]} -eq 0 ]]; then
  echo "ERRO: PRODUCTS array vazio. start.sh ainda nao escaneado?" >&2
  exit 1
fi

echo "============================================"
echo "  NoctusAI Platform — smoke test"
echo "============================================"
echo ""
echo "=== docker compose ps ==="
docker compose ps --format "table {{.Service}}\t{{.Status}}" | head -30
echo ""

echo "=== Backend health checks ==="
fails=0
for entry in "${PRODUCTS[@]}"; do
  IFS=':' read -r slug name bp fp <<< "$entry"
  status=$(curl -fsS -o /dev/null -w "%{http_code}" "http://localhost:$bp/api/health" 2>/dev/null || echo "FAIL")
  if [[ "$status" == "200" ]]; then
    printf "  ✓ %-20s http://localhost:%-5s  %s\n" "$slug" "$bp" "$status"
  else
    printf "  ✗ %-20s http://localhost:%-5s  %s\n" "$slug" "$bp" "$status"
    fails=$((fails + 1))
  fi
done
echo ""

echo "=== Frontend smoke (sample: core + seed) ==="
for entry in "core:5173" "seed:8100"; do
  IFS=':' read -r slug fp <<< "$entry"
  status=$(curl -fsS -o /dev/null -w "%{http_code}" "http://localhost:$fp" 2>/dev/null || echo "FAIL")
  printf "  %s %-10s http://localhost:%-5s  %s\n" \
    "$([[ $status == 200 ]] && echo ✓ || echo ✗)" "$slug" "$fp" "$status"
done
echo ""

if [[ $fails -gt 0 ]]; then
  echo "============================================"
  echo "  $fails backend(s) failed health check."
  echo "  docker compose logs <slug>-backend  para investigar"
  echo "============================================"
  exit 1
fi

echo "============================================"
echo "  Frota saudavel. ${#PRODUCTS[@]}/${#PRODUCTS[@]} backends OK."
echo "  Proximo: ./start.sh tunnel <slug>  para expor publicamente"
echo "============================================"
