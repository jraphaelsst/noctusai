# product-container-rebuild — Sequential Build Plan

> **Status:** SUPERSEDED 2026-05-20 (never executed) — `KB § PATTERNS/minimum-viable-rebuild.md` made this scope obsolete. Only the modified product (social-wiring) needed a rebuild; the rest catch up lazily on their next own-modify build. Kept for the planning structure as historical reference. See `feedback_minimum_viable_rebuild.md` for the rule that retired this approach.

- **Created:** 2026-05-20
- **Purpose:** Rebuild all product containers after the seed-default canonical-not-coincidence fix (commit `89923eb8`), one product at a time, smallest → biggest. Each fully-validated container becomes the canonical reference for the next.
- **Why sequential:** Parallel rebuilds across ~9 products crashed mid-flight earlier this session. Sequential isolates failures, gives clean error attribution, lets each green container serve as the validated baseline.
- **Trigger doc:** `KB § PATTERNS/seed-canonical-defaults.md` + `KB § PATTERNS/containerization.md § 5c Sync runbook` + `§ 12b Validation-freshness contract`.

---

## Pre-flight (Phase 0)

Required state before starting any product build:

1. **Canonical clone confirmed.** All builds run from `/Users/rapha/Documents/repository/NoctusAI/noctusai/` (this clone). The `start.sh audit_clone_alignment` gate added in commit `89923eb8` will refuse to proceed if any sibling clone (`noctus-fleet/` etc.) holds a bind-mount.
2. **Tree state clean.** `git status` shows the two new commits (`89923eb8` seed-defaults + `962a8103` media-creator-w2-4) landed; no uncommitted work in canonical clone.
3. **No stale containers.** `docker ps -a --filter "name=noctus-"` → either empty, or stop/remove any pre-seed-fix containers (they hold the old `infra.tsx` default that misroutes FE→core).
4. **Infra up.** Redis + WAHA + Postgres ready via `docker-compose.infra.yml` so chatbot/queue-dependent products (social-wiring, therapy-platform) can validate their full surface — start with `./start.sh` to bring up infra first.
5. **Base images rebuilt.** `bash scripts/infra/build-base-images.sh` rebuilds `noctus-seed-backend-base` + `noctus-seed-frontend-base` so the FE base image incorporates the seed `infra.tsx` same-origin default. Every product build downstream inherits this.

---

## Build order — smallest to biggest (LoC, lazy proxy for blast radius)

| # | Product | LoC | Modules | Notes |
|---|---|---:|---:|---|
| 1 | `dev-team` | 2,781 | 0 | Smallest product — fastest signal that the base images and seed default work end-to-end. Meta-product (agno multi-agent dev team UI). |
| 2 | `seed` | 3,594 | 0 | Canonical template product — validates that the seed's own `runtime-watch` Dockerfile change works on itself before applying to consumers. |
| 3 | `daily-life` | 10,101 | 0 | Small product, no modules. |
| 4 | `adconnect` | 16,161 | 0 | Light footprint. |
| 5 | `personal-finance` | 21,856 | 0 | Medium product, gamification-heavy. |
| 6 | `core` | 25,385 | 0 | **Special**: control-plane. Was the only product the bad default `localhost:8000` accidentally worked for — must explicitly verify it doesn't regress to dependent on its own port literal. |
| 7 | `social-wiring` | 41,165 | 4 | Module count drives surface area. Validate `media_creation` (just-committed) + scheduling + email_marketing + youtube. |
| 8 | `therapy-platform` | 63,694 | 0 | Whatsapp-chatbot heavy; needs WAHA infra. |
| 9 | `erp-imobiliario` | 103,941 | 0 | Largest blast radius. Last on purpose — pilot products (`erp-imobiliario`, `therapy-platform`, `social-wiring`) all validate the seed change works at scale before non-pilot products commit. |

---

## Per-product validation contract (the "100%-validated" gate)

For each product in the order above:

```bash
# 1. Build the single-product container (canonical clone enforced by start.sh)
./start.sh <slug>
# OR (equivalent, lower-level):
docker compose up -d --build <slug>

# 2. Wait for ready signal — uvicorn startup line in logs
docker logs noctus-<slug> 2>&1 | grep -E "Application startup complete|Uvicorn running" -m1

# 3. Bind-mount audit — confirm canonical clone owns the runtime
docker inspect noctus-<slug> --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}}{{println}}{{end}}{{end}}' \
  | grep -v "^$" | sed 's|/host_mnt||g'
# Expected: every Source under /Users/rapha/Documents/repository/NoctusAI/noctusai/

# 4. Watched-dirs audit — uvicorn reload covers the changed dirs
docker logs noctus-<slug> 2>&1 | grep "Will watch"

# 5. Live probe — endpoints that exercise the seed-default fix
PORT=$(grep PRODUCT_PORT products/<slug>/backend/Dockerfile | head -1 | awk '{print $NF}')
curl -sf -o /dev/null -w "health: HTTP %{http_code}\n" http://localhost:$PORT/api/health
curl -sf -o /dev/null -w "spa  : HTTP %{http_code}\n" http://localhost:$PORT/
curl -sf -o /dev/null -w "api404: HTTP %{http_code}\n" http://localhost:$PORT/api/_does_not_exist
# Expected: 200 / 200 / 404 (the last MUST be 404 not 200 — that's the 63b98284 SPA-fallback fix)

# 6. FE same-origin probe — confirm the bundled FE points at same-origin not localhost:8000
docker exec noctus-<slug> sh -c 'grep -o "VITE_BACKEND_API_URL[^\"]*" dist/assets/index-*.js 2>/dev/null | head -1' || true
# If the bundle was built with the fix, this either returns empty (define-replaced)
# or the literal "" — never "http://localhost:8000".
```

**Pass condition:** all 5 commands green, no errors in logs, no toasts on the FE smoke test.
**Fail condition:** STOP. Diagnose. Fix-on-contact if root is on the seed; surface + advise if root is product-specific.

---

## Methodology — "use 100%-validated containers as canonical reference"

After each product passes:
- Tag a known-good docker image: `docker tag noctus-<slug>:latest noctus-<slug>:validated-2026-05-20`
- Brief note in this file's §3 Change Log (built date · validated tail · any divergence found).
- The next product's build uses this product's container as a *reference* — if it fails an analogous probe that the previous green container passed, the regression is product-specific, not seed-wide.

This is the same idea as the "pilot-products-first refactor cadence" rule from `KB § PATTERNS/project-execution.md § 2.12` — prove on small first, expand.

---

## Stop conditions

Halt the sequential build and surface to user if:

- **A product fails the contract AND the root cause looks seed-wide** (e.g. all subsequent products would likely fail the same way). Don't waste cycles on the rest.
- **A product fails AND fix is hard-to-reverse / needs decision** (e.g. compose schema change, base image divergence). Surface with recommendation + named destination.
- **Disk usage crosses 80% during the run** (per `disk-usage-monitor.sh` thresholds). Mole-sweep first.

Otherwise: log the issue, fix-on-contact, continue.

---

## §3 Change Log (filled during execution)

| Product | Built | Probes | Image tag | Notes |
|---|---|---|---|---|
| dev-team | ⏳ | — | — | — |
| seed | ⏳ | — | — | — |
| daily-life | ⏳ | — | — | — |
| adconnect | ⏳ | — | — | — |
| personal-finance | ⏳ | — | — | — |
| core | ⏳ | — | — | — |
| social-wiring | ⏳ | — | — | — |
| therapy-platform | ⏳ | — | — | — |
| erp-imobiliario | ⏳ | — | — | — |

---

## §4 Methodology refinement (filled at close)

After all 9 products green, capture:
- What the parallel-build crash actually was (resource exhaustion? base image race? compose dependency?).
- Whether sequential build is the steady-state right answer or if a controlled `--parallel <N>` flag would also work.
- Any seed-side issues caught that need codifying (e.g. base-image rebuild ordering rule).
- Three-way sync update to `KB § PATTERNS/containerization.md`.
