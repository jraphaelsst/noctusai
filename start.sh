#!/bin/bash
# NoctusAI Platform — Start services.
#
# Default mode is **Docker**: SINGLE container per product (uvicorn serves
# API + built SPA on one port) on the external `noctus-net`. Two compose
# projects: `noctusai-products` (the fleet) + `noctusai-infra`
# (Redis/WAHA/Postgres). The native (uvicorn + vite) path is the legacy
# hot-reload mode.  → project: containerization-single-container.
#
# Modes:
#   ./start.sh                     whole fleet (all products, one container each)
#   ./start.sh <slug> [<slug>...]  ONLY these products (subset)
#   (no `dev` mode — every local container live-rebuilds: vite build
#    --watch + uvicorn --reload, source bind-mounted. One shape always.)
#   ./start.sh redis               fleet + Redis (infra project)
#   ./start.sh waha                fleet + WAHA
#   ./start.sh local-db            fleet + local Postgres
#   ./start.sh full                fleet + Redis + WAHA + Postgres
#   ./start.sh tunnel <slug>       fleet + cloudflare tunnel exposing one product
#   ./start.sh tunnel              fleet + tunnels for ALL products
#   ./start.sh build               rebuild images (incl. bases) then up
#   ./start.sh native              legacy native (uvicorn + vite, hot-reload)
#   ./start.sh --docker [profile]  legacy alias — kept for backward compat
#
# Products are registered in the PRODUCTS array below between the
# BEGIN/END_PRODUCTS_REGISTRY sentinels (scaffold_product appends here).
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Verify root .env exists (all backends read from it)
if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "ERRO: Arquivo .env nao encontrado na raiz do repositorio."
  echo "  Crie o .env com as variaveis necessarias (veja CLAUDE.md)."
  exit 1
fi

# Product registry — format: "slug:Display Name:backend_port:frontend_port"
# Single-container: the product is served on backend_port (API + SPA).
# frontend_port is retained for the native legacy mode + the port sweeper;
# frontend_port is retained only for the native legacy path + the port
# sweeper (single-container mode publishes just backend_port).
# BEGIN_PRODUCTS_REGISTRY
PRODUCTS=(
  "core:Core:8000:5173"
  "erp-imobiliario:ERP Imobiliario:8001:8080"
  "personal-finance:Personal Finance:8002:8090"
  "therapy-platform:Therapy Platform:8003:8095"
  "seed:Seed:8004:8100"
  "daily-life:Daily Life:8005:8110"
  "adconnect:AdConnect:8007:8130"
  "dev-team:Dev Team:8009:8123"
  "social-wiring:Social Wiring:8011:8160"
)
# END_PRODUCTS_REGISTRY

# Compute PORTS list (backends + frontends) for the native cleanup sweeper.
PORTS=()
for entry in "${PRODUCTS[@]}"; do
  IFS=':' read -r _slug _name bp fp <<< "$entry"
  PORTS+=("$bp" "$fp")
done

is_registered_slug() {
  local q="$1" entry s
  for entry in "${PRODUCTS[@]}"; do
    IFS=':' read -r s _ _ _ <<< "$entry"
    [[ "$s" == "$q" ]] && return 0
  done
  return 1
}

# ──────────────────────────────────────────────────────────────────────
# Mode dispatch.
# ──────────────────────────────────────────────────────────────────────
MODE="${1:-fleet}"

# Backward-compat: ./start.sh --docker [profile]  →  ./start.sh [profile]
if [[ "$MODE" == "--docker" ]]; then
  shift
  set -- "${@:-fleet}"
  MODE="${1:-fleet}"
fi

if [[ "$MODE" == "native" ]]; then
  : # fall through to the legacy native code at the bottom
else
  # ── Docker. ─────────────────────────────────────────────────────────
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERRO: docker nao esta instalado/no PATH. Use './start.sh native'." >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "ERRO: 'docker compose' (v2) requerido (Docker Desktop atualizado)." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "ERRO: Docker daemon nao esta rodando (open -a Docker)." >&2
    echo "       Ou rode nativo: ./start.sh native" >&2
    exit 1
  fi

  # ── Multi-clone drift audit (KB § PATTERNS/containerization.md § 12b.1). ──
  # Any running noctus-* container whose bind-mount Source is OUTSIDE
  # $ROOT_DIR (this script's repo) means a sibling clone owns the runtime.
  # Edits in THIS clone are invisible to that container — a silent stale-
  # code hazard. Refuse to proceed; the user fixes by either recreating
  # the offending container from here (`docker compose up -d --build
  # <slug>`) or invoking start.sh from the canonical clone instead.
  audit_clone_alignment() {
    local offenders=()
    local containers
    containers="$(docker ps --filter "name=noctus-" --format '{{.Names}}' 2>/dev/null || true)"
    [[ -z "$containers" ]] && return 0
    while IFS= read -r c; do
      [[ -z "$c" ]] && continue
      # Bind-mount Source paths for this container — newline-separated.
      local sources
      sources="$(docker inspect "$c" --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}}{{println}}{{end}}{{end}}' 2>/dev/null || true)"
      while IFS= read -r src; do
        [[ -z "$src" ]] && continue
        # Docker Desktop on macOS reports bind Sources prefixed with
        # /host_mnt (the VM bridge). Normalize so the prefix-comparison
        # against $ROOT_DIR matches the underlying host path.
        local norm="${src#/host_mnt}"
        # Allow infra mounts (host paths under /var, /tmp, /Users/*/Library, etc.
        # are not repo clones). Only flag sources that LOOK like a clone of this
        # repo: contain "/NoctusAI/" but don't start with $ROOT_DIR.
        if [[ "$norm" == *"/NoctusAI/"* && "$norm" != "$ROOT_DIR"/* ]]; then
          offenders+=("$c  ←  $src")
        fi
      done <<< "$sources"
    done <<< "$containers"
    if [[ ${#offenders[@]} -gt 0 ]]; then
      echo "" >&2
      echo "ERRO: multi-clone drift detected — containers bind-mount a SIBLING clone:" >&2
      printf '  %s\n' "${offenders[@]}" >&2
      echo "" >&2
      echo "  Canonical clone (this script): $ROOT_DIR" >&2
      echo "  Each offender runs code from a different tree than you edit here." >&2
      echo "  Fix per KB § PATTERNS/containerization.md § 12b.1:" >&2
      for line in "${offenders[@]}"; do
        local slug="${line%%  *}"; slug="${slug#noctus-}"
        echo "    docker compose stop $slug && docker compose rm -f $slug && docker compose up -d --build $slug" >&2
      done
      echo "" >&2
      exit 1
    fi
  }
  audit_clone_alignment

  PRODUCTS_COMPOSE=(compose -f "$ROOT_DIR/docker-compose.yml")     # noctusai-products
  INFRA_COMPOSE=(compose -f "$ROOT_DIR/docker-compose.infra.yml")  # noctusai-infra

  # The shared fabric is created ONCE, outside any single compose project
  # (the two-project split makes `noctus-net` external).
  ensure_net() {
    if ! docker network inspect noctus-net >/dev/null 2>&1; then
      echo "[net] criando rede compartilhada externa 'noctus-net'"
      docker network create noctus-net >/dev/null
    fi
  }

  # Shared seed base images — built ONCE before product images so the
  # heavy common layers are cached a single time, not per product.
  build_bases() {
    echo "[base] garantindo imagens base do seed (noctus-seed-*-base)..."
    bash "$ROOT_DIR/scripts/infra/build-base-images.sh" "${NOCTUS_IMAGE_TAG:-dev}"
  }

  print_fleet_urls() {
    echo ""
    echo "============================================"
    echo "  Containers rodando (1 por produto — API + SPA na mesma porta):"
    local entry name bp
    for entry in "${PRODUCTS[@]}"; do
      IFS=':' read -r _slug name bp _fp <<< "$entry"
      echo "  $name → http://localhost:$bp"
    done
    echo "============================================"
  }

  # Cold-boot CPU-contention guard. Each product's `runtime-watch`
  # entrypoint runs an initial `vite build` before uvicorn answers; N
  # simultaneous rollup builds oversubscribe CPU (observed 2026-05-19:
  # 9 cold builds → load ~2.3x cores → minutes-long convergence, all
  # containers flip `unhealthy` inside the healthcheck window though
  # nothing failed). Bring products up in core-sized waves, gating each
  # wave on the prior wave going `healthy` (uvicorn answering ⇒ that
  # product's `vite build` is done ⇒ its CPU is freed), so aggregate
  # load stays ≈ cores instead of 2.3x over. One-time tax: once `dist/`
  # exists the watch loop keeps it warm, so per-product single-click
  # restarts (the normal workflow) are unaffected. Tunables:
  # NOCTUS_BOOT_BATCH (wave size) · NOCTUS_BOOT_WAVE_TIMEOUT (per-wave
  # gate ceiling, seconds; on timeout it proceeds — slow ≠ failed).
  # KB § PATTERNS/containerization.md § 6a.
  staggered_up() {
    local svcs=("$@") cores batch i wave deadline ready s st
    cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
    batch="${NOCTUS_BOOT_BATCH:-$(( cores / 2 > 1 ? cores / 2 : 2 ))}"
    if [[ ${#svcs[@]} -le $batch ]]; then
      docker "${PRODUCT_ARGS[@]}" up -d "${svcs[@]}"
      return 0
    fi
    echo "[docker] cold-boot stagger: ${#svcs[@]} produtos em ondas de $batch (cores=$cores; override: NOCTUS_BOOT_BATCH)"
    i=0
    while [[ $i -lt ${#svcs[@]} ]]; do
      wave=("${svcs[@]:i:batch}")
      echo "[docker]   onda: ${wave[*]}"
      docker "${PRODUCT_ARGS[@]}" up -d "${wave[@]}"
      i=$(( i + batch ))
      [[ $i -ge ${#svcs[@]} ]] && break          # last wave: nothing to gate for
      deadline=$(( SECONDS + ${NOCTUS_BOOT_WAVE_TIMEOUT:-300} ))
      while :; do
        ready=0
        for s in "${wave[@]}"; do
          st="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "noctus-$s" 2>/dev/null || echo none)"
          [[ "$st" == "healthy" ]] && ready=$(( ready + 1 ))
        done
        [[ $ready -ge ${#wave[@]} ]] && { echo "[docker]   onda saudavel ($ready/${#wave[@]})"; break; }
        if [[ $SECONDS -ge $deadline ]]; then
          echo "[docker]   ⚠ timeout da onda ($ready/${#wave[@]} saudaveis apos ${NOCTUS_BOOT_WAVE_TIMEOUT:-300}s) — prosseguindo; build lento, NAO falha (ver: docker logs noctus-<slug>)" >&2
          break
        fi
        sleep 5
      done
    done
  }

  # ----- mode handling -----
  # NOTE: there is NO `dev` mode. ONE container, ONE shape
  # (project: containerization-single-env). Every local product
  # container builds the `runtime-watch` target with source bind-mounted
  # → `vite build --watch` + `uvicorn --reload` give live feedback with
  # no second container, no `dev` command, no separate project.

  # Subset: first arg is a registered slug → bring up ONLY those products.
  if is_registered_slug "$MODE"; then
    SUBSET=()
    for arg in "$@"; do
      if is_registered_slug "$arg"; then
        SUBSET+=("$arg")
      else
        echo "ERRO: '$arg' nao e um slug registrado." >&2
        exit 1
      fi
    done
    echo "============================================"
    echo "  NoctusAI — subset: ${SUBSET[*]}"
    echo "============================================"
    ensure_net
    build_bases
    docker "${PRODUCTS_COMPOSE[@]}" build "${SUBSET[@]}"
    PRODUCT_ARGS=("${PRODUCTS_COMPOSE[@]}")
    staggered_up "${SUBSET[@]}"
    echo ""
    for s in "${SUBSET[@]}"; do
      IFS=':' read -r _ nm bp _ <<< "$(printf '%s\n' "${PRODUCTS[@]}" | grep "^$s:")"
      echo "  $nm → http://localhost:$bp"
    done
    echo ""
    echo "  ./stop.sh   # parar"
    exit 0
  fi

  echo "============================================"
  echo "  NoctusAI Platform — Docker (modo: $MODE)"
  echo "============================================"

  INFRA_PROFILE=""
  TUNNEL_PROFILE=""
  TUNNEL_SLUG=""
  case "$MODE" in
    fleet|"")      ;;
    redis)         INFRA_PROFILE="redis" ;;
    waha)          INFRA_PROFILE="waha" ;;
    local-db|postgres) INFRA_PROFILE="postgres" ;;
    full)          INFRA_PROFILE="full" ;;
    build)         ;;
    tunnel)
      TUNNEL_SLUG="${2:-}"
      if [[ -z "$TUNNEL_SLUG" ]]; then
        TUNNEL_PROFILE="tunnel-all"
        echo "[tunnel] expondo TODA a frota via cloudflared"
      elif is_registered_slug "$TUNNEL_SLUG"; then
        TUNNEL_PROFILE="tunnel-$TUNNEL_SLUG"
        echo "[tunnel] expondo $TUNNEL_SLUG via cloudflared"
      else
        echo "ERRO: slug '$TUNNEL_SLUG' nao registrado." >&2
        exit 1
      fi
      ;;
    *)
      echo "ERRO: modo desconhecido '$MODE'." >&2
      echo "  Use: fleet | <slug...> | redis | waha | local-db | full | tunnel [slug] | build | native" >&2
      exit 1
      ;;
  esac

  ensure_net
  build_bases

  PRODUCT_ARGS=("${PRODUCTS_COMPOSE[@]}")
  [[ -n "$TUNNEL_PROFILE" ]] && PRODUCT_ARGS+=(--profile "$TUNNEL_PROFILE")

  if [[ "$MODE" == "build" ]]; then
    echo "[docker] rebuild forcado (--no-cache --pull)..."
    bash "$ROOT_DIR/scripts/infra/build-base-images.sh" "${NOCTUS_IMAGE_TAG:-dev}"
    docker "${PRODUCT_ARGS[@]}" build --no-cache --pull
  else
    echo "[docker] buildando imagens de produto (cache hit se ja construidas)..."
    docker "${PRODUCT_ARGS[@]}" build
  fi

  echo "[docker] subindo noctusai-products..."
  ALL_SLUGS=()
  for entry in "${PRODUCTS[@]}"; do ALL_SLUGS+=("${entry%%:*}"); done
  staggered_up "${ALL_SLUGS[@]}"
  # profile-gated tunnels aren't products → bring them up after the
  # staggered product boot (no-op for already-up products).
  [[ -n "$TUNNEL_PROFILE" ]] && docker "${PRODUCT_ARGS[@]}" up -d

  if [[ -n "$INFRA_PROFILE" ]]; then
    echo "[docker] subindo noctusai-infra (profile: $INFRA_PROFILE)..."
    docker "${INFRA_COMPOSE[@]}" --profile "$INFRA_PROFILE" up -d
  fi

  print_fleet_urls
  if [[ "$INFRA_PROFILE" == "postgres" || "$INFRA_PROFILE" == "full" ]]; then
    echo "  Postgres (local) → postgresql://noctus:noctus_local@localhost:5432/noctus"
    echo "    psql → docker exec -it noctus-postgres psql -U noctus -d noctus"
  fi

  # Tunnel URL extraction — wait for cloudflared to log its public URL.
  if [[ "$MODE" == "tunnel" ]]; then
    echo ""
    echo "[tunnel] aguardando URL publica do cloudflared (~10-30s)..."
    extract_tunnel_url() {
      local container="$1" url="" i
      for i in $(seq 1 30); do
        url=$(docker logs "$container" 2>&1 | grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" | head -1 || true)
        [[ -n "$url" ]] && { echo "$url"; return 0; }
        sleep 2
      done
      return 1
    }
    verify_tunnel_url() {
      local url="$1" i
      [[ -z "$url" || "$url" =~ ^\( ]] && return 1
      for i in $(seq 1 15); do
        curl -fsS -o /dev/null --max-time 8 "$url/api/health" 2>/dev/null && return 0
        sleep 2
      done
      return 1
    }
    if [[ -z "$TUNNEL_SLUG" ]]; then
      echo "  URLs publicas:"
      for entry in "${PRODUCTS[@]}"; do
        IFS=':' read -r s _ _ _ <<< "$entry"
        url=$(extract_tunnel_url "noctus-$s-tunnel" || echo "(timeout — docker logs noctus-$s-tunnel)")
        if verify_tunnel_url "$url"; then
          printf "    ✓ %-20s → %s\n" "$s" "$url"
        else
          printf "    ⚠ %-20s → %s  (nao verificada)\n" "$s" "$url"
        fi
      done
    else
      url=$(extract_tunnel_url "noctus-$TUNNEL_SLUG-tunnel" || echo "(timeout)")
      echo ""
      printf "  Public URL (%s): %s\n" "$TUNNEL_SLUG" "$url"
      if verify_tunnel_url "$url"; then
        echo "  ✓ Verificada via curl /api/health → 200 OK"
      else
        echo "  ⚠ URL extraida mas nao respondeu em ~30s (propagacao OU tunnel caiu)."
      fi
      echo "  URL EFEMERA — muda a cada restart do tunnel."
    fi
  fi

  echo ""
  echo "  docker compose -f docker-compose.yml logs -f   # logs da frota"
  echo "  ./stop.sh                                      # parar tudo"
  exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# Native mode (legacy) — uvicorn + vite directly on host.
# Reached only when the user passes 'native' as first arg.
# ──────────────────────────────────────────────────────────────────────
PIDS=()

kill_tree() {
  local pid=$1 children
  children=$(pgrep -P "$pid" 2>/dev/null) || true
  for child in $children; do kill_tree "$child"; done
  kill "$pid" 2>/dev/null || true
}

free_ports() {
  local stale_pids
  stale_pids=$(lsof -ti :$(IFS=,; echo "${PORTS[*]}") 2>/dev/null | sort -u) || true
  if [ -n "$stale_pids" ]; then
    echo "[cleanup] Matando processos orfaos nas portas ${PORTS[*]}..."
    for pid in $stale_pids; do kill_tree "$pid"; done
    sleep 1
  fi
}

cleanup() {
  echo ""
  echo "Parando todos os servicos..."
  for pid in "${PIDS[@]}"; do kill_tree "$pid"; done
  wait 2>/dev/null
  echo "Todos os servicos parados."
  exit 0
}

trap cleanup SIGINT SIGTERM

echo "============================================"
echo "  NoctusAI Platform — modo nativo (legacy)"
echo "============================================"
echo ""

free_ports

ensure_frontend_deps() {
  local dir="$1" name="$2"
  if [ ! -d "$dir/node_modules" ] || [ "$dir/package.json" -nt "$dir/node_modules/.package-lock.json" ]; then
    echo "[$name] Instalando dependencias..."
    (cd "$dir" && npm install --prefer-offline --no-audit --no-fund -q)
  fi
}

VENV="$ROOT_DIR/venv"
if [ ! -d "$VENV" ]; then
  echo "[venv] Criando venv na raiz do repositorio..."
  python3 -m venv "$VENV"
fi
echo "[venv] Instalando dependencias..."
"$VENV/bin/pip" install -q -r "$ROOT_DIR/requirements.txt"

# Seed-version stamp absorbed into the MCP toolkit (scripts-mcp-absorption):
# scripts/stamp-seed-version.sh → noctus.dev.stamp_seed_version.
if [ -x "$VENV/bin/python" ]; then
  "$VENV/bin/python" "$ROOT_DIR/mcp/noctusai/cli.py" --stamp-seed-version || true
fi

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
for url in "${URLS[@]}"; do echo "$url"; done
echo "============================================"
echo ""
echo "Pressione Ctrl+C para parar todos os servicos."
echo ""

wait
