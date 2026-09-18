# Product working scope — which products we touch, and where

> **The catalog is the working guide.** `public.products.ativo` +
> `public.products.deploy_scope` are not decoration on an admin screen — together
> they are the standing answer to "may I edit this product's code, and which
> environment does that work target?" Set in the UI by the user; read by every
> agent before touching a product.

---

## 1 · The three states

| `ativo` | `deploy_scope` | What it means for our work |
|---|---|---|
| `true` | `live` | **Work it in PROD.** Flow: `predeploy_check` + CI green → bless → promote → `deploy_pull`/`deploy_image` → prod smoke. |
| `true` | `dev` | **Work it, but it has NOWHERE to deploy right now.** 🔴 The dev fleet is DORMANT (2026-08-11) — this is a PARKING state, not a workflow: land the code on the `dev` branch and stop. Do not invent a substitute environment, and do not promote it. → `KB § PATTERNS/devops/dev-fleet-dormant.md` |
| `false` | (forced `dev`) | **IGNORE.** Do not touch this product's code at all. |

`deploy_scope` is stored **INTENT**, deliberately distinct from
`GET /api/products/deployment-status`, which probes whether a container is
reachable *right now*. Intent answers "where do we work this?"; the probe answers
"is it up?". Conflating them makes "running in prod but we've stopped shipping
there" inexpressible — exactly the state a wind-down needs. Both are shown in the
admin UI, and a disagreement between them is surfaced, never silently reconciled.

**Depth of work is unchanged.** Scope selects the *destination*, not the rigour:
a `live` product still earns prod only by passing the full gate first
(`KB § GUIDES/production-deploy.md § 0.1`). A `dev`-scoped product runs the same
gates and then **stops at the `dev` branch** — since 2026-08-11 there is no dev
fleet to deploy it to, so `ativo`+`dev` parks work rather than routing it.

## 2 · Two invariants, enforced not trusted

- **I1 — an inactive product can never be `live`.** DB `CHECK`
  (`products_inactive_never_live`) on `public.products`, so *every* writer obeys
  it, not just the one that goes through FastAPI.
- **I2 — a reactivated product always lands in `dev`.** It has not been
  re-validated in prod, so returning it straight to `live` would silently
  re-expose it. Promotion back to `live` is a separate, explicit human action.

Consequence: **deactivating a live product demotes it to `dev` in the same
write.** Not a convenience — a two-step "demote then deactivate" leaves a window
where a crash strands the row in the combination I1 forbids.

## 3 · Where the rules live (one path each)

| Axis | Endpoint | Refuses |
|---|---|---|
| status | `POST /api/products/{id}/activation` | 404 unknown product |
| scope | `POST /api/products/{id}/deploy-scope` | **409** when setting `live` on an inactive product |

`ativo` and `deploy_scope` are **deliberately absent from `PATCH /api/products/{id}`**.
`ProductUpdate` is a `StrictHttpModel`, so sending either returns 422 — that is
what makes the dedicated endpoints the only path and keeps the transition rules
in one place. `DELETE /api/products/{id}` is retained as a legacy alias and
delegates to the same helper.

Presentation fields split the same way: **Nome / Descrição / Cor** are
human-owned and editable in the admin modal; **icone / url_base / slug** are
SYSTEM-owned (scaffolder + url-roster tooling) and are not offered on edit —
hand-editing them is how the catalog drifts from the fleet it describes.

## 4 · Surfaces

- **`/admin/products`** — the single catalog + control surface. Sectorized into
  the three buckets (spaced cards, one per bucket), each row carrying the Status
  and Deploy toggles, a colour palette popover, an edit icon, licence count, and
  the container-mismatch warning.
- **Dashboard cards** — admin-only inline toggles for quick changes. Admins also
  *receive* inactive products from `/api/auth/me` (role-branched there), so a
  deactivated product still renders — dimmed, non-launchable — and can be
  reactivated in place. Non-admins never see those rows.

Both consume `products/core/frontend/src/components/ProductStateControls.tsx`,
which also owns `bucketOf` / `BUCKETS`. A hand-rolled third copy would let the
rules drift between surfaces, and a guide that disagrees with itself is worse
than no guide.

> **Retired: `/admin/product-control`.** A separate control board existed briefly
> and was merged into `/admin/products` (2026-08-10) — it was a strict subset
> apart from two things, both carried over: the container-mismatch warning and
> the per-bucket counts. Two pages doing the same job is drift waiting to happen.

## 4a · Auditing

Every transition writes to `public.audit_logs` via `app.services.audit_service`:
`product.activated` · `product.deactivated` · `product.deploy_scope_changed`,
each recording BEFORE and AFTER `{ativo, deploy_scope}` — the interesting part
of a deactivation is what it was demoted *from*. A refused (409) change writes
nothing, because nothing changed. The write is best-effort: an audit failure is
logged loudly but never rolls back a transition the operator already saw succeed.

## 4b · Enforced at the deploy/migrate ACTION, not just at verification (2026-09-17)

**The incident.** A real prod deploy ran `noctus.dev.deploy_image
product='erp-imobiliario' confirm=True` and then applied a migration to `erp`.
`erp-imobiliario` was `ativo=false, deploy_scope='dev'` — exactly the row §1's
table says to IGNORE. `deploy_image` reported `status: "deployed"`, healthy,
swap-verified — none of its gates (snapshot-verify, PROD-PIN ancestry,
swap-verify) ever asked "should this be touched at all?", only "did the touch
land cleanly?". The mistake surfaced only afterwards, when `noctus.dev.deploy_verify`
classified `erp` as `skipped_inactive` — a rule `deploy_verify` (and
`predeploy_check`) already honoured, that the actual deploy/migrate ACTIONS did
not.

**The fix.** `noctus.dev.deploy_image` and `noctus.dev.migrate_product` now
BOTH refuse — `status='refused_catalog_scope'`, `exit_code=1`, nothing
touched — before doing anything else, unless the product resolves as
`ativo=true AND deploy_scope='live'` in the catalog (or `core`). Both compose
the SAME catalog-roster resolution `deploy_verify` already used
(`deploy_verify._resolve_live_products`, via the shared
`mcp/noctusai/tools/noctus/dev/_catalog_scope_guard.py`) rather than a second
hand-rolled catalog read. Fail-closed: when the catalog is unreachable and the
checked-in `build-scope.txt` fallback is unavailable too, the guard resolves
`in_scope=False` — "cannot tell" is never "allowed". Escape hatch:
`allow_inactive=True` on both tools — legitimate only for a deliberate,
supervised reactivation, and the resolved `catalog_scope` verdict rides on the
returned payload either way, never silently.

A secondary tell in the same incident — `erp-imobiliario`'s pulled `:latest`
was built from a revision behind `origin/prod`, because `build-scope.txt`
only rebuilds `ativo=true+live` products — needed **no separate check**.
`deploy_image`'s existing PROD-PIN ancestry guard stays scoped to "not ahead
of prod" (staleness-behind-tip is the documented normal steady state for a
genuinely live product too, since a product's image only rebuilds when ITS
OWN files or `seed/` changed). Once `refused_catalog_scope` blocks an
inactive/dev-scope product from reaching the deploy path at all, its
permanently un-rebuilt image can never be pulled onto prod in the first
place — the catalog-scope guard is what closes this, not a "revision ==
prod tip" assertion (which would wrongly refuse routine, healthy re-deploys
of live products). See `KB § PATTERNS/devops/prod-deploy-safety-gates.md`.

## 5 · Before you touch a product

```sql
SELECT slug, ativo, deploy_scope FROM public.products ORDER BY slug;
```

`ativo = false` → stop. `deploy_scope = 'dev'` → do the work, land it on the
`dev` branch, do **not** promote — and note there is no dev fleet to deploy to
while it is dormant. `deploy_scope = 'live'` → the full pipeline applies.

Migration: `products/core/backend/migrations/042_product_deploy_scope.sql`.
Related: `KB § PATTERNS/architect/git-branch-model.md` (dev vs prod lines) ·
`KB § GUIDES/production-deploy.md` (the dev-validate gate that both scopes obey).
