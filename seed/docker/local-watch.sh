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

echo "[local-watch] starting uvicorn --reload on :${PORT}..."
exec uvicorn app.main:app \
    --host 0.0.0.0 --port "${PORT}" \
    --app-dir "products/${SLUG}/backend" \
    --reload \
    --reload-dir "products/${SLUG}/backend" \
    --reload-dir /app/seed
