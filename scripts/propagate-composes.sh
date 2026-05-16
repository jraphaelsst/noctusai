#!/usr/bin/env bash
# propagate-composes.sh — regenerate every product's docker-compose.yml
# from the canonical products/seed/docker-compose.yml (single-container
# shape). Project: containerization-single-container (Phase 3). Targeted
# substitution only (slug/port/VITE) — bash-3 safe.
#
# Usage: bash scripts/propagate-composes.sh [--check]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
CHECK="${1:-}"
python3 - "$CHECK" <<'PY'
import sys, pathlib
check = sys.argv[1] == "--check"
canon = pathlib.Path("products/seed/docker-compose.yml").read_text()

PRODUCTS = [
    ("core", "8000"), ("erp-imobiliario", "8001"),
    ("personal-finance", "8002"), ("therapy-platform", "8003"),
    ("daily-life", "8005"), ("mailing", "8006"),
    ("adconnect", "8007"), ("dev-team", "8009"),
    ("imobi-scheduling", "8011"), ("youtube-crawler", "8008"),
]
SEED_VITE = "      args:\n        VITE_CORE_URL: ${VITE_CORE_URL:-}\n"
VITE = {
    "core": "      args:\n        VITE_CORE_API_URL: ${VITE_CORE_API_URL:-}\n",
    "erp-imobiliario": (
        "      args:\n"
        "        VITE_CORE_API_URL: ${VITE_CORE_API_URL:-}\n"
        "        VITE_CORE_URL: ${VITE_CORE_URL:-}\n"
    ),
}

stale = False
for slug, port in PRODUCTS:
    s = canon
    # tunnel target first (carries both slug + port)
    s = s.replace("http://seed:8004", f"http://{slug}:{port}")
    # container/image/tunnel-container names
    s = s.replace("noctus-seed", f"noctus-{slug}")
    # build dockerfile path
    s = s.replace("products/seed/", f"products/{slug}/")
    # tunnel profile
    s = s.replace("tunnel-seed", f"tunnel-{slug}")
    # service key (2-space indent) + depends_on ref (6-space indent)
    s = s.replace("\n  seed:\n", f"\n  {slug}:\n")
    s = s.replace("\n      seed:\n", f"\n      {slug}:\n")
    # ports + healthcheck port
    s = s.replace("8004", port)
    # per-product VITE args
    s = s.replace(SEED_VITE, VITE.get(slug, SEED_VITE))
    # header note
    s = s.replace(
        "Canonical per-product compose fragment — SINGLE CONTAINER.",
        f"{slug} compose — SINGLE CONTAINER (generated from products/seed/docker-compose.yml; edit there + re-propagate).",
    )
    out = pathlib.Path(f"products/{slug}/docker-compose.yml")
    if check:
        if not out.exists() or out.read_text() != s:
            print(f"STALE: {out}")
            stale = True
    else:
        out.write_text(s)
        print(f"wrote {out} (port {port})")
sys.exit(1 if stale else 0)
PY
