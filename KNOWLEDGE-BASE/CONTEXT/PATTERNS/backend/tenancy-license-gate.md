# Tenancy: the product license gate

> Formalized 2026-10-06 (round 2). Act-as-org removed + platform-org rule added
> 2026-10-07 (owner decision). Platform org picker added 2026-10-08 (§ Platform org
> picker). Self-contained.

## The rule

1. **License gate.** A caller whose org has no ACTIVE license for the product
   (`public.licenses` `status='active' AND (fim IS NULL OR fim > now())`) is blocked
   server-side on EVERY authenticated API call: `403
   {"detail":"Sua organização não tem acesso a este produto.","code":"org_sem_licenca"}`.
   Public/unauthenticated routes are untouched; `core` is exempt. Customers
   (`membro`, `allow_customer`) need the license AND `products.aceita_clientes`.
2. **The effective org is the caller's home org** — it comes from the trusted
   `public.noctus_users` row (`org_id`, `org_role`), never `user_metadata`. The ONLY
   exception is the explicit, 2FA-gated, per-login **platform org picker** (§ below);
   there is no implicit staff override (the superadmin "act-as-org" of 2026-10-06 was
   removed on 2026-10-07 — core 067).
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

## Platform org picker (2026-10-08, core 070 + seed `me_router`)

Contract: `projects/org-picker/CONTRACT.md`. Platform STAFF enter a customer org **per
product, per login**; everyone else enters their own org and the picker endpoints answer a
strict `403 {"code":"not_platform_staff"}`.

- **Staff = explicit grant, never derived from `org_role`:** `noctus_users.role='admin'`
  (superadmin, writable only through the superadmin-gated users router) AND home
  `org_role IN ('owner','admin')` AND the home org `organizations.is_platform`. Re-checked by the RPC and the SQL helper themselves.
- **Data model (core 070, expand-only):** `products.db_schema` (= the product's
  `create_product_app(schema=…)`, pinned to the tree by `test_migration_070`) +
  `products.org_picker_ready` (default false); `platform_org_selections` (service-role only;
  one LIVE row per (user, product); bound to the Supabase auth `session_id`; `ended_by` ∈
  replaced | new_session | exit | logout | revoked); RPCs `platform_org_selection_set/_end`
  (SECDEF, EXECUTE service_role only; errors `platform_org_selection:not_platform_staff |
  target_not_licensed | product_not_ready`); triggers end a live selection `revoked` when the
  user's org/role changes, the home org stops being `is_platform`, or the target's license
  lapses.
- **RLS:** `public.current_org_id_for(p_schema)` (canonical text in `sql_templates`, parity
  keeper `check_org_identity_function_parity`; keeps caller EXECUTE via the `rls-helper`
  marker) returns the live selection's target only for staff + this login's `session_id` (and
  that `auth.sessions` row still exists) + `aal2` + a `org_picker_ready` product + a
  still-licensed target; a staff request whose `x-noctus-acting-org` is present and differs
  from the result is DENIED (NULL, also on the home fall-through); otherwise the home rule
  (customers NULL). Un-readying a product (or changing its `db_schema`) ends its live
  selections by trigger. `current_org_id()` / `current_user_org_id()` stay
  HOME-ONLY forever. A product's policies opt in with
  `(SELECT public.current_org_id_for('<schema>'))`; it flips `org_picker_ready=true` only
  when every policy is converted — keeper `check_org_picker_ready_policies` fails a chain that
  flips it with a home-only policy left (or without the acting-audit attach). Rolled out
  2026-10-09: social-wiring, agents, academia-de-reciclagem, seed, community, igig (store
  excluded: `STORE_ORG_ID`). Shape per product: `<n>_org_picker_policies` (ALTER POLICY from
  live `pg_policies`) → `<n+1>_org_picker_acting_audit` → `<n+2>_org_picker_ready`. A role
  check on the caller's own `noctus_users` row may stay home-keyed (staff are `role='admin'`
  with home `org_role` owner/admin, so they pass it) — an exact allowlist entry, and the org
  predicate beside it must still be converted.
- **Seed:** `OrgSelectionStore` (Protocol + Real + Fake + factory, `api/auth/org_selection.py`);
  the gate (`configure_license_gate(selection_store=, db_schema=)`) carries it;
  `resolve_effective_org(core, user_id, *, product_slug, token, acting_header, …)` is still
  the ONE resolver: staff + live selection + same login + aal2 + licensed ⇒ target with role
  `owner`, else home (no aal2 ⇒ home + `mfa_required`). Intent pin: header present and ≠
  resolved org ⇒ `409 {"code":"org_selection_changed"}` (non-staff: ignored).
  `/api/me/access` gains `org_selection{available, required, mfa_required, acting, org,
  home_org, selection_id, org_role}`; `GET /api/me/org-choices` (home first, licensed orgs,
  `no-store`), `PUT`/`DELETE /api/me/org-choice` (`403 mfa_required`, `403 org_sem_licenca`,
  `409 product_not_ready`; `DELETE …?all=true`, staff-only, ends every product's selection
  as `logout`). Core logout ends all selections. `org_id` must be a UUID (422 otherwise).
- **Audit/LGPD:** data-mutating rows while acting carry `org_id = target`,
  `acting_org_id = home`, `act_as_session_id = selection id`, role `platform_support` (the
  client sees the changes, labelled "Suporte NoctusAI"); selection start/end/swap and reads
  are logged with `org_id NULL` (platform-only). The acting actor is stashed on EVERY
  FastAPI auth path (org dep, base dep, `require_scopes`/legacy bridge). Browser writes sent
  straight to PostgREST while acting are audited by core 072's row trigger
  `public.audit_acting_write()` (same tags; changed column NAMES only, never values; a failed
  audit insert fails the write), attached per product via
  `public.attach_acting_audit_triggers('<schema>')`. `check_org_picker_ready_policies` refuses
  a ready flip whose chain lacks that call. — 2026-10-09
  Realtime DOES act on converted tables; the SPA tears channels down on swap.
- **Probes:** `noctus.dev.verify_db_guards` — `platform_org_selections.*`,
  `platform_org_selection_set.refuses_*`, `current_org_id_for.*` (positive control + home for
  non-staff / other session / aal1 / unlicensed / mismatching header), revocation trigger,
  `audit_acting_write.*` (acting write ⇒ one target-org row; non-acting write ⇒ none).
- **Team rules (core):** `owner` is never grantable via invite or role change; granting
  `admin` needs an inviter who is owner/admin or the platform superadmin; an `owner` target
  can be neither re-roled nor removed (strict 403) and an `admin` target needs the same
  caller. (The seed team router has no role-change route and refuses removal with 409.)

Composes with: `no-metadata-authz.md`, `database-rls.md`, `audit-trail.md`.
