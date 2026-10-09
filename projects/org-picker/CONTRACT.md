# Org picker — contract (owner-confirmed 2026-10-08)

Replaces the removed act-as-org. Design: architect report + security review (2026-10-08),
folded with the owner's decisions below. This file is the single contract all three slices
build to.

## Owner decisions (verbatim in substance)

1. **Who (staff):** EXPLICIT grant only — never derived from org_role. Platform staff =
   `noctus_users.role = 'admin'` (superadmin; writable only via superadmin-gated endpoints)
   AND `org_role IN ('owner','admin')` AND the user's home org has `organizations.is_platform = true`. Today: the owner only.
   Everyone else enters their own org, no picker, picker endpoints → strict 403.
2. **When:** once per product per LOGIN (Supabase auth `session_id`). Popup modal on first
   entry to a picker-ready product; remembered until logout; "Trocar org" swap inside the
   product (staff-only, server-gated).
3. **Org list:** only orgs holding an ACTIVE, non-expired license for the product. The home
   (NoctusAI) org is always listed first ("Entrar como NoctusAI").
4. **Powers:** full owner powers in the target org — including invites/roles/API keys/
   webhooks/credentials (owner: "allow everything"). No reason prompt.
5. **2FA:** required. Picking/switching and every request while acting require an aal2
   session (seed `require_admin_assurance` semantics). No aal2 → picker endpoints 403
   `mfa_required`; an existing selection is ignored (resolves home) until aal2.
6. **Audit / LGPD:** the client sees DATA CHANGES staff make in their org (e.g. lead
   created/deleted) — audit row `org_id = target`, `acting_org_id = home`,
   `act_as_session_id = selection id`, actor shown as "Suporte NoctusAI". The client must
   NOT see that staff browsed / selected / swapped their org: selection start/end/swap and
   reads are logged with `org_id = NULL` (platform-only). No customer notification on
   selection.

## Data model (core migration 070, expand-only)

- `public.products`: `+ db_schema text UNIQUE` (backfilled for every product; NOT NULL for
  ativo rows) `+ org_picker_ready boolean NOT NULL DEFAULT false`.
- `public.platform_org_selections` (RLS on, no policy, service_role only):
  `id, user_id → noctus_users ON DELETE CASCADE, product_id → products, target_org_id →
  organizations, home_org_id → organizations, auth_session_id uuid NOT NULL, started_at,
  ended_at, ended_by ∈ (replaced, exit, logout, new_session, revoked)`,
  CHECK ((ended_at IS NULL) = (ended_by IS NULL)); UNIQUE live (user_id, product_id);
  index live (user_id, product_id, auth_session_id).
- RPC `public.platform_org_selection_set(p_user_id, p_product_slug, p_target_org_id,
  p_auth_session_id) → uuid` SECDEF, EXECUTE service_role only. Derives product_id +
  db_schema from the slug (refuses unknown slug / `org_picker_ready = false`), re-checks
  staff (role='admin' AND home is_platform) and target license, ends the live row for
  (user, product) with `replaced`, inserts. Errors: `platform_org_selection:not_platform_staff`,
  `:target_not_licensed`, `:product_not_ready`.
- RPC `public.platform_org_selection_end(p_user_id, p_product_slug text DEFAULT NULL,
  p_reason text)` — NULL slug = all products.
- Revocation triggers end live selections (`revoked`) on: noctus_users UPDATE of
  org_id/org_role/role or DELETE; organizations.is_platform change; licenses status/fim
  change or DELETE for the target org.
- RLS helper `public.current_org_id_for(p_schema text) → uuid` SECDEF STABLE:
  returns the live selection's target IFF caller is staff AND a live selection exists for
  the product whose `db_schema = p_schema` AND `auth_session_id = (auth.jwt()->>'session_id')::uuid`
  AND the JWT is aal2 (`auth.jwt()->>'aal' = 'aal2'`) AND the target holds an active
  license for that product AND the auth session still exists (`auth.sessions`) AND the product
  is `org_picker_ready`, AND the header `x-noctus-acting-org` (if present) equals the target;
  a present header that differs from the result is a DENY (NULL); otherwise the existing home
  rule (customers excluded).
  Non-staff exit after one indexed lookup. `current_org_id()` / `current_user_org_id()`
  stay HOME-ONLY forever (public tables and storage never act; realtime DOES act on converted tables -- the SPA tears channels down on swap).
- Product policies opt in by calling `(SELECT public.current_org_id_for('<schema>'))` —
  policy literal, never a request header. Pilot: social-wiring (migration 211). A product
  sets `products.org_picker_ready = true` only once every policy in its schema is converted
  (keeper-enforced).

## API (seed `me_router`, mounted on every product backend; core exempt)

All bodies JSON. Staff-only routes return strict `403 {"detail":…, "code":"not_platform_staff"}`
for non-staff, `403 code mfa_required` without aal2, `401` without a token.

- `GET /api/me/access` (ungated, existing) — adds:
  ```json
  "org_selection": {
    "available": true,            // product org_picker_ready AND caller is staff
    "required": true,             // available AND no live selection for this login
    "mfa_required": false,        // staff without aal2
    "acting": false,              // live selection whose target != home
    "org": {"id": "…", "nome": "…"} | null,       // effective org
    "home_org": {"id": "…", "nome": "…"} | null,
    "selection_id": "…" | null
  }
  ```
  (non-staff: `{"available": false, "required": false, "mfa_required": false, "acting": false, …}`)
- `GET /api/me/org-choices` → `{"orgs": [{"id","nome","is_home"}]}` (home first, then by
  nome). `Cache-Control: no-store`.
- `PUT /api/me/org-choice` body `{"org_id": "…"}` → returns the new `/api/me/access` body.
  Unlicensed target → `403 code org_sem_licenca`; product not ready → `409 code product_not_ready`.
- `DELETE /api/me/org-choice` → `204` (ends this product's selection, `exit`);
  `?all=true` (staff-only) ends EVERY product's selection (`logout`) -- the SPA calls it before sign-out.
- Intent pin: for staff with a live selection the SPA sends `X-Noctus-Acting-Org: <org id>`
  on every API request (FastAPI + PostgREST). FastAPI auth deps: header present and ≠
  resolved org → `409 {"code": "org_selection_changed"}`. SQL helper: header present and ≠
  target → DENY (the helper returns NULL, also on a home fall-through: a stale tab never reads/writes the wrong org). Non-staff header: ignored silently. Header added
  to CORS allow-list.
- Core `POST /api/auth/logout` ends ALL the user's selections (`logout`).

## Frontend (seed lib + framework)

- `access.ts`: `MeAccess.org_selection` typed per above.
- `org-selection.ts`: `useOrgSelection()` (access, choices, choose, end), pin store feeding
  the `X-Noctus-Acting-Org` header in `api.ts` and the Supabase client headers; `409
  org_selection_changed` → refetch access + reopen picker.
- Organs: `OrgPickerModal` (non-dismissible when `required`; home first; shows
  "Configure 2FA" CTA when `mfa_required`), `ActingAsBanner` (org name + "Trocar org",
  rendered only when `available`). Swap → `window.location.reload()` (no cross-org cache).
- `layout.tsx`: mounts `<OrgSelectionGate>`; logout calls `DELETE /api/me/org-choice`
  best-effort before signOut. Role/banner labels come from `/api/me/access`, never metadata.

## Out of scope (named destinations)

- Other products' policy conversion → one migration per product, flips `org_picker_ready`
  (NOC-REMEDIATE[org-picker-policy-conversion]).
- Drop of the prod-only `act_as_sessions` shim → core 071 after deploy_verify (contract step).

## Named destinations added by the security review (2026-10-08)

- NOC-REMEDIATE[org-picker-postgrest-audit]: FastAPI writes while acting are client-visible
  (`org_id = target`, role `platform_support`) on EVERY auth path (org dep, base dep,
  `require_scopes`/bridge). Writes the browser sends straight to PostgREST while acting
  carry no audit row yet; a per-table trigger reading `current_org_id_for` would close it.
  Not built now (no trigger). — 2026-10-08
