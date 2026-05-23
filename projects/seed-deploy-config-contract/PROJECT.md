# seed-deploy-config-contract — Project Document

> Living doc. Symbol-first. Phase status `✅`/`⏳`/`❌`/`🔒`. Triage `[F]`/`[R]`/`[A]`.

## 1 · Goal (zero-context)

Make the **dev↔prod silent-fallback class structurally impossible** by giving the seed a **deploy-config contract**: a primitive that resolves environment-divergent config with a **canonical default + fail-loud-if-missing-in-prod** semantic, a **startup guard** that validates required-prod config at boot, a **keeper** that flags seed code deriving runtime behavior from a dev-only artifact without an env fallback, and the **consume doc**. This is the *executable* form of `KB § PATTERNS/dev-prod-parity.md` §2 (the dev↔prod difference checklist) + §4 (verify-in-prod-shape).

**Why it exists.** This deploy cycle the same class bit ≥3× — all **silent** fallbacks to a dev value in prod: nav SSO'd to `http://localhost:8080` (no `PRODUCT_URL_*` override → fell to the localhost DB column), CORS collapsed to localhost in the slim image (registry empty, no env fallback), `infra.tsx` localhost default. The seed already centralizes URL/CORS resolution (`noctusai_lib.config.{product_urls,cors_registry}`) but has **no general "this config is REQUIRED in prod → fail loud, never silently serve the dev value"** primitive. That gap is the recurring root.

**Anticipatory framing (user's "eternalize conflicts as latent features").** Each dev↔prod-divergent knob becomes a seed seam with a canonical default (no-op in dev) + a loud-fail-in-prod guard, consumed by every product → a product **cannot** silently ship a dev value to prod.

## 2 · User intent (quoted)

- *"would it help if we used this kinda solution seed-level? so we get possible conflicts and eternalize them as 'possible future features' that products consume from seed code?"*
- *"file and execute e2e. dispatch parallel agents to help u on non-conflicting tasks. git-branch their work, then evaluate possible duplicates and collisions and resolve, then merge the other agents' work to us. dont commit to main … only push to main when 100% resolved."*

Decisions: build seed-level (not per-product); back-compat-defaulted so dev is a no-op; pilots = erp/therapy/social per pilot-products-first; integration branch `feat/seed-deploy-config-contract`, `main` gated until 100%.

## 3a · Seed-first analysis (REQUIRED, before §6)

- **Cross-product concern** → the right per-product code count is **0**. The primitive lives in `noctusai_lib.config`; every backend inherits it via `create_product_app` (the guard) + direct import (the resolver). Replication-to-seed symmetry: zero per-product config-resolution code.
- **Verify-the-seed-ships-it**: the primitive is NEW seed code (this project ships it); pure-logic + env-only ⇒ **exempt from Fake+Real** (a Fake would exercise the same code as the Real — no IO beyond `os.environ`). Mirrors `product_urls.py` / `cors_registry.py` (pure, env-only, lazy same-layer imports, downward-clean).
- **Back-compat**: `is_deploy_context()` is **False** in dev (no `PRODUCT_URL_*`, no `APP_ENV=production`) ⇒ `require_prod_config` is a no-op, `resolve_config` returns the canonical default. Existing products unaffected until they opt in.
- **Pilots**: erp · therapy · social (Wave 2 / follow-up); non-pilots extend in a later gated wave.

## 5 · Files (by slice — file-disjoint)

| Slice | Files (disjoint) |
|---|---|
| A primitive | `seed/lib/backend/noctusai_lib/config/deploy_config.py` (new) · `seed/lib/backend/tests/config/test_deploy_config.py` (new) |
| B keeper | `mcp/noctusai/tools/noctus/dev/compliance.py` (append 1 fn) · `mcp/noctusai/tests/test_compliance.py` (append 1 Test class) |
| C docs | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/deploy-config-contract.md` (new) |
| Wave-2 guard | `seed/framework/backend/noctusai_seed/app.py` (`create_product_app`, line 51) — architect inline |

INDEX.md + CLAUDE.md rows for slice C's new doc = **architect wires at reconciliation** (avoids 3-way doc collision).

## 6 · Phases / waves

- **✅ Wave 1 (parallel, C1 file-disjoint, no inter-dependency)** — A + B + C dispatched concurrently (isolated worktrees, pushed own branches), merged `--no-ff` (`81fc3cf0`/`7abbc67c`/`970dc522`), authoritatively re-verified in the main checkout (A 17/17 · B 6/6 + meta-keeper 0 + live baseline 0 · C symbol-clean + API↔A consistent). Cross-tree overlay leak recovered (see findings.md).
  - **A — primitive.** `deploy_config.py`: `is_deploy_context() -> bool`; `resolve_config(key, *, canonical_default=None, required_in_prod=False) -> str | None` (env → canonical → if `required_in_prod ∧ is_deploy_context() ∧ unset` → raise `MissingProdConfigError`); `require_prod_config(keys: list[str]) -> None` (aggregate-raise listing ALL missing). Pure/env-only. `__all__`. Colocated test covers: dev no-op, prod-missing raises, canonical fallback, aggregate message.
  - **B — keeper.** `check_derives_from_dev_only_artifact`: flags seed `*.py` that reads `start.sh` / calls `parse_products_registry` / opens a `scripts/` artifact to DERIVE a value **without** an env fallback in the same function. Must PASS `cors_registry.py` (it HAS the env fallback). `severity="warning"`. Escape hatch `dev-artifact-derivation-ok`. Colocated `TestCheckDerivesFromDevOnlyArtifact` (required by `check_detector_has_regression_test`, compliance.py:6320). **Proactive (N=1, user-directed) — marked as such.**
  - **C — docs.** `deploy-config-contract.md`: the contract (dev↔prod-parity checklist → seam table), consume recipe (import `resolve_config`/`require_prod_config`; wire the guard), the keeper, relationship to `dev-prod-parity.md` / `seed-canonical-defaults.md`. Symbol-first. Must match A's API exactly (semantic-consistency point — see §6a).
- **✅ Wave 2 (A merged → done)** — startup guard shipped: `create_product_app` gained an opt-in `required_prod_config: Optional[list[str]] = None` param (back-compat default None = no-op) + a fail-fast `require_prod_config(...)` call right after logging. Verified: app.py AST-clean, primitive imports, guard no-op in dev, param in signature. The contract is now EXECUTABLE (the seam lives in the factory every product inherits).
- **⏳ Follow-up (pilot consume wave, pilot-products-first)** — pilots (erp/therapy/social) opt in by passing `required_prod_config=[...]` their actual prod-required keys. Deferred-with-destination (the seam is ready + back-compat; adoption is a per-product step, not a blocker) — NOT silent. Non-pilots extend in a later gated wave.

## 6a · Collision classes (decided at dispatch)

- A / B / C edit-sets are **C1 file-disjoint** vs each other (verified: distinct paths; B's two files touched by B only). Parallel-clean.
- **Semantic-consistency point** (the absorbed semantic-duplicate check): C's documented API ↔ A's built API. Not a file collision — architect verifies at reconciliation that the doc matches the code (read both deliverables, not just `git diff --name-status`).
- Integration merge: `--no-ff` per branch + a dedicated reconciliation commit (`KB § PATTERNS/branching-dispatch.md`).

## 7 · Open questions (+ recommendation)

1. **`is_deploy_context()` signal.** Rec: `True` if `APP_ENV in {production, staging}` OR any `PRODUCT_URL_*` (non-pattern) env set — covers the VPS (sets `PRODUCT_URL_*`) without a new required var; dev sets neither. Engineer A implements this; revisit if a product needs an explicit override.

## 10 · Commands

```bash
# worktrees (architect)
git worktree add -b feat/seed-deploy-config-contract/A-primitive ../noc-wt-dcc-A feat/seed-deploy-config-contract
git worktree add -b feat/seed-deploy-config-contract/B-keeper    ../noc-wt-dcc-B feat/seed-deploy-config-contract
git worktree add -b feat/seed-deploy-config-contract/C-docs      ../noc-wt-dcc-C feat/seed-deploy-config-contract
# verify (per slice)
seed: cd seed/lib/backend && python -m pytest tests/config/test_deploy_config.py
keeper: cd mcp/noctusai && .venv/bin/python -m pytest tests/test_compliance.py -k DerivesFromDevOnlyArtifact
```

## 11 · Change log

- 2026-05-23 — filed; Wave 1 decomposed (A/B/C, C1 file-disjoint); integration branch `feat/seed-deploy-config-contract` created off `main`; branching-dispatch runbook (just absorbed) governs.
- 2026-05-23 — Wave 1 ✅ shipped via parallel branching-dispatch (3 engineers, isolated worktrees, dash-form branches). A↔C semantic-consistency PASS. Merged `--no-ff` + reconciliation commit (INDEX/CLAUDE wired for C's doc; branch-naming N=3 + overlay-leak refinements folded into `branching-dispatch.md`). Authoritative verify green in main checkout. Overlay-leak recovered (findings.md). main still gated → Wave 2 next.
- 2026-05-23 — Wave 2 ✅ startup guard wired into `create_product_app` (opt-in `required_prod_config`, fail-fast after logging, back-compat no-op). Verified AST-clean + import + signature + dev-no-op. Contract is EXECUTABLE. Pilot adoption = follow-up consume wave. Integration branch ready; presenting integration→main for user go (main GATED until then).
