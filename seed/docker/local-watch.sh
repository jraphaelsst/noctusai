#!/bin/sh
# local-watch — entrypoint for the `runtime-watch` image target.
#
# Project: containerization-single-env. ONE container, ONE shape: this
# single process-group serves the API AND keeps the SPA bundle fresh, so
# editing code (with the source bind-mounted by the local compose) just
# works — no second container, no `dev` command, no separate project.
#
#   1. `vite build` once (blocking) so `dist/` exists BEFORE uvicorn
#      starts — the seed factory mounts the SPA at startup; if dist were
#      absent it would fail-soft to API-only and not remount later.
#   2. `vite build --watch` in the background — rebuilds dist on .ts/.tsx
#      /.css edits (uvicorn's StaticFiles serves the new files on the
#      next request; refresh the browser).
#   3. `uvicorn --reload` in the foreground — reloads on .py edits.
#
# PRODUCT_SLUG / PRODUCT_PORT are baked per product (Dockerfile ENV).
set -e
SLUG="${PRODUCT_SLUG:?PRODUCT_SLUG not set}"
PORT="${PRODUCT_PORT:?PRODUCT_PORT not set}"
FE="/app/products/${SLUG}/frontend"

echo "[local-watch] initial SPA build (${SLUG})..."
( cd "$FE" && npm run build )

echo "[local-watch] starting vite build --watch (background)..."
( cd "$FE" && npm run build -- --watch ) &

# Enforce the contract above (not just attempt it). The background
# `--watch` does its own initial pass that briefly empties dist/ (vite
# emptyOutDir); `exec uvicorn` would otherwise race straight into the
# seed factory's startup-only serve_spa check during that window →
# "dist missing" → SPA fail-soft for the whole container lifetime
# (serve_spa decides once, never remounts). Block until dist/index.html
# is stably present so uvicorn's startup check always sees a mounted SPA.
echo "[local-watch] waiting for dist/index.html to stabilize before uvicorn..."
_stable=0
_waited=0
_timeout="${LOCAL_WATCH_DIST_TIMEOUT:-180}"
while [ "$_stable" -lt 3 ]; do
  if [ -f "$FE/dist/index.html" ]; then
    _stable=$((_stable + 1))            # present this tick
  else
    _stable=0                           # mid-rewrite/empty → reset
  fi
  if [ "$_waited" -ge "$_timeout" ]; then
    echo "[local-watch] ⚠ dist/index.html not stable after ${_timeout}s — starting uvicorn anyway (SPA may be API-only this boot; check the build log)" >&2
    break
  fi
  _waited=$((_waited + 1))
  sleep 1
done
[ "$_stable" -ge 3 ] && echo "[local-watch] dist ready (stable ${_stable}s) — starting uvicorn."

echo "[local-watch] starting uvicorn --reload on :${PORT}..."
exec uvicorn app.main:app \
    --host 0.0.0.0 --port "${PORT}" \
    --app-dir "products/${SLUG}/backend" \
    --reload \
    --reload-dir "products/${SLUG}/backend" \
    --reload-dir /app/seed
