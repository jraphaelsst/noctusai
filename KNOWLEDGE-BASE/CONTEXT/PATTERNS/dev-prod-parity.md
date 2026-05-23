# Dev↔prod parity — "works in dev" ≠ "works in prod"; verify in the production shape

> **Rule.** A change is **not done** until verified in the **production shape** (slim image / live VPS), not just dev-green. Dev and prod are **structurally different environments** in noc — the slim prod image ships no `start.sh`, no node, baked dist, and reads config from env only. Code that works in dev can **silently** break in prod because prod lacks a dev artifact, reads config at a different layer, or runs a different file-set. **Tests-green ≠ prod-correct.**

This is the umbrella class. [[seed-canonical-defaults]] (wrong *value*), [[boundary-contract-tests]] B4 (env propagation), and [[containerization]] §12b (stale-container freshness) are **special cases** of it. The unifying failure: *works in environment A, silently broken in environment B, nobody verified B.*

---

## 1 · Why this is the highest-recurrence drift class on the platform

It has bitten the same shape ≥3× — and each was shipped by a prior agent who verified **dev**, not **prod**:

1. **`infra.tsx` localhost default** (2026-05-20) — FE defaulted backend URL to `http://localhost:8000`; worked in dev, misrouted every non-core product in the container. → [[seed-canonical-defaults]] §2.
2. **Cross-product nav → localhost after the prod deploy** (2026-05-22) — the launcher resolved tiles via `resolve_product_url`; no prod env override was set → fell to the DB `url_base` column, which is **seeded localhost by design**. Dev-green; prod SSO'd users to `http://localhost:8080`.
3. **CORS empty in the slim prod container** (2026-05-22, the sharpest) — `derive_cors_origins` got its slug list from the `start.sh` PRODUCTS registry. **The slim prod image ships no `start.sh`** → registry empty → CORS collapsed to localhost-only → apex login `Servidor indisponível`. Even a *canonical* default wouldn't have helped: the **derivation source itself was absent in prod**.

Sibling (same class, CI shape): test-dep superset drift — `test_audit_hook` imports `sqlalchemy`, `test_dimob_service` imports `defusedxml`; both lived in a product's **per-product** `requirements.txt` but not the **root superset** the CI backend jobs install → `ModuleNotFoundError` in CI only.

The common thread: **dev/local/full-image had X; prod/slim-image/CI-superset did not; nobody checked B.**

---

## 2 · The noc dev↔prod difference checklist (consult before shipping anything env-sensitive)

The slim prod `runtime` image and the VPS are **not** a dev box. Known structural divergences:

| Dimension | Dev / local / full image | Slim prod image · VPS · CI | Drift if you assume parity |
|---|---|---|---|
| `start.sh` + PRODUCTS registry | present | **ABSENT** (slim image) | seed code deriving from the registry gets **empty** → derive from **env** instead |
| node + vite | present (`runtime-watch` rebuilds) | **ABSENT** (baked `dist`) | can't rebuild in prod; FE config is frozen at CI build time |
| FE config (`VITE_*`) | read live each build | **BAKED at CI build** | URL/origin change needs a **rebuild**, not a restart (boundary B1) |
| BE config (`PRODUCT_URL_*`, `CORS_ORIGINS`, `APP_BASE_URL`) | env or falls to default | **env-only — must be SET** | localhost defaults silently ship; set prod env + **recreate** the container |
| DB `url_base` seed column | localhost (by design) | localhost (by design) | prod nav must override via **env**, never by editing the DB |
| CORS origins | `localhost:<port>` list | must include the **prod** origins | `derive_cors_origins` must read `PRODUCT_URL_<SLUG>` env **directly** (registry-free) |
| `public.products` rows | created by seed migrations | only what was **mirrored to prod** | a live product whose seed-row migration wasn't mirrored = **no nav tile** |
| Test deps | per-product `requirements.txt` | CI installs the **root superset** | a test importing a dep absent from the superset = `ModuleNotFound` in CI only |
| LLM provider | Anthropic key available | **OpenAI / Gemini** (no Anthropic) | product LLM code must not assume the Anthropic provider |

Add a row whenever a new divergence surfaces — this taxonomy is **open** (always-hardening posture).

---

## 3 · Authoring-time discipline (so the drift never ships)

Before shipping any code whose behavior depends on the environment, ask **the parity question**:

> **"Does this hold in the *slim prod container*, not just my dev box? If dev and prod differ on this dimension, what proves prod works?"**

Concretely:
- **Deriving from a file/artifact?** Confirm that file exists in the slim image (`start.sh`, the registry, a build tool). If it might be absent → **derive from env**, with a typed-error / `""` fallback, never a dev-convenience literal.
- **Reading config?** Know the **layer**: build-time (`VITE_*`, baked → needs rebuild) vs runtime (`getenv` per-request → needs only restart/recreate). Document which, so the deployer knows rebuild-vs-restart.
- **Setting a default?** It must be the **canonical** answer or env-driven — never a value that happens to work for your dev setup. → [[seed-canonical-defaults]].
- **Adding a seed-data row** a live product needs (e.g. `public.products`)? Its migration must be **mirrored to prod**, or the prod feature silently no-ops.

If none of your existing tests would fail when this contract drifts dev→prod → you have a **boundary** with no test → file a boundary-contract test or accept-with-destination. → [[boundary-contract-tests]].

---

## 4 · Deploy-time discipline — verify the live prod path end-to-end

`pytest` green + `vite build` clean is **not** "deployed and working." After any deploy that touches env-sensitive behavior:

1. **Verify the FE bake** before/after a rebuild (boundary B1) — confirm the bundle baked the prod URL, not localhost (bundle-hash unchanged on a backend-only change is a good signal).
2. **Live-probe the actual prod path** — the real failure mode only shows here. E.g. CORS: `OPTIONS` preflight against the prod origin must return `200 + access-control-allow-origin`; an evil origin must `400`. Login: actually hit `/api/auth/login` cross-origin.
3. **Keep the safety in place during a risky cutover** — a flip that removes a working override to rely on derived behavior is reversible: leave the override until the new path is **live-verified**, then remove. The 2026-05-22 first CORS cutover failed (registry-empty) but never left prod broken because the override protected it until verified.

→ Container-runtime freshness (is the *running* container even serving the new code?) is the [[containerization]] §12b contract. This rule is the layer above: *even a fresh container can be prod-wrong if the code assumed dev parity.*

---

## 5 · Detection status (codification honesty)

- **Wrong-value sub-class** (localhost default) → **already Stage-4**: `check_seed_canonical_default` keeper ships, 0 baseline. → [[seed-canonical-defaults]] §6.
- **Derives-from-dev-only-artifact sub-class** (the registry-empty case) → **Stage-3** (this doc). N=1 for the *derivation* shape specifically (`derive_cors_origins`); a deterministic detector ("seed code calls `parse_products_registry()` / reads a `scripts/` artifact without an env fallback") is **deferred to N=2** of that exact shape — honest, not forced. Until then it's authoring-discipline + the §2 checklist.
- **Verify-in-prod-shape discipline** → judgment-dependent, stays Stage-3 by design (no static predicate for "did you live-probe prod").

---

## 6 · The remediation that closed each bit (reference)

- **infra.tsx / vite factory** → canonical default (`?? ""`, throw on unmapped) + propagate. → [[seed-canonical-defaults]].
- **nav → localhost** → set `PRODUCT_URL_PATTERN=https://{slug}.noctusai.com` + per-product overrides on the VPS `.env`; recreate `core` (runtime config, no rebuild). DB stays localhost by design.
- **CORS registry-empty** → made `derive_cors_origins` **deploy-aware**: in `@registry:all` mode it now resolves each registry slug via `resolve_product_url` **and** scans `os.environ` for `PRODUCT_URL_<SLUG>` keys **directly** (registry-free) → works with no `start.sh`. Immediate stopgap was an explicit `CORS_ORIGINS` env list, verified by preflight.
- **test-dep superset drift** → added the missing deps (`sqlalchemy`, `defusedxml`) to the **root** `requirements.txt` with an inline comment naming the importing test + the superset-completeness reason.

---

**Doc anchors.** Memory: `feedback_dev_prod_parity_verify_in_prod_shape` · `reference_cross_product_nav_url_resolution` (the URL/CORS specifics) · `feedback_ci_layered_rehab` (the CI superset shape). CLAUDE.md §1 "Finish the session — verify" bullet (dev↔prod-parity clause). Special cases: [[seed-canonical-defaults]] · [[boundary-contract-tests]] · [[containerization]] §12b. Guide: [[KB § GUIDES/production-deploy.md]] §6. Born 2026-05-22 (nav-remap → prod-CORS session).
