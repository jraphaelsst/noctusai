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
product, per login**; since multi-org (2026-10-13, § Members below) so do ordinary MEMBERS of
several orgs — but only the orgs they are an ACTIVE member of (`public.org_memberships`);
a PUT for any other org answers a strict `403 {"code":"not_a_member"}`.

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
  from the result is DENIED (NULL, also on the home fall-through); staff on a ready product
  with no valid selection get NULL (core 078, § Every entry is a choice); otherwise the home
  rule (customers NULL). Un-readying a product (or changing its `db_schema`) ends its live
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
  `owner`, else home (no aal2 ⇒ home + `mfa_required`; the aal2 leg applies only while the
  product's `org_picker_requires_mfa` is true — core 073, owner switched it off 2026-10-09,
  restore = `UPDATE products SET org_picker_requires_mfa = true`). Intent pin: header present and ≠
  resolved org ⇒ `409 {"code":"org_selection_changed"}` (staff AND members; it only narrows — it
  can refuse a request, never widen one).
  `/api/me/access` gains `org_selection{available, required, mfa_required, acting, org,
  home_org, selection_id, org_role}`; `GET /api/me/org-choices` (client orgs by name, the
  home org LAST, licensed orgs, `no-store`), `PUT`/`DELETE /api/me/org-choice` (`403 mfa_required`, `403 org_sem_licenca`,
  `409 product_not_ready`; `DELETE …?all=true` ends every product's selection of the CALLER
  as `logout`; any authenticated user — it only ever touches their own rows). Core logout ends all selections. `org_id` must be a UUID (422 otherwise).
- **Every entry is a choice (owner decision 2026-10-12).** Platform staff must choose the org
  EVERY time they ENTER a product, never silently landing in the home org (NoctusAI).
  - ENTRY = (a) an SSO launch/redeem landing from core (always an entry, even in the same
    tab), or (b) a page load of the product in a browser tab that has no visit marker for
    this product (new tab, typed URL, bookmark, reopen after tab close).
  - NOT entry: reload (F5) of the same tab, in-app navigation, "Trocar org" (already reopens
    the picker), silent token refresh, 409 handling.
  - On entry the picker is REQUIRED (non-dismissible), product content is NOT rendered behind
    it, and the server refuses product data until a choice exists.
  - Within the visit (same tab, reloads included) the choice holds.
  - Multi-tab: ONE live org per (user, product). Choosing in a second tab ends the first
    tab's choice; that tab gets 409 org_selection_changed → picker reopens.
  - Picker list order: client orgs first (alphabetical), the home org "Entrar como NoctusAI
    (minha org)" LAST.
  - Users the picker does not apply to (non-staff with fewer than 2 eligible orgs, D1 below):
    no picker, no behaviour change at all. A member with ≥2 eligible orgs follows these rules
    exactly as staff do (§ Members, Front end).

  **Visit marker (seed FE, `org-visit.ts`):** `sessionStorage['noctus:org-visit:<slug>']`
  (per tab, per product); every access is try/catch and unavailable storage reads as "no
  marker" (fail toward prompting). Written ONLY after a successful `PUT` (so a reload
  mid-pick is still an entry) or, for non-staff, once `/api/me/access` says
  `available=false`. `SSOCallback` drops it on mount (`beginOrgVisitEntry`); logout
  (`endOrgSelectionBestEffort`) drops it too. **Entry handshake** (`useOrgSelection`):
  no marker + `available` ⇒ `DELETE /api/me/org-choice` (this product, end reason `exit`)
  then refetch access ⇒ required picker; the leftover selection is never pinned/adopted.
  `<OrgContentGate>` (mounted by the seed shell around the routes) renders no children while
  an entry's access is pending, the handshake is in flight, or the picker is required.
  **Entry polish (2026-10-13):** `/api/me/org-choices` fires as soon as the FIRST access says
  `available && !mfa_required`, in PARALLEL with the entry DELETE (the list does not depend on
  the selection; `staleTime` 5 min so "Trocar org" opens instantly); the list renders at once
  and the buttons stay disabled (`chooseBlocked`; `choose()` also awaits the handshake) until
  the DELETE settles. The same gate state is exposed as `useOrgEntryPending()`: the seed shell
  header does NOT mount org-scoped widgets (notification bell, AI/LLM badges) nor the
  enrichment "Carregando" state while it is true, so nothing fetches behind the picker; logo,
  sidebar shell and avatar/name stay. Non-staff: unchanged.
  **Cross-tab rule (owner 1A, 2026-10-12; fix 2026-10-13):** one org per product per login, so
  choosing in a 2nd tab must make the 1st tab RE-PROMPT, never silently adopt. The marker
  therefore stores the org THIS tab chose (`markOrgVisit(orgId)`; non-staff store the sentinel
  `-`; reader `getOrgVisitOrg()`; a legacy timestamp value reads as unknown). On a `visit` load
  for a picker user whose server selection differs from the marker org (other tab replaced it,
  none, or legacy marker) the marker is cleared and the phase goes straight to `ended`
  (required, non-dismissible picker, content blocked) WITHOUT the entry DELETE -- it would end
  the other tab's live selection; the next PUT replaces it and that tab re-prompts in turn. The
  in-page swap branch still hard-reloads (purges the old org's cache) and the reload re-prompts.
  Same org re-chosen elsewhere (marker == server org): silent, F5 unchanged.
  **Server:** `resolve_effective_org(..., require_selection=True)` (the default — every
  gated path: base dep license gate, org dep, `resolve_org_membership`) answers staff on a
  ready product with no valid live selection `409 {"code":"org_selection_required"}`
  (`ORG_SELECTION_REQUIRED_CODE`) instead of home; only `/api/me/access` passes
  `require_selection=False`. The MFA path is unchanged (aal1 on a requires-MFA product ⇒
  home + `mfa_required`). A pin mismatch is still checked first (`org_selection_changed`).
  The FE api client treats both 409 codes alike (clear pin, reopen picker, no retry).
  **PostgREST (core 078):** `current_org_id_for(p_schema)` mirrors the resolver — staff on
  the ready product owning `p_schema` whose token passes its MFA rule (`NOT
  org_picker_requires_mfa OR aal='aal2'`) but who hold no valid live selection (this login,
  auth session alive, target licensed) get **NULL** (RLS: no rows, writes refused; a
  `DEFAULT current_org_id_for(…)` `org_id NOT NULL` column refuses the insert). aal1 on a
  requires-MFA product stays home (the resolver's `mfa_required` path); non-staff, a
  not-ready product, and the pin-header narrowing are unchanged. Probes
  `current_org_id_for.null_for_*` / `null_on_session_mismatch` / `null_when_*`
  (`verify_db_guards`, parked `pending_migration` until 078 is applied). Known residual: the
  SQL helper also requires the `auth.sessions` row to exist, the Python resolver does not
  (SQL stricter: NULL vs target for a token outliving its session).
- **Members (multi-org S2+S3, owner decisions 2026-10-13, core `org_member_selection`).** The
  SAME picker, widened from "staff" to "staff OR an ACTIVE member of the target org" — no second
  mechanism. Roadmap: `project-history/roadmaps/multi-org-membership-2026-10.md`.
  - **Who:** the RPC `platform_org_selection_set` keeps its staff path byte-for-byte; a non-staff
    caller needs an ACTIVE `org_memberships` row for the target (else
    `platform_org_selection:not_a_member`, row locked `FOR SHARE`), plus the usual ready/licensed
    refusals. A customer-role membership never resolves (helper NULL, resolver ignores it).
  - **Role = the membership role in the EFFECTIVE org, never the home profile role** (owner in A
    + viewer in B ⇒ viewer in B — the privilege-leak guard; probe
    `platform_org_selection_set.member_role_is_the_target_membership_role`). The resolver reads it
    from `org_memberships` on EVERY request (`OrgSelectionStore.memberships`, never cached).
  - **Q1** no aal2 for members (staff keep it). **D1 (owner, 2026-10-14 — replaces Q2):** an
    ELIGIBLE org = an ACTIVE, non-customer membership whose org is licensed for the product and in
    which the user is not blocked from it (D5). With ≥2 eligible orgs and no valid live selection
    EVERY gated path answers `409 org_selection_required` (a choice on every entry, like staff;
    SQL: `current_org_id_for` NULL); exactly ONE eligible org is served silently (even when it is
    not the profile org — the profile does not move); none → the home org (the license gate judges
    it). `/api/me/access`: `org_selection.required`, `available` (= ≥2 eligible), `eligible_orgs`.
    A customer-role PROFILE keeps the old path (home; no picker). **Q3**
    `noctus_users.org_id/org_role` = the LAST-ACTIVE org and follow the pick (with the membership
    role, in the RPC's transaction, before the selection row is written); the 079 mirror trigger
    then upserts the identical membership, so a pick never ends or downgrades one. The 070 trigger
    ends the user's other live selections when the mirror moves — the last-active org is ONE value.
  - **Revocation by recheck (S3):** `current_org_id_for` joins `org_memberships` (`status='active'`)
    on every call — ending a membership makes the selection stop resolving on the next query, and
    the HOME fall-back itself requires an ACTIVE membership, so a removed member never falls back to
    the org they were removed from (NULL). Nothing in the JWT. The pin header only narrows.
  - **Audit:** the selection row is the record of a switch (user, target, previous home, login,
    `started_at`/`ended_by`); a member is never "acting" (`EffectiveOrg.acting` is staff-only), so
    their writes carry the plain actor with `org_id` = the selected org — no `platform_support` tag.
  - **Invariant, enforced by the DB:** a profile's org is always an ACTIVE membership. Ending
    (or deleting) the membership a profile points at is refused at COMMIT
    (`org_memberships_profile_org_active`, a deferred constraint trigger, core
    `org_member_selection`) unless the profile moves or is deleted in the same transaction. That
    is why the Python home path and every non-picker reader may trust `noctus_users.org_id`
    without re-reading memberships: revocation-safety is one DB rule, not a query in each reader.
    S4's remove-member must therefore move or delete the profile in the same transaction.
  - **Team = memberships (S4, core `team_membership_ops`).** "Members of org X" is the ACTIVE
    `org_memberships` of X, never `noctus_users.org_id` (a user's LAST-ACTIVE org): the team list
    (role shown = the membership role), seat counts (`check_user_limit`), `notify_team`, SSO cache
    org-invalidation and the tenant-health user count all read memberships
    (`app/services/team_memberships.py`). The three writes are SECURITY DEFINER functions
    (service_role only) called over RPC because PostgREST sequences are not transactional:
    `team_member_remove` (end the membership; if it was the profile org, move the profile to the
    most recently updated other ACTIVE membership with that membership's role, else delete it; end
    the user's live selections for the org), `team_member_set_role` (membership role + the profile
    mirror ONLY for the profile org), `team_invitation_accept` (an EXISTING user: activate or
    re-activate a `removed` membership with the invited role, link `invited_by`/`invitation_id`,
    mark the invitation accepted — the profile does NOT move; `active` → 409, `suspended` → 403,
    an invitation never lifts a suspension). A first-time invitee still gets a profile in the
    inviting org (the 079 trigger mirrors the membership). Refusals are `team_membership:<code>`
    mapped to strict statuses in `ERROR_MAP`; the last ACTIVE owner can be neither removed nor
    demoted (SQL, serialised on the org row) and the router additionally keeps an `owner` target
    untouchable (403) for everyone but platform staff (S4b, D2). A sole-membership profile is never
    deleted any more (S4b, D4 — below).
    **SSO admission** (`/api/sso/token`, `/launch`): admitted when ANY ACTIVE non-customer
    membership is in an org licensed for the product (profile org first, then most recently
    updated); the token carries the admitting org and the role in it; the org the product then
    ACTS in is the resolver's job. Probes: `team_member_remove.refuses_last_owner`,
    `team_member_set_role.refuses_demoting_last_owner`,
    `team_member_remove.moves_profile_in_the_same_transaction`,
    `team_invitation_accept.refuses_an_active_member`; behaviour on real Postgres:
    `mcp/noctusai/tests/test_core_team_membership_ops_on_replay.py`.
  - **Access rules (S4b, owner decisions D2–D5 2026-10-14, core `member_access_rules`).** API
    contract: roadmap § S4b API contract.
    - **D2 platform powers.** Platform staff (`platform_staff_role`, Python + SQL twins: the
      resolver's staff rule; `owner` = THE NoctusAI owner, `admin` = a NoctusAI admin) manage ANY
      org's team: every team route takes `?org_id=` (another org needs staff or an ACTIVE
      owner/admin membership there). Only the NoctusAI owner overrides the last-owner rule — decided
      in SQL from the ACTOR passed to `team_member_remove/_set_role/_move` (4-arg/6-arg forms; the
      082 signatures are wrappers with no actor = no override), never from a caller flag.
    - **D3 moves.** `team_member_move(actor, user, source, target, role, mode)`, `POST /api/team/move`:
      staff anywhere, an org owner/admin only between orgs they own/admin BOTH of
      (`org_manager_role`); `transfer` ends the source (last-owner rule) and moves the profile when it
      pointed at the source, `add` keeps it; role never above the actor's role in the target (staff
      = owner). `PATCH /api/admin/users/{id}` reassignment is a `transfer` through it (metadata
      synced first, restored if the move is refused).
    - **D4 detached profile.** Removing a user whose ONLY active membership is this org moves the
      profile to a personal org of their own (`Pessoal — <nome>`, `indv_<slug>`, `is_personal`,
      owner) in the removal transaction; the org is made through the ONE org path
      (`app/services/org_provisioning.py`, shared with signup and OAuth signup) and validated in SQL
      (owned by the user, `is_personal`, no members) — never a profile delete. First-time invitees go
      through `team_invitation_accept(inv, user, nome)` too: profile + membership linked
      (`invited_by`/`invitation_id`) + invitation accepted, one transaction.
    - **D5 product blocks.** `public.org_member_product_access` (a LIVE row = blocked; append-only
      history closed by `unblocked_at/_by`; RLS self-read; written only by
      `org_member_product_access_set`, owner/admin or staff, block needs a license and ends a live
      selection of that org). Blocked ⇒ not eligible (D1), `platform_org_selection:product_blocked`,
      SSO never admits through it, the resolver/`current_org_id_for` never resolve to it (home
      included, picker-ready or not), `/api/auth/me` `has_access=false`. Routes:
      `GET|PUT /api/team/{user_id}/product-access[/{slug}]`.
    - Probes: `current_org_id_for.member_with_two_eligible_orgs_and_no_selection_is_null`,
      `.member_with_one_eligible_org_lands_there`, `.blocked_org_is_never_resolved`,
      `platform_org_selection_set.refuses_blocked_member`, `org_member_product_access.one_live_block`
      / `.append_only` / `.unblocked_by_needs_at`,
      `team_member_move.refuses_an_actor_who_does_not_manage_both_orgs`,
      `team_member_remove.sole_member_keeps_the_profile_in_a_personal_org`; real Postgres:
      `mcp/noctusai/tests/test_core_member_access_rules_on_replay.py`.
  - **Front end (S5, 2026-10-14).** No member-specific flow: `useOrgSelection` keys everything off
    `org_selection.available`, so a member with ≥2 eligible orgs gets the staff entry handshake
    as-is (no marker ⇒ `DELETE /api/me/org-choice` ⇒ required picker ⇒ choice ⇒ marker + reload;
    cross-tab rule 1A) — a pick lasts ONE visit, never the whole login. Member vs staff is only
    presentation, from `isMemberOrgPicker(sel)` (`available && manage_any_org === false`; absent on
    a pre-S4b backend = staff): `OrgPickerModal` keeps the server order (last-active first), names
    the role IN each org and marks the current one "Atual"; `ActingAsBanner` (and its slim bar)
    render for staff only; the member switches from `<OrgSwitcher/>` in the seed shell header
    `actions`, which opens the same picker. Single-org members: `available=false`, no popup, no
    switcher. Core `/team` (`hooks/useTeam.ts`): org selector over `manageable_orgs` (staff:
    `/api/organizations`, acting as owner), every team call `?org_id=`, "Mover" (target + role
    capped by the actor's role there + mode chosen each time, none preselected), "Acessos" (switch
    per licensed product), removal copy for D4. Refusals reach the client as `{detail, code}`
    (`team_memberships._call`) and `lib/team-errors.ts` maps each contract code to pt-BR.
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
