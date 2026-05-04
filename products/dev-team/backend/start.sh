#!/usr/bin/env bash
# Dev server for dev-team backend.
# Mirrors the canonical pattern across products: uvicorn with --reload,
# product-specific port (8009 — next free after mailing's 8006-8008 range).
set -euo pipefail

cd "$(dirname "$0")"

# Ensure the engine package is importable. Editable install is idempotent;
# falls through quickly when already installed.
if ! python -c "import dev_team" 2>/dev/null; then
  echo "[start.sh] Installing dev_team engine in editable mode…"
  pip install -e ../../../dev_team
fi

exec uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT:-8009}"
