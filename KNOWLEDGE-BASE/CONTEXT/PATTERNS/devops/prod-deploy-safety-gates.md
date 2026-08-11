# Prod-deploy safety gates — the closed-loop on what shipping to prod ACTUALLY needs

**What it is.** A composite of 4 keepers + 1 aggregator + 1 mirror tool that together form the **pre-deploy gate** for the prod cache transformation. Codified 2026-05-26 evening as Phase 3.4 of `project-history/roadmaps/cache-backend-portability-2026-05.md`.

**Why.** Trigger T2 (hosted noc prod deployment) + T3 (CI runs embedding gates) of the roadmap both fired. The prod cache (containerized Postgres+pgvector) is now load-bearing — a stale or unreachable prod cache means CI flake AND prod-noc-agent failure. The safety gates surface the failure modes BEFORE the deploy.

## The 4 keepers + 1 aggregator

| # | Keeper | Severity | When it fires |
|---|---|---|---|
| 1 | `check_prod_cache_reachable` | **high** | When `NOCTUS_CACHE_BACKEND=postgres` AND (psycopg2 import fails OR connect fails OR pgvector extension missing). NO-OP on sqlite default. |
| 2 | `check_cache_backend_env_matches_environment` | warning | When detected env (CI / container / local-dev) disagrees with `NOCTUS_CACHE_BACKEND`. Advisory — manual override is legitimate. |
| 3 | `check_drift_shield` | warning | When OPEN auto-improvement entries (s1/s2/s3, not yet closed/s4) touch files in the `origin/prod..origin/main` diff. Reminds architect to triage BEFORE shipping the changes. |
| 4 | `check_slip_shield` | warning | When ≥2 s2-memory entries on the same target (codification slip) AND that target is in the deploy diff. Pattern: emerging issue never promoted. |
| **5** | **`check_pre_deploy_gate`** | composite | Runs all 4 above. Exit 1 only if ANY high-severity issue surfaces (advisory ones never block the deploy). |

## The mirror tool

`noctus.dev.cache_deploy_mirror` — snapshots local SQLite → prod Postgres+pgvector. Per-cache TRUNCATE+INSERT in a single transaction. Vectors transferred verbatim (sqlite-vec BLOB → pgvector `vector(N)` via struct.unpack + pgvector adapter). **NO re-embed cost** at deploy time.

Companion: `noctus.dev.init_prod_cache_schema` — runs the `IF NOT EXISTS` DDL bootstrap. ONE-TIME per fresh Postgres container.

## Deploy runbook (the integrated flow)

```bash
# 0. Pre-flight: dev is clean + ready
python mcp/noctusai/cli.py --check-pre-deploy-gate     # composite — must pass

# 1. Bless dev → main (sacred-main gate)
noctus.dev.release stage=bless           # dry-run first
noctus.dev.release stage=bless confirm=True

# 2. Promote main → prod (sacred-main gate)
noctus.dev.release stage=promote         # dry-run first
noctus.dev.release stage=promote confirm=True

# 3. Deploy on VPS (over SSH)
noctus.dev.deploy_pull target=origin/prod confirm=False
noctus.dev.deploy_pull target=origin/prod confirm=True

# 4. On the VPS: bring up the cache container (one-time per fresh stack)
docker compose -f deploy/fleet/compose.infra.prod.yml --profile cache up -d
# OR --profile full to bring up redis + waha + cache together

# 5. Bootstrap the cache schema (one-time after step 4)
NOCTUS_CACHE_BACKEND=postgres NOCTUS_CACHE_POSTGRES_DSN=postgresql://... \
  python mcp/noctusai/cli.py --json -c "from tools.noctus.dev.cache_deploy_mirror import init_prod_cache_schema; print(init_prod_cache_schema())"
# (or via MCP tool: noctus.dev.init_prod_cache_schema)

# 6. Mirror local → prod cache (every deploy)
noctus.dev.cache_deploy_mirror confirm=False    # dry-run plan
noctus.dev.cache_deploy_mirror confirm=True     # actual mirror

# 7. Verify
NOCTUS_CACHE_BACKEND=postgres python mcp/noctusai/cli.py --check-prod-cache-reachable
```

## What this DOESN'T gate (intentional)

- **It does NOT gate on test green** — that's `noctusai_pytest` / CI's job (the `test.yml` workflow). The safety gates assume tests passed.
- **It does NOT force-roll the cache** — if mirror fails mid-deploy, prod cache stays at the prior known-good snapshot. Atomic-per-cache transaction.
- **It does NOT prevent stale cache reads** — the auto-freshness mechanism (`post-merge`/`post-checkout` hooks + 3-leg mirror contract) handles that locally; the deploy mirror is the prod analog.
- **Drift-shield and slip-shield are ADVISORY** — they nudge review, not block. Hard-block would conflict with `safety nets become learnings` philosophy (the surfaced pattern IS the methodology working).

## Composes with

- [`cache-backend-portability-2026-05`](../../../project-history/roadmaps/cache-backend-portability-2026-05.md) — the parent roadmap.
- [`prod-cache-container`](prod-cache-container.md) — the pgvector container the keepers verify.
- [`cache-auto-freshness`](../common/cache-auto-freshness.md) — local-side auto-freshness; this is the prod-side analog.
- [`scoped-auto-improvement`](../common/scoped-auto-improvement.md) — drift-shield + slip-shield consume the same auto-improvement.ndjson.
- [`branching-and-merging`](../architect/branching-and-merging.md) — the bless/promote gates this composes with.
- [`ci-embedding-cache-gate`](ci-embedding-cache-gate.md) — the CI consumer of `check_prod_cache_reachable` (T3 of roadmap).

## CLI

```bash
# Individual keepers
python mcp/noctusai/cli.py --check-prod-cache-reachable
python mcp/noctusai/cli.py --check-cache-backend-env-matches-environment
python mcp/noctusai/cli.py --check-drift-shield
python mcp/noctusai/cli.py --check-slip-shield

# Composite (use in CI / pre-deploy)
python mcp/noctusai/cli.py --check-pre-deploy-gate
```

## MCP tools

- `noctus.dev.cache_deploy_mirror(confirm=False, only=[...], dsn=None)` — local → prod transfer.
- `noctus.dev.init_prod_cache_schema(dsn=None)` — one-time DDL bootstrap.

## History

- **2026-05-26 evening**: All 4 keepers + composite + mirror tool shipped together as Phase 3.4 of the cache-backend-portability roadmap, gated on triggers T1+T2+T3+T5 all firing simultaneously (multi-environment hosted noc deployment).

## The frontend leg — every other gate is blind to the bundle (2026-08-11)

The deploy gates form a chain, and until now the chain **stopped at the HTML**:

| Gate | Proves | Blind to |
|---|---|---|
| `deploy_image` health probe | the CONTAINER is up | everything served |
| `/api/health` (internal + edge) | the BACKEND answers | the frontend entirely |
| public edge 200 | the HTML **shell** was served | whether the JS ever loaded |

A bundle that 404s, is truncated, or is served as the SPA HTML fallback leaves
**all three green while every user sees a blank page**. Under PROD-ONLY there is
no dev fleet to catch it first, and a UI-library change (the react-router v6→v7
fleet migration) is exactly the shape that exercises it.

`noctus.dev.spa_smoke` / `--spa-smoke` closes it. Per active product:

1. shell 200, carries `<div id="root">` **and** an `/assets/*.js` tag
2. that bundle 200, ≥10 KB, and **actually JS** — not the HTML fallback
3. a **deep link** 200 (client routing / SPA rewrite wired)
4. optional `expect_absent` / `expect_present` bundle markers

**The subtle one is #2.** A missing asset rewritten to `index.html` returns
**200**, so a naive status check passes on a completely broken page. The gate
checks the content type and the leading bytes, not just the status.

Marker assertions are how you prove *what* shipped: `@remix-run/router` exists
only in react-router v6, so `expect_absent=["@remix-run/router"]` proves a v7
bundle actually reached the edge — bytes on the wire, not a build log.

The product set comes from `deploy/fleet/build-scope.txt`, the same file the
build workflow scopes on, so the gate and the build can never disagree about
which products matter.

🔴 **Named limit:** it does **not** execute JavaScript, so an in-component render
crash still passes. It closes the "bundle never arrived / arrived wrong" class —
the failure a *deploy* introduces. Catching a render crash needs a headless
browser; that is a deliberate non-goal, and stating it here is the point (a gate
whose limits are undocumented gets trusted for things it never checked).

Wired as `noc-ship` step **6a**, immediately after the backend smoke. Pinned by
`mcp/noctusai/tests/test_spa_smoke.py` (20 tests, mostly NEGATIVE — the live
fleet is green, so a happy-path-only suite would prove nothing). That suite also
carries an autouse guard that fails any test attempting a real network call:
while writing it, one test omitted its fake and silently smoke-tested LIVE PROD,
passing for the wrong reason.
