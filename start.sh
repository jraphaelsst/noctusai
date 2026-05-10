#!/bin/bash
# NoctusAI Platform — Start all services.
#
# Default mode is **Docker**: every product runs as a container pair on
# the `noctus-net` shared network. The native (uvicorn + vite) path is
# preserved as the legacy mode for hot-reload-fast iteration on a single
# product.
#
# Modes:
#   ./start.sh                     full fleet (10 products × backend+frontend)
#   ./start.sh redis               + Redis profile
#   ./start.sh full                + Redis + WAHA
#   ./start.sh tunnel <slug>       + cloudflare tunnel exposing one product
#   ./start.sh tunnel              + cloudflare tunnels for ALL products
#   ./start.sh build               rebuild images then up (forces refresh)
#   ./start.sh native              legacy native (uvicorn + vite, hot-reload)
#   ./start.sh --docker [profile]  legacy alias — kept for backward compat
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

# ──────────────────────────────────────────────────────────────────────
# Mode dispatch.
# ──────────────────────────────────────────────────────────────────────
MODE="${1:-fleet}"

# Backward-compat: ./start.sh --docker [profile]  →  ./start.sh [profile]
if [[ "$MODE" == "--docker" ]]; then
  MODE="${2:-fleet}"
  shift  # so $1 becomes the old $2 (profile or slug)
  set -- "$MODE" "${@:2}"  # rebuild $@ as if the user typed `./start.sh <mode>`
fi

# ──────────────────────────────────────────────────────────────────────
# Native mode (legacy) — uvicorn + vite directly on host. Preserved for
# fast hot-reload on a single product. Mode 'native' falls through past
# the docker block to the original code below.
# ──────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "native" ]]; then
  : # fall through to the legacy native code at the bottom
else
  # Default = Docker. Mode is one of: fleet | redis | full | tunnel | build
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERRO: docker nao esta instalado ou nao esta no PATH." >&2
    echo "       Use './start.sh native' pra rodar sem Docker." >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "ERRO: 'docker compose' (v2) requerido. Instale Docker Desktop atualizado." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "ERRO: Docker daemon nao esta rodando." >&2
    echo "" >&2
    echo "  Abra o Docker Desktop e espere a baleia (icone na barra de menu)" >&2
    echo "  estabilizar antes de tentar de novo:" >&2
    echo "" >&2
    echo "    open -a Docker" >&2
    echo "" >&2
    echo "  Ou rode em modo nativo: ./start.sh native" >&2
    exit 1
  fi

  echo "============================================"
  echo "  NoctusAI Platform — Docker"
  echo "  modo: $MODE"
  echo "============================================"
  echo ""

  # Build COMPOSE_ARGS based on mode
  COMPOSE_ARGS=(compose)
  TUNNEL_SLUG=""
  case "$MODE" in
    fleet|"")
      ;;  # default — no extra profiles
    redis)
      COMPOSE_ARGS+=(--profile redis)
      ;;
    waha)
      COMPOSE_ARGS+=(--profile waha)
      ;;
    full)
      COMPOSE_ARGS+=(--profile full)
      ;;
    build)
      ;;  # special-cased below; forces rebuild
    tunnel)
      TUNNEL_SLUG="${2:-}"
      if [[ -z "$TUNNEL_SLUG" ]]; then
        # tunnel ALL products
        COMPOSE_ARGS+=(--profile tunnel-all)
        echo "[tunnel] expondo TODA a frota via cloudflared (10 URLs publicas)"
      else
        # tunnel ONE product — validate slug against registry
        FOUND=0
        for entry in "${PRODUCTS[@]}"; do
          IFS=':' read -r s _ _ _ <<< "$entry"
          [[ "$s" == "$TUNNEL_SLUG" ]] && FOUND=1 && break
        done
        if [[ $FOUND -eq 0 ]]; then
          echo "ERRO: slug '$TUNNEL_SLUG' nao registrado em PRODUCTS." >&2
          echo "       Slugs disponiveis:" >&2
          for entry in "${PRODUCTS[@]}"; do
            IFS=':' read -r s _ _ _ <<< "$entry"
            echo "         - $s" >&2
          done
          exit 1
        fi
        COMPOSE_ARGS+=(--profile "tunnel-$TUNNEL_SLUG")
        echo "[tunnel] expondo $TUNNEL_SLUG via cloudflared"
      fi
      ;;
    *)
      echo "ERRO: modo desconhecido '$MODE'." >&2
      echo "       Use: fleet | redis | waha | full | tunnel [slug] | build | native" >&2
      exit 1
      ;;
  esac

  # Build (cached for fleet/redis/full/tunnel; forced for `build` mode)
  if [[ "$MODE" == "build" ]]; then
    echo "[docker] Rebuild forcado (--no-cache)..."
    docker "${COMPOSE_ARGS[@]}" build --no-cache --pull
  else
    echo "[docker] Buildando imagens (cache hit se ja construidas)..."
    docker "${COMPOSE_ARGS[@]}" build
  fi

  echo "[docker] Subindo servicos em background..."
  docker "${COMPOSE_ARGS[@]}" up -d

  # Print URL summary using the registry block.
  echo ""
  echo "============================================"
  echo "  Servicos containerizados rodando:"
  for entry in "${PRODUCTS[@]}"; do
    IFS=':' read -r _slug name bp fp <<< "$entry"
    echo "  $name Backend  → http://localhost:$bp"
    echo "  $name Frontend → http://localhost:$fp"
  done
  echo "============================================"

  # Tunnel URL extraction — wait for cloudflared to log its public URL
  if [[ "$MODE" == "tunnel" ]]; then
    echo ""
    echo "[tunnel] Aguardando URL publica do cloudflared (~10-30s)..."
    extract_tunnel_url() {
      local container="$1"
      local url=""
      for i in $(seq 1 30); do
        url=$(docker logs "$container" 2>&1 | grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" | head -1 || true)
        if [[ -n "$url" ]]; then
          echo "$url"
          return 0
        fi
        sleep 2
      done
      return 1
    }

    # Verify the extracted URL actually resolves and serves. Cloudflare's
    # edge needs ~10s after the cloudflared registration log line to
    # propagate the hostname. A second hidden failure mode: connection
    # already died (QUIC dropout) — the log still shows the URL but DNS
    # is NXDOMAIN. Curl-verifying here surfaces both before we report.
    verify_tunnel_url() {
      local url="$1"
      [[ -z "$url" || "$url" =~ ^\( ]] && return 1
      for i in $(seq 1 15); do
        if curl -fsS -o /dev/null --max-time 8 "$url/api/health" 2>/dev/null; then
          return 0
        fi
        sleep 2
      done
      return 1
    }

    if [[ -z "$TUNNEL_SLUG" ]]; then
      # All products
      echo ""
      echo "  URLs publicas:"
      for entry in "${PRODUCTS[@]}"; do
        IFS=':' read -r s _ _ _ <<< "$entry"
        url=$(extract_tunnel_url "noctus-$s-tunnel" || echo "(timeout — docker logs noctus-$s-tunnel)")
        if verify_tunnel_url "$url"; then
          printf "    ✓ %-20s → %s\n" "$s" "$url"
        else
          printf "    ⚠ %-20s → %s  (nao verificada — pode ainda estar propagando)\n" "$s" "$url"
        fi
      done
    else
      url=$(extract_tunnel_url "noctus-$TUNNEL_SLUG-tunnel" || echo "(timeout)")
      echo ""
      echo "  ╔════════════════════════════════════════════════════════════╗"
      printf "  ║  Public URL (%s):  %-32s║\n" "$TUNNEL_SLUG" "$url"
      echo "  ╚════════════════════════════════════════════════════════════╝"
      echo ""
      if verify_tunnel_url "$url"; then
        echo "  ✓ Verificada via curl /api/health → 200 OK"
      else
        echo "  ⚠ AVISO: URL extraida dos logs mas nao respondeu em ~30s."
        echo "    Pode ser propagacao do edge da Cloudflare (espere 1min e tente),"
        echo "    OU o tunnel ja perdeu conexao (docker logs noctus-$TUNNEL_SLUG-tunnel)."
      fi
      echo ""
      echo "  Use essa URL em webhooks de Stripe / Meta / Google OAuth callback."
      echo "  A URL e EFEMERA — muda toda vez que o tunnel reinicia."
    fi
  fi

  echo ""
  echo "  docker compose logs -f       # acompanhar logs"
  echo "  ./stop.sh                    # parar tudo"
  echo ""
  exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# Native mode (legacy) — uvicorn + vite directly on host.
# Reached only when the user passes 'native' as first arg.
# ──────────────────────────────────────────────────────────────────────
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
echo "  NoctusAI Platform — modo nativo (legacy)"
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
