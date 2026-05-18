#!/usr/bin/env bash
# propagate-dockerfiles.sh — regenerate every product's single-container
# backend/Dockerfile from the canonical products/seed/backend/Dockerfile.
#
# Project: containerization-single-container (Phase 2). Seed is the spine;
# products inherit. Substitutions are TARGETED: only `products/seed/` paths
# and the seed backend port (8004) change — the literal "seed" in
# `seed/lib`, `seed/framework`, `@noctusai/seed` refers to the SHARED seed
# tree and must NOT change. Per-product VITE_* + dev-team backend extras
# are spliced. bash 3.x compatible (macOS) — no mapfile.
#
# Usage: bash scripts/propagate-dockerfiles.sh [--check]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CHECK="${1:-}"
python3 - "$CHECK" <<'PY'
import sys, pathlib

check = sys.argv[1] == "--check"
canon = pathlib.Path("products/seed/backend/Dockerfile").read_text()

# slug → backend port (mirrors vite.config.factory PRODUCT_MAP + start.sh)
PRODUCTS = [
    ("core", "8000"), ("erp-imobiliario", "8001"),
    ("personal-finance", "8002"), ("therapy-platform", "8003"),
    ("daily-life", "8005"), ("adconnect", "8007"), ("dev-team", "8009"),
    ("social-wiring", "8011"),
]

# VITE_SUPABASE_* are boot-critical + baked at build for EVERY product
# (the seed FE hard-throws on empty). They prefix every product's VITE
# block — distinct from VITE_BACKEND_API_URL, which stays runtime-
# detected (never baked). Only the product-varying URL args differ.
SEED_VITE_SUPABASE = (
    "ARG VITE_SUPABASE_URL=\nENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}\n"
    "ARG VITE_SUPABASE_PUBLISHABLE_KEY=\n"
    "ENV VITE_SUPABASE_PUBLISHABLE_KEY=${VITE_SUPABASE_PUBLISHABLE_KEY}\n"
)
SEED_VITE = SEED_VITE_SUPABASE + "ARG VITE_CORE_URL=\nENV VITE_CORE_URL=${VITE_CORE_URL}\n"
VITE = {
    "core": SEED_VITE_SUPABASE
        + "ARG VITE_CORE_API_URL=\nENV VITE_CORE_API_URL=${VITE_CORE_API_URL}\n",
    "erp-imobiliario": (
        SEED_VITE_SUPABASE
        + "ARG VITE_CORE_API_URL=\nENV VITE_CORE_API_URL=${VITE_CORE_API_URL}\n"
        "ARG VITE_CORE_URL=\nENV VITE_CORE_URL=${VITE_CORE_URL}\n"
    ),
}
EXTRA_MARKER = (
    "# {{BACKEND_EXTRA}} — product extras (e.g. dev-team: COPY dev_team +\n"
    "# pip install -e /opt/dev_team). Seed has none.\n"
)
DEVTEAM_EXTRA = (
    "# dev-team: the agno engine, editable-installed alongside the product.\n"
    "COPY dev_team /opt/dev_team\n"
    "RUN --mount=type=cache,target=/root/.cache/pip pip install -e /opt/dev_team\n"
)

# Per-slug pip RUN block. Default = the canonical (all-wheel deps, slim
# runtime has no compiler — correct for ~all products). erp-imobiliario
# (N=1, verified 2026-05-18) pulls `xhtml2pdf → svglib → rlpycairo →
# pycairo`; pycairo has no arm64 wheel so pip source-builds it via meson,
# needing gcc + cairo dev headers. Install AND purge the toolchain in the
# SAME layer → shipped image stays slim. Per-slug seam (mirrors VITE /
# DEVTEAM_EXTRA), NOT a fleet-wide bloat: only erp's generated Dockerfile
# carries the toolchain. If a 2nd product needs a source build, lift this
# into the seed backend base builder instead of growing this dict.
SEED_PIP_RUN = (
    "RUN --mount=type=cache,target=/root/.cache/pip \\\n"
    "    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \\\n"
    "    && pip install -r /tmp/req.clean.txt"
)
PIP_RUN = {
    "erp-imobiliario": (
        "RUN --mount=type=cache,target=/root/.cache/pip \\\n"
        "    apt-get update \\\n"
        "    && apt-get install -y --no-install-recommends gcc pkg-config libcairo2-dev \\\n"
        "    && grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \\\n"
        "    && pip install -r /tmp/req.clean.txt \\\n"
        "    && apt-get purge -y gcc pkg-config libcairo2-dev \\\n"
        "    && apt-get autoremove -y \\\n"
        "    && rm -rf /var/lib/apt/lists/*"
    ),
}

stale = False
for slug, port in PRODUCTS:
    s = canon
    s = s.replace("products/seed/", f"products/{slug}/")
    s = s.replace("PRODUCT_SLUG=seed", f"PRODUCT_SLUG={slug}")
    s = s.replace("8004", port)
    s = s.replace(SEED_VITE, VITE.get(slug, SEED_VITE))
    s = s.replace(SEED_PIP_RUN, PIP_RUN.get(slug, SEED_PIP_RUN))
    s = s.replace(
        EXTRA_MARKER,
        DEVTEAM_EXTRA if slug == "dev-team" else "# (no product extras)\n",
    )
    s = s.replace(
        "seed — CANONICAL thin product image (the reference every product mirrors).",
        f"{slug} — thin product image (generated from products/seed/backend/Dockerfile; edit there + re-propagate).",
    )
    s = s.replace('title="noctus-seed"', f'title="noctus-{slug}"')
    out = pathlib.Path(f"products/{slug}/backend/Dockerfile")
    if check:
        if not out.exists() or out.read_text() != s:
            print(f"STALE: {out}")
            stale = True
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(s)
        print(f"wrote {out} (port {port})")

sys.exit(1 if stale else 0)
PY
