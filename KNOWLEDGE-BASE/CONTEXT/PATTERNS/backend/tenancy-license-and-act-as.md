# Tenancy: license gate + superadmin act-as-org

> Formalized 2026-10-06 (round 2). Self-contained.

## The rule

Two layers of "owner". **Superadmin** = `public.noctus_users.role = 'admin'` (the
platform owner), read from the trusted row, never `user_metadata`. **Org owner** =
`org_role = 'owner'` of a customer's own org. (`platform_admin` is the PRODUCT-side
name for org owner/admin — never reuse it for the platform owner.)

1. **License gate.** A caller whose EFFECTIVE org has no ACTIVE license for the
   product (`public.licenses` `status='active' AND (fim IS NULL OR fim > now())`) is
   blocked server-side on EVERY authenticated API call: `403
   {"detail":"Sua organização não tem acesso a este produto.","code":"org_sem_licenca"}`.
   Public/unauthenticated routes are untouched; `core` is exempt. Customers
   (`membro`, `allow_customer`) need the license AND `products.aceita_clientes`.
2. **Act-as-org.** The superadmin picks an org in core and enters a product AS it —
   full read+write, reason optional, no 2FA, no time limit; it ends on "Sair", a new
   act-as, or core logout. The target org MUST hold the license for the entry product.
3. **No admin license bypass.** There is NO `role == 'admin'` branch around the
   license check anywhere. A superadmin reaches a product he has no home license for
   ONLY through a live `act_as_sessions` row, and the license is then checked against
   the TARGET org.

## By construction (zero per-product code)

| Piece | Where |
|---|---|
| Effective-org resolver (`EffectiveOrg(org_id, org_role, home_org_id, acting_session_id)`; acting ⇒ target org, `org_role='owner'`) | `noctusai_lib/api/auth/effective_org.py` |
| License check (Fake + Real + factory, 60 s positive TTL cache, negatives never cached, fail closed → 503) | `noctusai_lib/domain/licensing.py` |
| Enforced inside `make_get_current_user_org`, `ProductDependencies.get_org_id`, the trusted legacy bridge, `require_scopes`, seed `auth_router` login | all route through the ONE resolver, then `enforce_license` |
| Gate configured once by `create_product_app` (slug = `product_slug=` ∨ `settings.product_slug` ∨ schema-derived) | `noctusai_seed/app.py` |
| `GET /api/me/access` (auth, NOT gated → `has_access`), `GET /api/me/context` (auth + gated → org/home_org/acting) | `noctusai_seed/me_router.py`, auto-mounted |
| Audit tagging: `AuditActor.acting_org_id` / `act_as_session_id`; rows while acting carry `org_id` NULL so the customer's org-scoped audit read never sees them | `api/audit/{types,sink}.py`, `audit_logs` cols (core 065) |
| RLS: `current_org_id()` / `current_user_org_id()` return the session's target org for a superadmin with a live session (SECURITY DEFINER, caller-executable RLS helpers) | `sql_templates.org_identity_function_sql`, core 065 |
| Core endpoints: `GET /api/admin/orgs`, `POST /api/admin/act-as`, `DELETE /api/admin/act-as/current`, `GET /api/admin/act-as/history` (superadmin only; non-admin 403, no token 401); core logout ends the session (`ended_by='logout'`) | `products/core/backend/app/routers/act_as.py` |

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

## Gotchas

- `public.act_as_sessions` is service-role only (RLS on, no policy). The RLS helper
  reads it as SECURITY DEFINER; never grant anon/authenticated.
- Re-declaring `current_org_id()` / `current_user_org_id()` in a NEW migration must paste
  the canonical rendering (keeper `check_org_identity_function_parity`). The act-as branch
  made ~35 older copies stale, but applied migrations are immutable history: those copies
  are FROZEN by content hash in `mcp/noctusai/tests/org_identity_parity_baseline.json`
  (applied before 2026-10-06; ledger-keyed by filename; superseded by core 065). The
  baseline never grows; a baselined file whose content changes is flagged. A second
  assertion requires the LAST (highest-numbered) core migration re-declaring each helper
  to equal the canon (today core 065), so the act-as branch can't be silently clobbered.
  The helpers carry `-- secdef-execute-ok: rls-helper` (policies call them; EXECUTE stays).
- **The base auth dep is gated too.** `make_get_current_user` and
  `ProductDependencies.get_current_user` (auth with no org lookup) resolve the caller's
  effective org and enforce the license, so an auth-only route is gated by construction
  (no org / no `noctus_users` row ⇒ nothing to license, passes; lookup error ⇒ 503;
  core and the pytest allow-all Fake do zero extra queries). `make_get_current_user_org`
  unwraps `.ungated` so the license is checked once. The ONLY exemptions are the named
  `make_get_current_user_ungated` / `ProductDependencies.get_current_user_ungated`; the
  keeper fails any use outside `_LGC_UNGATED_ALLOWLIST` (file + rationale; today only the
  seed `me_router`).
- **store** is gated like every product: `require_store_admin` → the gated
  `get_current_user`, so the CALLER's effective org must hold the `store` license, while
  data/key scoping stays on `STORE_ORG_ID` (the shop owner's data, not the caller's
  tenancy). Shop buyers are anonymous (no login): every `/api/*` buyer route in
  `public_router` / `webhooks_router` declares no auth dep, so they are public routes and
  untouched. No keeper allowlist exists for store.
- `/api/me/access` uses the ungated dep on purpose — it answers
  `has_access=false` instead of 403; no other opt-out exists.

Composes with: `no-metadata-authz.md`, `database-rls.md`, `audit-trail.md`.
