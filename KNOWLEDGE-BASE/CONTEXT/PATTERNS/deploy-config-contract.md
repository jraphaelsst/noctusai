# Deploy-config contract — every dev↔prod-divergent knob routes through the seed primitive

> This is the **executable form** of [[dev-prod-parity]] §2 (the dev↔prod difference checklist) + §4 (verify-in-prod-shape). Where that doc is the discipline ("what differs between dev and prod, and how do you verify the prod shape"), this doc is the seam that makes the discipline structural. Its value-correctness sibling is [[seed-canonical-defaults]] (a seed default must be the *canonical* answer, never a consumer-#1 coincidence) — that rule governs *what* the default is; this rule governs *that the knob is forced to fail loud in prod when there is no safe default*.

---

## 1 · Rule (one-liner)

Every config knob whose value **diverges between dev and prod** routes through the seed deploy-config primitive — a **canonical default** (no-op in dev) `∧` a **fail-loud-if-required-in-prod** guard ⇒ a product **cannot** silently ship a dev value to prod.

The recurring root this closes: a seed/product reads a config knob, finds nothing set, and **silently falls to the dev value** (localhost URL, empty CORS registry, dev port). Dev keeps working; prod misroutes with an opaque downstream error. The fix is to make "unset in prod" a **loud boot-time failure** for the knobs that have no safe shared default, and a **canonical default** for the knobs that do.

---

## 2 · The primitive

Import from `noctusai_lib.config.deploy_config`. Pure / env-only (no IO beyond `os.environ`) — exempt from Fake+Real (a Fake would exercise the same code as the Real). Mirrors `product_urls.py` / `cors_registry.py` (same layer, env-only, downward-clean).

```python
from noctusai_lib.config.deploy_config import (
    MissingProdConfigError,
    is_deploy_context,
    resolve_config,
    require_prod_config,
)
```

### API

- `class MissingProdConfigError(RuntimeError)` — raised when a `required_in_prod` knob is unset inside a deploy context.
- `is_deploy_context() -> bool` — `True` iff `APP_ENV ∈ {production, staging}` `∨` any non-pattern `PRODUCT_URL_*` env is set. (The VPS sets `PRODUCT_URL_*`; dev sets neither ⇒ dev is `False`.)
- `resolve_config(key, *, canonical_default=None, required_in_prod=False) -> str | None` — resolution order: env `key` → `canonical_default` → if `required_in_prod ∧ is_deploy_context() ∧` still unset ⇒ raise `MissingProdConfigError`. In dev (`¬ is_deploy_context()`) an unset `required_in_prod` knob returns the `canonical_default` (∨ `None`) — never raises.
- `require_prod_config(keys: list[str]) -> None` — in a deploy context, **aggregate-raise** one `MissingProdConfigError` listing **all** missing keys (¬ first-fail). In dev: no-op.

---

## 3 · Consume recipe (backend)

### 3a · An optional knob — canonical default, no-op in dev

```python
from noctusai_lib.config.deploy_config import resolve_config

# unset → canonical default everywhere; prod overrides via env. Never raises.
storage_region = resolve_config("STORAGE_REGION", canonical_default="us-east-1")
```

### 3b · A required-in-prod knob — fail loud in prod, default in dev

```python
# unset in a deploy context ⇒ MissingProdConfigError (¬ silent dev fallback).
# unset in dev ⇒ returns the canonical default, dev keeps working.
public_base = resolve_config(
    "PUBLIC_BASE_URL",
    canonical_default="http://localhost:8000",
    required_in_prod=True,
)
```

### 3c · The startup guard — assert the required set at boot

```python
from noctusai_lib.config.deploy_config import require_prod_config

# at app startup — aggregate-raises ALL missing required-prod keys at once
require_prod_config(["PUBLIC_BASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"])
```

---

## 4 · The startup guard in the seed (Wave 2)

`create_product_app` (`seed/framework/backend/noctusai_seed/app.py`) calls `require_prod_config([...])` at boot ⇒ every product inherits the guard with **zero per-product code**. In dev the call is a no-op (`¬ is_deploy_context()`); in a deploy context a missing required knob fails the boot **loudly and immediately**, listing every gap at once — never a half-booted app silently serving dev values.

Replication-to-seed symmetry: the right per-product config-validation code count is **0**. The guard lives in the factory; products opt knobs in by passing keys.

---

## 5 · The keeper — `check_derives_from_dev_only_artifact`

Enforcement (`mcp/noctusai/tools/noctus/dev/compliance.py`, `severity="warning"`). Flags seed `*.py` that **derives runtime behavior from a dev-only artifact** — reads `start.sh`, calls `parse_products_registry`, ∨ opens a `scripts/` artifact to derive a value — **without** an env fallback in the same function. The slim deploy image has no `start.sh` / no populated registry ⇒ such derivation yields the empty/dev value in prod (the CORS-collapsed-to-localhost class).

- **Passes** `cors_registry.py` — it HAS the env fallback (reads `PRODUCT_URL_*` directly, registry is only a dev convenience).
- **Escape hatch**: `dev-artifact-derivation-ok` (when the derivation is genuinely dev-only ∧ guarded).
- Colocated `TestCheckDerivesFromDevOnlyArtifact` (required by `check_detector_has_regression_test`).

---

## 6 · dev↔prod-parity checklist → seam table

Each dev↔prod-divergent knob routes through a named seam — never a per-product re-resolution, never a silent fallback.

| Divergent knob | Seam (route) | Semantic |
|---|---|---|
| Product URLs (nav / SSO / cross-product links) | `product_urls.resolve_product_url` | `PRODUCT_URL_<SLUG>` → `PRODUCT_URL_PATTERN` → DB `url_base`; prod overrides via env, ¬ rebuild |
| CORS allow-origins | `cors_registry.derive_cors_origins` | reads `PRODUCT_URL_*` env directly + `@registry:all`; ¬ derives from the (empty-in-slim) start.sh registry |
| Required-in-prod config (base URL, service keys, etc.) | `require_prod_config([...])` (boot) + `resolve_config(..., required_in_prod=True)` (per-knob) | aggregate fail-loud in a deploy context; canonical default in dev |
| Optional env-divergent config (region, feature flags, …) | `resolve_config(key, canonical_default=...)` | canonical default everywhere; env overrides; never raises |
| Publishable / public keys (FE-baked, env-divergent) | `resolve_config(..., required_in_prod=True)` + the build-arg contract ([[seed-canonical-defaults]] §2) | loud-fail if a prod build omits it; ¬ a localhost-coincidence default |
| Same-origin FE backend URL | vite factory same-origin (`window.location.origin`) — already structural | `??""` not `||"localhost:8000"` ([[seed-canonical-defaults]] §2/§2a) |

New divergent knob ⇒ add a row + route it through `resolve_config` / `require_prod_config` (∨ the existing URL/CORS seam). A knob with no row is the next silent-prod-fallback waiting to happen.

---

## 7 · Relationship

- **[[dev-prod-parity]]** — the *discipline* (§2 difference checklist, §4 verify-in-prod-shape). This doc is its **executable form**: the checklist's knobs become seed seams; "verify in prod shape" becomes a boot-time guard that fails loud.
- **[[seed-canonical-defaults]]** — the *value-correctness* sibling. It governs *what* a default is (canonical-shared answer, ¬ consumer-#1 coincidence). This doc governs *that the knob is forced through the contract* (canonical default ∨ loud-fail-in-prod). Both fire together: a seam's default MUST be canonical (`seed-canonical-defaults`) `∧` a required-in-prod knob with no safe default MUST fail loud (`deploy-config-contract`).

---

**Doc anchors.** Memory entry: `feedback_deploy_config_contract.md` (to be authored). CLAUDE.md §1 bullet + §2 Map pointer (deploy-config-contract rule) — wired by the architect at reconciliation. Siblings: [[dev-prod-parity]] · [[seed-canonical-defaults]]. Project: `seed-deploy-config-contract` (2026-05-23). Primitive: `noctusai_lib.config.deploy_config`. Keeper: `check_derives_from_dev_only_artifact`.
