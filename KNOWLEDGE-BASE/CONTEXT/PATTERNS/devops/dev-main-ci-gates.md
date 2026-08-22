# The dev→main process — consistent, CI-enforced gates

> **One-screen answer to "how does code get from a change to production, and what proves it's safe?"** The gates are **automated** — "is it green?" is answered by CI, never by a human hand-running anything (the *unenforced-gate-is-silent-debt* rule; memory `feedback_unenforced_gate_is_silent_debt`). This doc is the consolidated map; the legs live in the per-gate docs linked below.

## Branch model

- **`dev`** = integration. Everyday work lands here (via `noctus.dev.task_branch` worktrees off `origin/dev`, integrated clean). → `KB § PATTERNS/common/branching.md`.
- **`main`** = production, **sacred**. Only reached by an explicit, gated bless→promote. → `KB § PATTERNS/architect/branching-and-merging.md § 0`.

## The CI gates (what runs, when)

Every push/PR is gated automatically by GitHub Actions. The full set:

| Workflow | Trigger | What it gates |
|---|---|---|
| **`test.yml` — Tests & Build** | push/PR to `main`,`dev` | product backend pytest (core/erp/pf) · frontend builds · e2e · `docker-compose` validate · **security** (Trivy fs, bandit, gitleaks) · **`mcp-toolkit-tests`** — the dev toolkit's own ~2.6k-test suite (hermetic, no live key), added 2026-05-31 to close the no-CI-gate gap |
| **`seed-typecheck.yml`** | push/PR to `main`,`dev` | seed lib + framework typecheck — validates the `dev` tip pre-bless |
| **`embedding-cache-gate.yml`** | PR (seed/embedding paths) | validates the shared prod embedding cache is reachable + fresh (conditional gate — hard-fail when the validation surface is up, soft-fail on fork PRs without secrets). → `KB § PATTERNS/devops/ci-embedding-cache-gate.md` |
| **`build-and-push.yml`** | push to `main` | builds + pushes the fleet images to GHCR (the deploy/deliver leg) |

Security-gate specifics: `KB § PATTERNS/devops/ci-security-gates.md`.

## The green requirement + bless→promote

1. **Work integrates to `dev`.** Push triggers `test.yml` + `seed-typecheck`; the **dev tip must be green** on all gates.
2. **Bless → promote** via `noctus.dev.release` (`stage ∈ status | bless | promote`, dry-run unless `confirm`): `status` reports the gate state; `bless` marks the green dev tip as release-candidate; `promote` fast-forwards `main`. `main` is sacred — the tool encodes the gates so promotion is never an ad-hoc merge. → `KB § PATTERNS/architect/branching-and-merging.md § 0`.
   - 🔴 **`bless` REFUSES unless `Tests & Build` is green on the exact `dev` tip** (2026-08-22). Red, still-running, no-run-at-all, and `gh`-unreachable all block equally — REFUSE-NOT-NULL, since "I could not find out" is not "it passed"; a run that was merely *cancelled* carries no verdict and does not pass either. The only exception is a diff touching nothing executable (docs + `project-history/` only), and there is **no override flag** — a red `dev` is fixed on `dev`.
   - **Why it exists:** this doc opened by claiming the gates are automated and "never a human hand-running anything" — and step 1's *green dev tip* was the one gate with no mechanism behind it. On 2026-08-21 `1c83232f` (a `monkeypatch.setattr` on our own module, caught by the compliance-regression gate) was blessed **and promoted to prod** while red, and `dev` then stayed red for 12 commits and ~34h with every checklist reading as satisfied. The gate that catches an unenforced gate has to itself be enforced. → `KB § PATTERNS/common/gate-methodology-sync.md`.
3. **Push to `main`** triggers `build-and-push.yml` → images to GHCR → deploy (`noctus.dev.deploy_pull` / `deploy_image`, with `predeploy_check` for config parity). → `KB § PATTERNS/devops/deploy-config-contract.md`.

## The principle (why this is consistent, not ad-hoc)

- **Every test suite + every regression baseline is CI-gated.** A suite or baseline that exists but isn't run on push is silent debt — it catches nothing until a human happens to run it, and humans don't. The MCP toolkit suite proved this 2026-05-31 (rotted to 12 reds + 15 compliance regressions, unnoticed, with no CI job). → memory `feedback_unenforced_gate_is_silent_debt`.
- **Baselines grow only by accept-with-rationale** (human ratifies), never silently. The compliance gate fails on any NEW high/critical fingerprint vs the committed `compliance_baseline.json`; refreshing it is a deliberate, documented act (e.g. the 2 NotificationBell organ-shims accepted 2026-05-31), and a real issue surfaced by a refresh is **fixed, not accepted** (the MEMORY.md over-cap finding, same day). → `KB § PATTERNS/common/accept-with-rationale.md`.
- **Caches stay fresh by automation** (pre-commit structural · pre-push/post-merge embedding · out-of-repo memory-embeddings always-attempt). Manual `--refresh-*` is the emergency stopgap, never the plan. → `KB § PATTERNS/common/cache-auto-freshness.md`.

## Composes with

`KB § PATTERNS/architect/branching-and-merging.md` (the sacred-main gates) · `KB § PATTERNS/common/branching.md` (worktree integration) · `KB § PATTERNS/devops/ci-security-gates.md` · `KB § PATTERNS/devops/ci-embedding-cache-gate.md` · `KB § PATTERNS/devops/deploy-config-contract.md` · `KB § PATTERNS/common/cache-auto-freshness.md`. Born 2026-05-31 — the consolidation leg of the unenforced-gate lesson.
