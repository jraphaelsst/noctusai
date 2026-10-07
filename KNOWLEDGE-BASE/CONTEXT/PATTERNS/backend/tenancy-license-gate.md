# Tenancy: the product license gate

> Formalized 2026-10-06 (round 2). Act-as-org removed + platform-org rule added
> 2026-10-07 (owner decision). Self-contained.

## The rule

1. **License gate.** A caller whose org has no ACTIVE license for the product
   (`public.licenses` `status='active' AND (fim IS NULL OR fim > now())`) is blocked
   server-side on EVERY authenticated API call: `403
   {"detail":"Sua organização não tem acesso a este produto.","code":"org_sem_licenca"}`.
   Public/unauthenticated routes are untouched; `core` is exempt. Customers
   (`membro`, `allow_customer`) need the license AND `products.aceita_clientes`.
2. **The effective org is always the caller's home org.** It comes from the trusted
   `public.noctus_users` row (`org_id`, `org_role`), never `user_metadata`. There is NO
   staff override: NoctusAI staff do not enter customer orgs (the superadmin
   "act-as-org" feature of 2026-10-06 was removed end to end on 2026-10-07 — core 067
   dropped `act_as_sessions` and restored the plain RLS helpers).
3. **No admin license bypass — `public.licenses` is the single source of truth.** There
   is NO `role == 'admin'` (or org-id) branch around the license check anywhere, in the
   seed or a product.
4. **The platform org holds every product license, by construction.** The NoctusAI org
   (`organizations.is_platform = true`, slug `noctusai`) reaches every product —
   including products created in the future — because the DATABASE keeps it licensed,
   not because Python special-cases it (core 068):
   - `public.grant_platform_org_licenses()` inserts an active, permanent (`fim NULL`)
     license for every (platform org × product) pair lacking one and clears any `fim`
     on an existing active one. Idempotent; SECURITY DEFINER; EXECUTE revoked from
     PUBLIC/anon/authenticated (service_role only).
   - Triggers call it: `AFTER INSERT ON products` (a new product is licensed the moment
     it exists) and `AFTER INSERT OR UPDATE OF is_platform ON organizations`.
   - `licenses_platform_org_guard` (BEFORE UPDATE/DELETE on `licenses`) refuses
     revoking, expiring (`fim`), re-pointing or deleting a platform org's ACTIVE license
     (pt-BR error). A cascade from deleting the product or the org itself is allowed.
   - Never "fix" a missing platform license by hand or with an admin branch: re-run
     `SELECT public.grant_platform_org_licenses();` and find what bypassed the trigger.

## By construction (zero per-product code)

| Piece | Where |
|---|---|
| Effective-org resolver (`EffectiveOrg(org_id, org_role)` = the home org) — the ONE answer to "which org is this request for" | `noctusai_lib/api/auth/effective_org.py` |
| License check (Fake + Real + factory, 60 s positive TTL cache, negatives never cached, fail closed → 503) | `noctusai_lib/domain/licensing.py` |
| Enforced inside `make_get_current_user_org`, `ProductDependencies.get_org_id`, the trusted legacy bridge, `require_scopes`, seed `auth_router` login | all route through the ONE resolver, then `enforce_license` |
| Gate configured once by `create_product_app` (slug = `product_slug=` ∨ `settings.product_slug` ∨ schema-derived) | `noctusai_seed/app.py` |
| `GET /api/me/access` (auth, NOT gated → `{has_access, product_slug, org}`) — the SPA's pre-flight that routes an unlicensed org to `/sem-acesso` | `noctusai_seed/me_router.py`, auto-mounted |
| FE UX half: `checkProductAccess` (login/SSO), the 403 `org_sem_licenca` interceptor, the seed `/sem-acesso` route | `@noctusai/lib` `access.ts` / `api.ts`, seed `app.tsx` |
| Platform org licenses (grant fn + triggers + revoke guard) | core 068 |

Slug mismatch (catalog slug ≠ schema, e.g. schema `erp` ↔ `erp-imobiliario`): pass
`product_slug=` to `create_product_app`. A product licensed for nobody still boots —
the gate runs per request, never at import.

## Tests / gates

Seed factories are Fake under pytest (like `make_audit_sink`): `FakeLicenseChecker`
allows everyone by default; a test that exercises the gate passes
`FakeLicenseChecker(allow_all=False, licensed={(org, slug)})` through
`configure_license_gate`. Keeper `check_license_gate_by_construction` fails any active
product that hand-rolls an org dependency, opts out (`enforce_license=False`,
`license_checker=`, own `configure_license_gate`), or branches on `role == 'admin'`
around a license call; it also pins the seed wiring. Strict `== 401` / `== 403` only.
`noctus.dev.verify_db_guards` proves the platform-org rule against the live DB
(rolled back): `licenses.platform_org.revoke_refused`,
`licenses.platform_org.holds_every_product`, `licenses.platform_org.new_product_licensed`.

## Gotchas

- Re-declaring `current_org_id()` / `current_user_org_id()` in a NEW migration must paste
  the canonical rendering (keeper `check_org_identity_function_parity`). Applied
  migrations are immutable history: stale copies (incl. core 065's superseded act-as
  branch) are FROZEN by content hash in `mcp/noctusai/tests/org_identity_parity_baseline.json`;
  a baselined file whose content changes is flagged. A second assertion requires the LAST
  (highest-numbered) core migration re-declaring each helper to equal the canon (today
  core 067). The helpers carry `-- secdef-execute-ok: rls-helper` (policies call them;
  EXECUTE stays).
- `audit_logs.acting_org_id` / `act_as_session_id` (core 065) are HISTORICAL columns —
  kept for rows written while act-as existed; nothing writes them.
- **The base auth dep is gated too.** `make_get_current_user` and
  `ProductDependencies.get_current_user` (auth with no org lookup) resolve the caller's
  org and enforce the license, so an auth-only route is gated by construction (no org /
  no `noctus_users` row ⇒ nothing to license, passes; lookup error ⇒ 503; core and the
  pytest allow-all Fake do zero extra queries). `make_get_current_user_org` unwraps
  `.ungated` so the license is checked once. The ONLY exemptions are the named
  `make_get_current_user_ungated` / `ProductDependencies.get_current_user_ungated`; the
  keeper fails any use outside `_LGC_UNGATED_ALLOWLIST` (file + rationale).
- **store** is gated like every product: `require_store_admin` → the gated
  `get_current_user`, so the CALLER's org must hold the `store` license, while
  data/key scoping stays on `STORE_ORG_ID` (the shop owner's data, not the caller's
  tenancy). Shop buyers are anonymous (no login): every `/api/*` buyer route in
  `public_router` / `webhooks_router` declares no auth dep, so they are public routes and
  untouched. No keeper allowlist exists for store.
- `/api/me/access` uses the ungated dep on purpose — it answers
  `has_access=false` instead of 403.

Composes with: `no-metadata-authz.md`, `database-rls.md`, `audit-trail.md`.
