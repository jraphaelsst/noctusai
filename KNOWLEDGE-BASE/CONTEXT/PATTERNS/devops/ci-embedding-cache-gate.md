# CI embedding-cache-gate

> **Trigger T3** of roadmap `cache-backend-portability-2026-05.md` — CI runners sharing the prod pgvector cache instead of each paying the full embed cost per run.

## Purpose

Without a shared cache every CI runner rebuilds the kb-embeddings + code-embeddings caches from scratch on each PR: ~$0.10 OpenAI + ~5 min of wall-clock per run. With a shared prod Postgres cache the FIRST runner pays the cost; every subsequent PR reads the already-computed rows → zero embed cost, sub-second retrieval.

`.github/workflows/embedding-cache-gate.yml` wires CI to the shared cache ∧ runs the vector-using keeper gates that would otherwise be cost-prohibitive per-run.

## Graceful-degrade posture (historical context)

**Phase 3 shipped 2026-05-26.** This section captures the original posture during Phase 1-2 (prod cache empty / unreachable); the live workflow now uses the **conditional gating pattern** described below.

Original Phase 1-2 posture: every gate ran `continue-on-error: true` unconditionally. Cache unreachable ⇒ workflow warned ∧ exited 0 (no PR block). Steps calling unshipped CLI flags logged a non-zero exit that was absorbed. Once the prod cache went live ∧ the baseline was seeded, the tech-lead flipped each gate to the conditional shape below.

## Conditional gating pattern (parallel-liveness-aware) — the reusable shape

The Phase-3 flip exposed a generalizable CI pattern: **a gate's strictness should depend on whether the validation surface is reachable in this run**. Two cases:

1. **Push from main repo (secrets available)** — tunnel can open → prod cache is reachable → hard-fail makes sense (real validation)
2. **Fork PR (no secrets — GitHub policy)** — tunnel skipped → cache unreachable → fall back to local sqlite → soft-fail makes sense (advisory only; can't meaningfully validate)

The pattern uses an env-from-step flag exported by the connectivity-establishing step. The gate steps then read the flag inside `continue-on-error`:

```yaml
- name: Open SSH tunnel to prod cache-pg
  if: ${{ secrets.NOCTUS_VPS_DEPLOY_KEY != '' && secrets.NOCTUS_VPS_HOST != '' }}
  run: |
    # ... ssh -L 5432:127.0.0.1:5432 -fN ... ...
    (timeout 5 bash -c 'until nc -z 127.0.0.1 5432; do sleep 0.3; done') \
      || (echo "::warning::tunnel failed; downstream gates soft-fail" && exit 0)
    echo "CACHE_TUNNEL_UP=1" >> $GITHUB_ENV     # ← the load-bearing line

- name: Run KB vector canonical gate
  # Hard-fail when tunnel UP (real prod cache validation).
  # Soft-fail when DOWN (fork PR fallback to sqlite, advisory only).
  continue-on-error: ${{ env.CACHE_TUNNEL_UP != '1' }}
  run: python mcp/noctusai/cli.py --check-kb-vector-canonical
```

**Why this shape generalizes.** It applies to ANY CI gate where:
- The validation requires a secret-gated resource (prod DB / private cache / partner API)
- Fork PRs legitimately cannot reach the resource (GitHub doesn't pass secrets to fork-PR workflows)
- You want hard-fail under conditions where validation is real, without blocking the fork-PR contributor pipeline

The key insight: `continue-on-error` accepts a **GitHub expression**, not just `true`/`false`. Exporting `CACHE_TUNNEL_UP=1` (or any flag) from the connectivity step lets downstream gates conditionally strict themselves. The flag's NAME should reflect the validation-surface being gated (the example uses `CACHE_TUNNEL_UP`; for a partner API it might be `PARTNER_API_REACHABLE`).

**Anti-pattern**: leaving `continue-on-error: true` unconditional even after the validation surface is live. The gate becomes permanently advisory and the methodology layer loses its closed-loop. Once the secret-gated resource is reachable from the main repo's CI, FLIP the gate to conditional hard-fail.

## Required GH secrets

## Required GH secrets

| Secret | Value shape | Provisioned by |
|---|---|---|
| `NOCTUS_VPS_DEPLOY_KEY` | ed25519 private key (restricted via `command="/bin/false",no-pty,no-X11-forwarding,no-agent-forwarding,permitopen="127.0.0.1:5432"`) | tech-lead, on first wire-up of the CI tunnel |
| `NOCTUS_VPS_HOST` | VPS hostname (the `ssh-keyscan` target) | tech-lead, on first wire-up |
| `NOCTUS_CACHE_POSTGRES_DSN` | `postgresql://user:pass@127.0.0.1:5432/dbname` (post-tunnel localhost) | tech-lead, on first deploy of the prod cache container |

Secrets MUST be set in repo `Settings → Secrets and variables → Actions` before the workflow can connect. Until they are, the tunnel step skips ∧ `CACHE_TUNNEL_UP` stays unset ∧ the conditional gating pattern auto-soft-fails downstream gates (graceful-degrade via fall-through, not via explicit `continue-on-error: true`). Sibling KB: `KB § CONTEXT/PATTERNS/devops/ssh-deploy-key-restrictions.md` documents the `restrict`-vs-`permitopen` quirk that caught us during first wire-up.

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
