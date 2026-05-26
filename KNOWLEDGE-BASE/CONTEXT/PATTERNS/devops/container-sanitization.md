# Container sanitization — the canonical cleanup procedure

**The class.** Stale Docker artifacts accumulate as the dev fleet evolves: dangling images from rebuilds, orphan anonymous volumes from `rm -fv` recreates, named volumes from absorbed/deprecated projects, build cache stale relative to current images, even latent stale-base bugs hidden behind runtime-accumulated `node_modules` (the [[base-image-dep-freshness]] class). Without a procedure, this either grows unbounded (disk fills, the `docker rm -fv` footgun exposes latent bugs at the worst time) or gets pruned recklessly (data loss on the wrong DB volume). This doc is the canonical sanitization procedure — what the `devops-engineer` runs, and what the tech-lead follows inline.

**Born:** 2026-05-25 — a dev-infra cleanup session reclaimed ~17.6 GB through the procedure below, surfaced + codified the base-image-dep-freshness gate, and broadened the sweep tools to handle any registered `.claude/worktrees/*`. This doc captures that procedure so it's reproducible without re-learning.

## When to fire
- Reclaiming disk space (the standing trigger).
- After a fleet rename / migration (this session's catalyst: postgres removal + `dev-*` prefix).
- After a stale-image bug fires (a clean recreate exposed a missing dep) — sanitize + verify the codified gate.
- Pre-deploy / pre-handoff hygiene.
- Periodically (any noisy `docker system df`).

## The procedure

### 1 · Inspect (read-only, classify before acting)

```bash
docker system df                 # overview: images / containers / volumes / build cache + reclaimable
docker images -f dangling=true   # the <none>:<none> set — always safe
docker images                    # tagged set — classify by purpose (running / foundation / stale)
docker volume ls                 # all volumes; cross-reference with in-use:
docker ps -q | xargs -I{} docker inspect {} --format \
  '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{println}}{{end}}{{end}}' | sort -u
```

**Classify every artifact into one of**:

| Class | Example | Action |
|---|---|---|
| **Dangling image** (`<none>:<none>`) | image-rebuild leftovers | safe auto-remove |
| **Orphan anonymous volume** (64-hex name, not in-use) | old container `node_modules` cache | safe auto-remove |
| **Stale build cache** | layer cache for replaced images | safe auto-remove |
| **Closed-project named volume** | `chatbot-docker_*`, `whatsapp-google-scheduling_*` (absorbed); `<old-project>_*` from a rename | **confirm with tech-lead** (data-bearing) |
| **CLI-managed image set** | `public.ecr.aws/supabase/*` (Supabase local-stack) | **confirm** (re-pull cost; CLI manages it) |
| **Stale tagged product image** | `noctus-<slug>:dev` not currently running, pre-base-fix | **confirm** (rebuilds on next start) |
| **Protected named volume** | `dev-noctusai-infra_waha_sessions` (WhatsApp session; losing = re-pair) | **NEVER auto-remove** |
| **In-use** (running container) | the 6 healthy dev containers + their images/volumes | NEVER touched (Docker protects) |
| **Build foundation** | `noctus-seed-{backend,frontend}-base:dev` + `node:20-alpine` + `python:3.11-slim` | **necessary, keep** — removing forces slow re-pull/rebuild |

### 2 · Safe auto-remove (regenerable, zero data loss)

```bash
docker image prune -f            # dangling only (the <none>: tags)
docker builder prune -f          # UNUSED build cache; keeps cache backing current images (NOT `-a` — that nukes in-use cache, slows next build)
docker volume prune -f           # Docker 23+: ANON unused only (named survive); pre-23: `--filter` or rm explicit
# this-session's rename leftovers (e.g. old-project named volumes that are caches):
docker volume rm <old-project>_seed_framework_fe_nm   # regenerable node_modules cache
```

### 3 · Confirm with the tech-lead before removing

- **Data-bearing volumes** of deprecated/absorbed projects (DB / WAHA sessions / n8n data). Irreversible.
- **CLI-managed image sets** (Supabase local-stack ~6 GB, etc.). Re-pull cost; the CLI may need them later.
- **Stale tagged product images** (e.g. `noctus-<slug>:dev` not running). Rebuilds on next start — no data loss, but the user may want them for fast resume.

Surface as a single multi-select question — let the user pick what to also remove.

### 4 · Aggressive deep-clean (only on explicit "remove all not in use")

```bash
docker volume prune -a -f        # ALL unused volumes (named too); in-use survive
docker image prune -a -f         # ALL unused images; protects only images run by a container
```

⚠️ This **also removes the build foundation** (seed bases + node/python/alpine). The next `./start.sh` / product rebuild re-pulls those (~700 MB) + rebuilds the seed bases once (a few minutes; the build-time dep-completeness gate runs then). One-time cost; steady-state recovers. Document this trade-off when surfacing.

### 5 · Recreate without re-exposing latent bugs (the `docker rm -fv` footgun)

`docker rm -fv <product>` drops the container's **anonymous `node_modules` volumes** (the arm64/glibc isolation vols). Recreate re-seeds them from the **image layer** — which exposes any base-image staleness (the dep your `package.json` declared was actually missing from the cached base; the runtime-accumulated anon volume was the only place it lived). See [[base-image-dep-freshness]].

**Prefer**:
```bash
docker compose -f docker-compose.yml up -d --build --renew-anon-volumes <slug>...
```
This rebuilds the product image FROM the (presumed-fresh) base, recreates the container, and re-seeds anon volumes from the freshly-built image — turning a silent stale-base into a loud build failure (the codified gate in `build-base-images.sh` catches it).

When the base itself is suspect (post-prune, post-dep-add): `bash scripts/infra/build-base-images.sh dev` first (the gate verifies declared seed-FE deps actually resolve in the built image; fails LOUDLY otherwise), then the product recreate.

### 6 · Verify

- `docker ps --filter "name=dev-noctus" --format '{{.Names}}\t{{.Status}}'` — all expected containers, all `(healthy)`.
- A per-product health probe (`docker exec <c> curl -fsS http://localhost:<port>/api/health`) when the docker healthcheck is mid-cycle (the `unhealthy` label is stale until the next interval).
- **PROD untouched**: `noctus.vps.ps` — plain `noctus-*` names on the VPS, all `(healthy)`. Local sanitization is local; prod is on a different machine + a different compose project (`noctusai-products-prod` vs `dev-noctusai-products`).
- `docker system df` re-run — reclaimable should be ≈ 0 if "keep only running + necessary" was the goal.

### 7 · Hardening pass (always-on)

Every gap surfaced during this sanitization → codify same session (`KB § PATTERNS/common/methodology-codification-pipeline.md`). The 2026-05-25 session surfaced + codified:
- **`base-image-dep-freshness`** ([[base-image-dep-freshness]]) — the build-time dep-completeness gate in `build-base-images.sh`.
- **Sweep-tool broadening** — `cleanup_stale_worktrees` + `mole` now handle any registered `.claude/worktrees/*`, not just `agent-*` (orphan-detection stays `agent-*`-conservative because unregistered dirs have no merge gate).

Both fixes mean THIS procedure is now self-defending: the gate catches the next stale-base before recreate exposes it; the broadened sweep catches the next non-agent-named worktree before it falls through to a bare `git worktree remove`.

## Anti-patterns

- **`docker rm -fv` on a product without verifying base freshness** — re-exposes stale-image deps (the [[base-image-dep-freshness]] class). Prefer `up --renew-anon-volumes` + the dep-completeness gate.
- **`docker volume prune -a -f`** without confirmation — removes data-bearing named volumes (DB / sessions) silently. The default `docker volume prune -f` is anon-only (Docker 23+) and safe.
- **`docker image prune -a -f`** as the default — removes the build foundation, slowing the next build for marginal reclaim. Use `-f` (dangling only) by default; `-a` only on explicit "deep clean."
- **Deleting volumes by name pattern** — `whatsapp-google-scheduling_postgres_data` looks deprecated, but contains DB data. Per the storage-hygiene reversibility test: no compose file references AND no container mounts AND tech-lead confirms data-loss-OK → then safe.
- **Pruning while a container is stopped but not removed** — `docker volume prune` will NOT touch in-use volumes, but a stopped container's anon vol is still attached. Recreate or rm the container first if you mean to drop its anon vol.

## Verification of this procedure

This doc IS the procedure the 2026-05-25 cleanup ran. Outcomes:
- Reclaimed ≈ 17.6 GB across dangling images, build cache, anon volumes, deprecated named volumes, and the explicit-confirm tier (Supabase + erp + cross-project DBs).
- Zero data loss (the protected `dev-noctusai-infra_waha_sessions` survived; the user confirmed every data-bearing removal).
- Surfaced + codified the base-image-dep-freshness class.
- Prod fleet (VPS) untouched + verified healthy after.

## Siblings · depth

`KB § PATTERNS/devops/containerization.md` (single-container architecture) · `KB § PATTERNS/devops/containerization-operations.md` (debug runbook + the codified-bumps catalog) · `KB § PATTERNS/devops/base-image-dep-freshness.md` (the gate this procedure relies on) · `KB § PATTERNS/common/storage-hygiene.md` (`noctus.dev.mole` for fs-level; this doc for docker-level) · agent `devops-engineer` (runs this) · skill `noc-container-debug` (debug entry point) · skill `noc-hygiene` (the broader scan trio).
