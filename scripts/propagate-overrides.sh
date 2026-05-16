#!/usr/bin/env bash
# propagate-overrides.sh — regenerate every product's dev-mode
# docker-compose.override.yml from the canonical
# products/seed/docker-compose.override.yml. Project:
# containerization-single-container (Phase 4). Dev port = backend + 1000.
# The shared base image name (noctus-seed-frontend-base) is PROTECTED
# from slug substitution. bash-3 safe.
#
# Usage: bash scripts/propagate-overrides.sh [--check]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
CHECK="${1:-}"
python3 - "$CHECK" <<'PY'
import sys, pathlib
check = sys.argv[1] == "--check"
canon = pathlib.Path("products/seed/docker-compose.override.yml").read_text()

PRODUCTS = [
    ("core", 8000), ("erp-imobiliario", 8001),
    ("personal-finance", 8002), ("therapy-platform", 8003),
    ("daily-life", 8005), ("mailing", 8006),
    ("adconnect", 8007), ("dev-team", 8009),
    ("imobi-scheduling", 8011), ("youtube-crawler", 8008),
]
BASE_TOKEN = "@@SEED_FE_BASE@@"

stale = False
for slug, bport in PRODUCTS:
    dport = bport + 1000
    s = canon
    # 1. protect the SHARED base image name from slug substitution
    s = s.replace("noctus-seed-frontend-base", BASE_TOKEN)
    # 2. ports (9004 dev distinct from 8004 backend — order-independent)
    s = s.replace("9004", str(dport))
    s = s.replace("8004", str(bport))
    # 3. product path
    s = s.replace("products/seed/", f"products/{slug}/")
    # 4. dev sidecar container_name
    s = s.replace("noctus-seed-frontend-dev", f"noctus-{slug}-frontend-dev")
    # 5. service keys + depends_on ref
    s = s.replace("\n  seed-frontend-dev:\n", f"\n  {slug}-frontend-dev:\n")
    s = s.replace("\n  seed:\n", f"\n  {slug}:\n")
    s = s.replace("\n      - seed\n", f"\n      - {slug}\n")
    # 6. restore the shared base image name
    s = s.replace(BASE_TOKEN, "noctus-seed-frontend-base")
    # 7. header note
    s = s.replace(
        "Dev-mode override — seed-inherited (project: containerization-single-",
        f"Dev-mode override for {slug} — generated from products/seed/ (project: containerization-single-",
    )
    out = pathlib.Path(f"products/{slug}/docker-compose.override.yml")
    if check:
        if not out.exists() or out.read_text() != s:
            print(f"STALE: {out}")
            stale = True
    else:
        out.write_text(s)
        print(f"wrote {out} (backend {bport} / dev {dport})")
sys.exit(1 if stale else 0)
PY
