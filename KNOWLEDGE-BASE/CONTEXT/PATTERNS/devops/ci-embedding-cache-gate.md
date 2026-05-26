# CI embedding-cache-gate

> **Trigger T3** of roadmap `cache-backend-portability-2026-05.md` — CI runners sharing the prod pgvector cache instead of each paying the full embed cost per run.

## Purpose

Without a shared cache every CI runner rebuilds the kb-embeddings + code-embeddings caches from scratch on each PR: ~$0.10 OpenAI + ~5 min of wall-clock per run. With a shared prod Postgres cache the FIRST runner pays the cost; every subsequent PR reads the already-computed rows → zero embed cost, sub-second retrieval.

`.github/workflows/embedding-cache-gate.yml` wires CI to the shared cache ∧ runs the vector-using keeper gates that would otherwise be cost-prohibitive per-run.

## Graceful-degrade posture

**Phase 3 not yet fully shipped**: the `PostgresCacheBackend` + the `--check-prod-cache-reachable` CLI flag arrive in a sibling slice (PGV-COMPOSE). Until that slice is integrated ∧ the GH secret is provisioned:

- Every gate in the workflow runs with `continue-on-error: true`.
- Cache unreachable ⇒ workflow warns ∧ exits 0 (no PR block).
- Steps that call unshipped CLI flags log a non-zero exit that is absorbed.

Once the prod cache is live ∧ the baseline is seeded, the tech-lead removes `continue-on-error` from each gate to harden it.

## Required GH secrets

| Secret | Value shape | Provisioned by |
|---|---|---|
| `NOCTUS_CACHE_POSTGRES_DSN` | `postgresql://user:pass@host:port/dbname` | tech-lead, on first deploy of the prod cache container |

Secret MUST be set in repo `Settings → Secrets and variables → Actions` before the workflow can connect to the shared cache. Until it is set, `NOCTUS_CACHE_POSTGRES_DSN` is empty ∧ the backend silently falls back to local SQLite (graceful-degrade via the `get_backend()` factory in `cache_backend.py`).

## Cost characteristic

```
Run N=1  →  first CI runner: pays $0.10 embed + seeds cache rows
Run N≥2  →  subsequent PRs: $0 embed (reads existing rows from shared cache)
```

Estimated savings: ~$0.10 × (CI_runs − 1) per PR cycle. At 10 PRs/day that is ~$0.90/day → ~$27/month. Marginal at current scale; matters once T1/T2 fires and multiple architects are pushing concurrently.

The `--vector-costs-total --since=<PR_created_at>` step reports per-PR cumulative cost as advisory output on the GH Actions summary.

## Workflow shape

```
on: pull_request (paths: KB/**/*.md + mcp/**/*.py + noctusai_lib/**/*.py + products/seed/**)
    workflow_dispatch

concurrency: cache-gate-${{ github.ref }} (cancel-in-progress)

job: embedding-cache-validate
  1. checkout + python 3.11 + pip install mcp/noctusai/requirements.txt
  2. --check-prod-cache-reachable          (continue-on-error until sibling slice)
  3. export NOCTUS_CACHE_BACKEND + DSN     (from secrets.*)
  4. --check-kb-vector-canonical           (continue-on-error until Phase 3 live)
  5. --check-code-embeddings-cache-freshness (continue-on-error)
  6. --vector-costs-total --since=...      (advisory, continue-on-error)
```

Secrets discipline: `NOCTUS_CACHE_POSTGRES_DSN` comes ONLY from `${{ secrets.* }}` — never inlined, never logged.

## Composes with

- `project-history/roadmaps/cache-backend-portability-2026-05.md` — the migration plan + trigger table; this pattern implements T3.
- `KB § CONTEXT/PATTERNS/common/cache-auto-freshness.md` — the closed-loop propagation umbrella; CI is an additional freshness boundary.
- `KB § CONTEXT/PATTERNS/devops/ci-security-gates.md` — the canonical CI job shape (action pin + SARIF + exit-code gate); this workflow follows the same job-anatomy convention.
- sibling slice `prod-cache-container.md` (PGV-COMPOSE) — ships the `PostgresCacheBackend` + compose service + `--check-prod-cache-reachable` CLI flag that this workflow calls.
