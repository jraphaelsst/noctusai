# multi-org-membership-2026-10 — one user ↔ many orgs; the brand belongs to the org

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: simulating a real customer-owner inviting a teammate into her new org (2026-10-12) exposed that a user can belong to exactly one org, and that brand/design-system data sits inside one org as rows.
> Decision: **ship the membership table expand-only today (S1); widen the existing platform org picker from "staff" to "members" next, pilot-first; absorb the customer's legacy org into her real account only on the owner's go.**
>
> No personal data here by design — customer identities live in the session/DB, never in git.

## Origin

The platform owner asked for a teammate to be invited into a customer's new company org and for the customer's legacy org data to be absorbed into her real account. The target: one person owns several orgs — a company, her personal brand, possibly 1–2 more companies — and each org carries its own brand + design system.

Evidence (prod, 2026-10-12):
- `public.noctus_users.org_id` is a single NOT NULL uuid = the only membership record. Core `team.py` accept-invite answers 409 "Você já pertence a outra organização" to anyone with an org.
- Accept-invite was ALSO broken for every first-time invitee (`.single()` → PGRST116 → bare 404) — fixed on dev `d73a333bf`, not yet on prod.
- The customer's legacy org (placeholder owner account, never signed in) holds BOTH brands as `social_wiring.marcas` rows (personal `pessoa_fisica` primary + company `empresa`), the company's brand kit (components + logos) attached to the WRONG marca (the personal one), an agent with ~600 `agents.*` rows, licenses agents + social-wiring. Brand assets are stored under `<legacy_org_id>/branding/...` paths.
- The customer's new company org (created at real signup) is empty but a social-wiring license.

Architect Phase-0 (2026-10-12): the platform org picker (core 070, `resolve_effective_org`, `current_org_id_for`, `OrgSelectionGate`) already carries a chosen org into backend + RLS; it is staff-only and license-scoped. Generalize, don't fork.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | S1 applied on prod | `select count(*) from public.org_memberships` = `noctus_users` count | readers can start trusting the table |
| T2 | Owner answers the open decisions (Q1–Q6) | decision log entry | S2/S3 semantics depend on them |
| T3 | Sibling branch `feat/org-picker-postgrest-entry` (core 078) integrated | it appears in `origin/dev` | S2/S3 touch the same resolver/RLS helper — never in parallel with it |
| T4 | Owner says "go" on the legacy-org absorption | decision log entry | moves real prod data + storage objects |

**Today's status (2026-10-14)**: T1 ✅ (079 on prod; every profile has its active home membership) · T2 ✅ (defaults 2026-10-13, then owner decisions D1–D5 2026-10-14 — see decision log) · T3 ✅ (078 on prod) · T4 ✅ (absorption done). Phase 2 is unblocked; S4b built on its branch.

> Every slice carries a test-recipe AND a verify-recipe (live state). Tests-green ≠ verified-in-production.

## Phase 1 — the membership list exists (SHIPPED to prod)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.0 | accept-invite works for first-time invitees | EDIT `products/core/backend/app/routers/team.py`, `seed/lib/backend/noctusai_lib/testing/mocks.py` (opt-in `strict_single`) | **shipped (dev `d73a333bf`)** | after prod deploy: rerun the pending invite's accept → 200; invitee profile in the inviting org; invitation `accepted` |
| P1.1 | `public.org_memberships` + mirror trigger + backfill | NEW `products/core/backend/migrations/079_org_memberships.sql`, NEW `products/core/backend/tests/test_migration_org_memberships.py` | **shipped (prod)** — replay green ×2; verified 2026-10-13 | after `migrate_product core`: membership count == profile count; inserting a profile creates its membership |

**Behavior guarantee**: no runtime change — nothing reads `org_memberships` yet; `noctus_users` stays the source for every reader.

**Why ship now**: every later slice reads it; expand-only is zero-risk.

## Phase 2 — members can switch orgs (DEFERRED — T1 ∧ T2 ∧ T3)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P2.1 (S2) | resolver + selection store accept members; role = membership role in the EFFECTIVE org | `seed/lib/backend/noctusai_lib/api/auth/effective_org.py`, `org_selection.py`, framework `me_router.py` + Fake store (`get_org_id`/`get_user_role` stay home-only: the profile mirror follows the pick, Q3) | **built on branch `feat/multi-org-s2-s3-member-selection` (not yet on dev/prod)** | a member of 2 orgs gets each org's data + role on social-wiring; owner-in-A/viewer-in-B is viewer in B (`verify_db_guards`) |
| P2.2 (S3) | `current_org_id_for` honours member selections + re-checks membership; ending a membership ends live selections | NEW core migration `org_member_selection` (+ `platform_org_selection_set` widened) + `sql_templates.py` renderer (parity baseline re-ratified for 078's now-historical copy) | **built on branch `feat/multi-org-s2-s3-member-selection` (not yet on dev/prod)** | RLS probe: a removed member's selection falls back to home on the next query |
| P2.3 (S4) | accept-invite adds a membership (no 409); remove-member ends it (no profile delete); SSO admits any licensed membership | core `team.py`, `sso.py` (+ `services/team_memberships.py`, `entitlements.py`, `notification_service.py`, `analytics.py`, NEW core migration `team_membership_ops`: 3 service-role RPCs) | **built on branch `feat/multi-org-s4-team-memberships` (not yet on dev/prod)** | invite an existing user into a 2nd org → 200; both orgs listed |
| P2.3b (S4b) | owner decisions D1–D5: choice on every entry with ≥2 eligible orgs; platform owner/admin powers; move user (transfer \| add); sole-org removal keeps the profile in a personal org; per-member product blocks | NEW core migration `083_member_access_rules`; seed `effective_org.py`, `org_selection.py` (`blocked_orgs`), `sql_templates.py`, framework `me_router.py`; core `team.py`, `sso.py`, `auth.py`, `oauth.py`, `users.py`, `services/team_memberships.py`, NEW `services/org_provisioning.py` | **built on branch `feat/multi-org-s4b-access-rules` (not yet on dev/prod)** | a 2-org member gets `409 org_selection_required` on a fresh login, picks, works; blocking them in one org lands them silently in the other; removing a sole-org member leaves their profile owner of `Pessoal — <nome>` |
| P2.4 (S5) | picker lists member orgs; required with ≥2 eligible orgs on EVERY entry (D1: the seed entry handshake — `DELETE /api/me/org-choice` on entry — extended to members); AppShell switcher; team UI for move/block (contract below) | `seed/lib/frontend/src/access.ts`, `org-selection.ts`, `OrgPickerModal.tsx`, `ActingAsBanner.tsx`, NEW `OrgSwitcher.tsx`, framework `layout.tsx`; core `TeamManagement.tsx` + NEW `hooks/useTeam.ts`, `pages/team/*`, `lib/team-errors.ts`, `AdminUsers.tsx` copy; core `services/team_memberships._call` sends `{detail, code}` | **built on branch `feat/multi-org-s5-switcher-ui` (not yet on dev/prod)** — no member-specific flow: the staff entry handshake already keys off `available`, so members get it as-is | a 2-org owner switches between orgs in the shell; a fresh SSO entry re-asks; a 1-org member sees no popup; `/team` moves a member (transfer and add) and blocks a product |
| P2.5 (S6) | pilots: social-wiring, community, igig (already picker-ready) → fan-out | per-product | after S5 | wiring audit per pilot |
| P2.5b (S6b) | the PRODUCT team router (seed `noctusai_seed/routers.py`, mounted by every product's Equipe) on `org_memberships`: roster = ACTIVE memberships of the effective org (today `noctus_users.org_id` = last-active org, so a member whose last pick is elsewhere vanishes); accept-invite adds a membership instead of 409 "já pertence a outra organização" (today `attach_user_to_org` is single-org) — consume core's `team_invitation_accept` RPC + lift the roster reads (`list_team` & co.) to seed lib | seed framework `routers.py`, seed lib `domain/org.py`, core `services/team_memberships.py` (lift) | **built 2026-10-14 (`multi-org-s6b-product-team`)** | a member of 2 orgs appears in SW Equipe of both; an existing user accepts a SW invite into a 2nd org |

**Why not now**: T2/T3 — semantics undecided and a sibling branch owns the same resolver.

### S4b API contract (contract-first — S5 builds the FE on it)

Seed, mounted on every product (`create_me_router`):

| Route | Change |
|---|---|
| `GET /api/me/access` | `org_selection` gains `eligible_orgs: [{id, nome, org_role, is_home}]` (this product's ELIGIBLE orgs for a non-staff user: ACTIVE, non-customer membership, org licensed, not blocked; home first then by name; `[]` for staff), `platform_role: "owner"\|"admin"\|null`, `manage_any_org: bool` (= platform staff), `manageable_orgs: [{id, nome, org_role}]` (the caller's ACTIVE owner/admin memberships). `required` (member) = ≥2 eligible orgs and no valid live selection (D1); `available` (member) = ≥2 eligible orgs. Every other field unchanged. |
| `GET /api/me/org-choices` | members: eligible orgs only (blocked ones excluded). |
| `PUT /api/me/org-choice` | new `403 {"code":"product_blocked"}` (D5). |
| any gated route | a member with ≥2 eligible orgs and no valid selection → `409 {"code":"org_selection_required"}` (was: only when the last-active org was unlicensed). Exactly one eligible org → served silently (it may differ from the profile org; the profile does not move). |

Core:

| Route | Contract |
|---|---|
| `?org_id=` on `GET /api/team`, `POST /api/team/invite`, `DELETE /api/team/{user_id}`, `PATCH /api/team/{user_id}/role`, `GET /api/team/invitations`, `DELETE /api/team/invitations/{id}` | default = the caller's profile org (behaviour unchanged). Another org: platform staff (any org; unknown org 404) or an ACTIVE owner/admin member of it; else `403`. Staff may remove/re-role an `owner` (D2); the LAST owner only by the NoctusAI owner (`409` otherwise). |
| `PATCH /api/team/{user_id}/role` | `role: "owner"` only by platform staff (P1, core 084) — anyone else `403 owner_grant_forbidden` (was: `owner` refused for everyone). Other rules unchanged. |
| `POST /api/team/move` | body `{user_id, source_org_id, target_org_id, role, mode: "transfer"\|"add"}` → `200 {data: {user_id, source_org_id, target_org_id, org_role, mode, previous_org_role, source_ended, profile_moved, reactivated, selections_ended}}`. `400` invalid role / `invalid_mode` / `same_org`; `403` `forbidden` (not owner/admin in BOTH orgs, not staff) / `owner_grant_forbidden` (`role: "owner"` by a non-staff actor, P1) / `role_above_actor` / `membership_suspended` (target); `404` `not_a_member` (source) / `org_not_found`; `409` `last_owner` (transfer) / `already_member` (target); `422` schema; `401` no auth. |
| `GET /api/team/{user_id}/product-access?org_id=` | `200 {data: {user_id, org_id, can_edit, target_is_staff, products: [{product_id, slug, nome, blocked, blocked_at, blocked_by}]}}` — every product the org is licensed for. `can_edit` = the caller may change it (org OWNER or staff, P5); `target_is_staff` = never blockable (P3). `403` unless staff / owner / admin of the org (an admin reads only); `404` not an active member. |
| `PUT /api/team/{user_id}/product-access/{product_slug}?org_id=` | body `{blocked: bool}` → `200 {data: {user_id, org_id, product_id, product_slug, blocked, changed}}` (idempotent). `403` `forbidden` (not the org's OWNER nor staff — an org admin since P5); `404` `product_not_found` / `not_a_member`; `409` `not_licensed` (block only) / `cannot_block_staff` (block of platform staff, P3). |
| `DELETE /api/team/{user_id}` | `200 {message, data: {removed: true, profile_moved_to: <org_id>\|null, personal_org_id: <org_id>\|null}}` (S5b) — `profile_moved_to` = the org the profile now points at (`null` = this org was not the profile org, nothing moved); `personal_org_id` set ONLY when a personal org was created for a sole-org member (D4; then `profile_moved_to` = the same id). The `409 profile_in_use` is gone. Read straight from the `team_member_remove` RPC result (083) — no SQL change. |
| `PATCH /api/admin/users/{id}` with `org_id` | a `transfer` through `team_member_move` (old membership ENDS). Refusals as `/move`. |
| `GET /api/auth/me` | `products[].has_access` is `false` for a product the user is blocked from in their profile org (D5). |

## Phase 3 — the brand is the org's (DEFERRED — after Phase 2 pilots)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P3.1 | seed org brand: `public.org_brands` (tokens, logo, palette, type) + `/api/me/brand` + `BrandProvider` organ theming the AppShell | core migration, seed lib/framework | Phase 2 done | switching org re-themes the shell |
| P3.2 | social-wiring `is_primary` marca = projection of the org brand (never authored twice); extra marcas stay for multi-brand companies | social-wiring | P3.1 | the company kit shows as the company org's brand |
| P3.3 | therapy `clinic_branding` onto the org brand (N=2 consumer) | therapy | P3.1 | clinic theme comes from the org brand |

## Phase 4 — absorb the legacy org (DONE 2026-10-13 — shape changed, see decision log)

1. Company org: receives the company marca, its brand kit **re-attached to the company marca** (+components, +references; storage objects COPIED under the company org prefix, paths rewritten), the agent + all its `agents.*` rows, an agents license.
2. Legacy org becomes the personal-brand org: owner → the real account, `is_personal`, keeps the personal marca + historical ledgers.
3. Real account gets an ACTIVE owner membership there; placeholder account's membership removed, account retired.
4. Verify: per-table row counts before/after; logo URLs resolve; the agent answers in the company org.

Exact IDs: reproduce from the DB at T4 (never committed).

## Anti-goals

- ❌ A second org-switching mechanism. The org picker is the one mechanism.
- ❌ Org/role in a JWT claim. RLS keeps re-checking via function (revocation-by-recheck).
- ❌ Deleting `social_wiring.marcas`. `marca_id` is load-bearing in 22 tables; multi-brand companies stay.
- ❌ Per-product membership tables. One `public.org_memberships`.

## Open questions (owner — T2)

Answered 2026-10-13 (decision log) — kept for the record.

- **Q1** Do regular members need MFA (aal2) to switch orgs, or only staff?
- **Q2** Must a multi-org user choose on every product entry, or only when the last-active org isn't licensed for it?
- **Q3** `noctus_users.org_id`: follows the last selection, or a fixed home?
- **Q4** Should `pessoa_fisica` marcas eventually become personal orgs?
- **Q5** One brand per org, or per-product overrides?
- **Q6** Does joining a second org need approval from the invitee's home org?

## Decision log

- **2026-10-12**: Generalize the platform org picker (architect Phase-0) instead of a new mechanism; S1 expand-only membership table shipped to dev; accept-invite first-time-invitee 404 fixed on dev.
- **2026-10-12**: Mock fidelity — the shared mock's lenient `.single()` hid the 404. `strict_single` opt-in shipped; flipping the default reds 5 more core tests (licenses check-access ×3, products detail ×2, website-settings rollback) — same probable live-404 class. NOC-REMEDIATE destination: slice "mock-fidelity" here (fix those call sites, then default `strict_single=True` fleet-wide).

- **2026-10-13 (T2)**: Owner accepted the recommended defaults ("go on"): **Q1** MFA to switch orgs only for staff, never for regular members · **Q2** a multi-org user chooses only when the last-active org isn't licensed for the product · **Q3** `noctus_users.org_id` follows the last selection (it is the "last-active" org, not a fixed home) · **Q4** yes — `pessoa_fisica` marcas become personal orgs · **Q5** one brand per org (no per-product overrides) · **Q6** joining a second org needs no approval from the home org.
- **2026-10-13 (T1/T3)**: 079 and 078 both on prod; T1 signal holds (every profile has its active home membership).
- **2026-10-13 (T4)**: Legacy org absorbed by IDENTITY SWAP instead of a data move (see Retrospective): the legacy org became the company org (keeps agent, kit, logos, licenses; kit re-attached to the company marca); the signup org became the personal-brand org (gets the personal marca); real account owns both via memberships; placeholder account removed from the org and banned (reversible), not deleted. Phase 4's original COPY plan is superseded.
- **2026-10-13**: Phase 2 starts: S2+S3 together in one slice — the backend resolver and `current_org_id_for` must agree on who may select an org, so they ship and are tested together.
- **2026-10-13 (S2+S3 review)**: Accepted: a non-staff pin mismatch returns 409 (the SPA pins only the resolved org and handles 409 globally); picking an org on one product ends the user's live selections on other products (consequence of Q3 — the last-active org is one value). Refused: leaving the Python home path trusting a profile whose membership was ended. Closed at the root instead — a deferred constraint trigger makes "a profile's org is an ACTIVE membership" a DB invariant, so no reader needs an extra query and S4 cannot forget it.

- **2026-10-13 (S4 built)**: Team = memberships. Accept-invite for an existing user (RPC `team_invitation_accept`) activates/creates the ACTIVE membership (profile untouched; `removed` re-activates with `ended_at` cleared; `suspended` is REFUSED 403 — an invitation must not lift an org's suspension; replay/active member 409). Remove-member (RPC `team_member_remove`, one transaction) ends the membership and, when it was the profile org, moves the profile to the most recently updated other ACTIVE membership or deletes it; it also ends the user's live selections for that org. Role change (RPC `team_member_set_role`) updates the membership and the profile mirror only for the profile org. Last-owner removal/demotion refused in SQL (serialised on the organizations row); the router's stricter existing rule (an `owner` target is untouchable here, 403) is unchanged. Listing, seat counts (`check_user_limit`), `notify_team`, SSO cache org-invalidation and the tenant-health user count now read ACTIVE memberships. SSO admits through ANY active non-customer membership in a licensed org (profile org tried first) and the token names the admitting org + the role in it. Known pre-existing hazard surfaced as a typed 409 (`profile_in_use`): deleting a sole-membership profile that still owns invitations/api_keys/audit rows fails on FKs without cascade (was a bare 500 before). Not touched: platform-admin `PATCH /api/admin/users/{id}` org reassignment (moves the profile; the old membership stays ACTIVE — a multi-org-consistent outcome, but the "revoke" wording in its docstring is now stale) — candidate cleanup.
- **2026-10-14 (S4 review)**: Accepted `suspended` → 403 on accept. Accepted the typed 409 `profile_in_use` for now (not a regression — it was a bare 500 before), but it is NOT the end state: almost every real user has append-only audit rows, so a sole-org member effectively can't be removed. Follow-up slice **S4b "detached profile"** (NOC-REMEDIATE destination): a removed sole-org user keeps their profile (audit history intact) in an auto-created personal org, like signup creates one, instead of a profile delete. Same slice: the platform-admin org-reassignment endpoint ends the old membership (today it stays ACTIVE), and first-time invitees get `invited_by`/`invitation_id` linked on their membership.

- **2026-10-14 (owner decisions D1–D5, verbatim intent; implemented on `feat/multi-org-s4b-access-rules`, core `083_member_access_rules`)**:
  - **D1** "Org picker = the SAME shared seed mechanism NoctusAI staff use ('every entry is a choice', core 078 + `OrgSelectionGate`), made dynamic per user × product: a NON-staff user is prompted on every entry into a product iff they have >=2 ACTIVE, non-customer memberships in orgs licensed for THAT product (and not blocked by D5). Exactly one eligible org → land there silently, no popup." **Replaces Q2 (2026-10-13).** Members still need no aal2 (Q1). Python resolver and `current_org_id_for` agree (parity baseline re-ratified: 081's copy is now historical).
  - **D2** "NoctusAI owner AND NoctusAI admins can manage ANY org's team (invite, remove, role change, move). ONLY the NoctusAI owner may override the 'never remove/demote an org's last owner' rule; NoctusAI admins and everyone else stay refused." Staff = `noctus_users.role='admin'` + home `org_role` owner/admin + home `is_platform` (the resolver's rule); NoctusAI owner = that home `org_role='owner'` (`platform_staff_role`). The override is decided in SQL from the ACTOR, never from a caller flag.
  - **D3** "NoctusAI owner/admins can move any user between any orgs. An org owner/admin can move a user only between orgs where the ACTOR is owner/admin in BOTH. Each move, the actor CHOOSES the mode: `transfer` or `add`. Target role chosen by the actor, never above the actor's own role in the target. Fix the platform-admin `PATCH /api/admin/users/{id}` org reassignment to go through this same op. Last-owner rule applies to `transfer` out of an org (D2 override only for NoctusAI owner)." Staff act as `owner` in any org for the role cap.
  - **D4** "Removing a user whose ONLY active membership is this org must NOT delete their profile. Instead, in the same transaction, give them a personal org of their own (individual, `is_personal`, slug pattern like signup's `indv_<slug>`), make them its owner, move the profile there. This replaces the typed 409 `profile_in_use`. Also: first-time invitees get `invited_by`/`invitation_id` linked on their membership." The org is created through the ONE org path (`services/org_provisioning.py`, now also used by signup + OAuth signup — the slug rule had been copied twice) and validated by the removal transaction (owned by the user, `is_personal`, empty); an unused one is discarded.
  - **D5** "Per-user product access: inside an org licensed for a product, an org owner/admin (and NoctusAI owner/admins) can BLOCK a specific member from that product, and unblock. Blocked ⇒ not an eligible choice (D1), SSO does not admit through it, the resolver/`current_org_id_for` never resolve to it, it doesn't show in their dashboard for that org. Default = allowed (no row = access)." Design: table `public.org_member_product_access` (one row per block, append-only history; FK to the membership; RLS self-read, service-role writes through `org_member_product_access_set`), chosen over a column on `org_memberships` (FK to products impossible in an array, per-entry who/when audit, and writing the membership row re-fires the 079/081 triggers and bumps the `updated_at` the removal uses to pick the next org).
  - Open points surfaced (not decided here, see the S4b report): a D3 move may grant `owner` (owner actor / staff) while the role-change route keeps refusing owner grants; an admin reassignment into an org the user is already active in is `409 already_member` (was a silent profile move); a block survives a removal + re-invite (it hangs off the membership row); staff selections are not subject to D5 blocks (D5 names members).

- **2026-10-14 (S5 built, `feat/multi-org-s5-switcher-ui`)**: D1's "every entry" for members needed NO backend change and no FE branch — `useOrgSelection`'s entry handshake was already keyed off `org_selection.available`, which S4b sets for ≥2 eligible orgs; tests now pin it for members (leftover pick ended on entry, 1-org member silent, 2nd org gained mid-visit re-prompts). Presentation only differs (`isMemberOrgPicker`): member list in server order with the role per org, `ActingAsBanner` staff-only, new header `OrgSwitcher`. One backend touch: the RPC refusals (`team_memberships._call`) reached the client as a plain-string detail (generic `FORBIDDEN`/`HTTP_ERROR` code), so the contract's codes were not observable — they now ride as `{detail, code}` (seed flat error shape), asserted in `test_team_access_rules.py`.

- **2026-10-14 (S5b built, `feat/multi-org-s5b-effective-org-shell`)**: The seed shell showed the SSO TOKEN's org/role (the org that admitted the user), so after a switch the subtitle, role label, nav role filter and `useIsOrgAdmin` stayed on the org the user left. Now one resolver, `resolveEffectiveSSOContext(metadata, access)` (seed lib `sso.ts`), re-bases `org` / `isProductAdmin` / `orgId` on `/api/me/access` (`org` + `org_selection.org_role`); the token stands in ONLY while access has not answered (`orgSource: 'token'`), an answered access with no org never shows the token's org, a pre-picker backend (no `org_role` key) keeps the token role (no switch possible there). Consumers: framework `layout.tsx`, `useIsOrgAdmin` (via `useEffectiveSSOContext`), `LLMSpendBadge` (role AND org id now from the same effective org — it used to pair the effective-ish gate with the token's `org_id`), igig's local `useIsOrgAdmin` (a re-implementation over `user_metadata`) now re-exports the seed hook. All share ONE `/api/me/access` query (`useMeAccess`). `DELETE /api/team/{id}` returns what happened (contract above) and core's remove toast says it in pt-BR. Not touched (S6 fan-out): ~20 product files still call `resolveSSOContext(user_metadata)` / `isOrgAdmin(resolveSSOContext(...))` directly (social-wiring components + `useLayoutEnrichment`, adconnect/agents/daily-life/orbity/knowledge-extractor/personal-finance pages, igig `LinkPreQualificacao`) — they keep the token role after a switch; plan/subscription/license in the shell are still the token org's.

- **2026-10-14 (owner decisions P1–P5, verbatim; implemented on `feat/multi-org-s5b-effective-org-shell`, core `084_owner_grant_and_block_rules`)**:
  - **P1** "Granting the role `owner` (in an org) is allowed ONLY to NoctusAI owner and NoctusAI admins (platform staff, `platform_staff_role` owner|admin). That covers BOTH the role-change route (PATCH role) AND `POST /api/team/move` target role. An org owner may no longer grant `owner` through either; refuse with a typed code (e.g. 403 `owner_grant_forbidden`). Enforce it in SQL (from the actor passed in, like the last-owner override) and in Python, and update the S5 move dialog and the role selector so `owner` is offered only to staff." Closes the S4b open point (move could grant `owner` while the role-change route refused it for everyone): both now grant it to staff only. Re-stating an existing owner's role is not a grant. Invitations unchanged (never grant `owner`) — P1 names only the two routes.
  - **P2** "D5 blocks survive removal and re-invite: no change, keep it. Add a test pinning it if one doesn't exist." Pinned: `p2_block_survives_removal_and_reinvite` (replay).
  - **P3** "NoctusAI staff can never be blocked. Refuse a block whose target is platform staff with a typed code (e.g. 409 `cannot_block_staff`), in SQL and Python, and hide or disable the toggle for staff in the 'Acessos' dialog." Unblocking an existing row stays allowed (cleans a block written before 084). Closes the S4b open point on staff vs D5.
  - **P4** "`manager` scope: unchanged. A manager manages only their own current org's team."
  - **P5** "Blocking or unblocking a member's product access is allowed ONLY for that org's OWNER, plus NoctusAI owner and admins. Org ADMINS may no longer do it: refuse with 403 `forbidden`, in SQL `org_member_product_access_set` and Python, and in the UI hide 'Acessos' toggles for org admins (read-only view is fine)." The GET now says `can_edit` / `target_is_staff` so the dialog renders read-only / without a switch.

- **2026-10-14 (owner decision, verbatim)**: Q "should NoctusAI staff be able to invite someone directly as an org owner?" — "no, only after they've joined, then we grant." Invitations never carry `owner` (unchanged); ownership is granted after joining, by NoctusAI owner/admins only (P1).

- **2026-10-14 (S6 built, `multi-org-s6-effective-context`)**: Every ACTIVE-scope product reads the EFFECTIVE org, not the SSO token: social-wiring's 7 admin gates (`ContratosContainer`, `ClienteDetailModal`, `ConflitosPendentesPanel`, `AntigosProprietariosPainel`, `EmpresasSection`, `ImovelConflitosCard`, `Settings`) → `useEffectiveSSOContext`; agents' `useIsAdmin` re-exports the seed `useIsOrgAdmin` (as igig's did in S5b); agents/seed Dashboards show the effective org; igig's pré-qualificação link names the effective org and is HIDDEN until `/api/me/access` answers (a link copied from the token stand-in could route leads to the org just left); seed `TeamPage` invite/admin gates follow the effective role. `meAccessQueryOptions` (seed `access.ts`, dependency-free) is now THE `/api/me/access` query definition — `useMeAccess`, `useMeAccessIfProvided` and `TeamPage` (which holds its own `api`, no infra import) share one cache entry. Not touched: inactive products (adconnect, daily-life, orbity, personal-finance, knowledge-extractor, erp-imobiliario — asleep per the catalog); core `AdminAuditDigest` (core staff page, own org resolution); SW `useLayoutEnrichment` (label from the roster; falls back to the effective role when the own row is absent — correct once S6b lands); plan/subscription/license in the shell (still the token org's). Found: the product team router is single-org → S6b.

- **2026-10-14 (S6b built, `multi-org-s6b-product-team`; owner go: "Ok, build it")**: The seed product team router (every product's Equipe) now follows `org_memberships`. Roster = `noctusai_lib.domain.org_memberships.list_member_profiles` (ACTIVE memberships of the effective org; role = the role THERE; staff/customer filter in the query) — a NEW seed-lib module; core's `services/team_memberships.py` now re-exports its reads from it (one definition, core + products). Accept: `attach_user_to_org` → `join_org` — an existing person joins (no single-org 409), profile and `user_metadata` stay on their home org (picker reaches the new one; same as core's accept), `removed` re-activates, `suspended` → 403, already ACTIVE → own role wins (different invited role still 409). `owner` is never invitable: `TeamPolicy.NEVER_INVITABLE_ROLE` (default invitable drops it; a policy declaring it is refused at construction), router refuses it on invite AND accept (403; prod had 0 pending owner invitations across the 16 product schemas, checked 2026-10-14). No migration: product invitations live in each product schema (core's `team_invitation_accept` reads `public.invitations` only), and a join is a single-row write. Fixed on contact: `MockSupabaseClient.maybe_single()` on 0 rows returned `[]` (real postgrest-py: no row) — it hid `is None` branches; seed-lib suite unchanged otherwise (10 732 passed). NEW test helper `noctusai_lib.testing.memberships.seed_profiles` (the mock has no 079 trigger).

## Retrospective (filled at first trigger fire)

- **Phase 4's plan was wrong in a way only the DB could tell.** It said "move the agent + all its `agents.*` rows". Published versions, compiled prompts, package trees and the agent audit log are guard-immutable — moving them means switching our own guards off. The org that already held them took the company identity instead (identity swap): ~15 rows changed, zero storage copies, zero guards touched. Lesson: when a plan says "move rows across orgs", list the immutability guards on those tables first.
- **A stale toolkit produced a false red.** The predeploy run inside a long-lived MCP server still carried pre-078 probe names, so `db_guards` failed on probes that no longer exist in the tree. A fresh `cli.py --predeploy-check` was green. The result already carried `toolkit_stale`; read it before believing a red.

## Composes with

`KB § PATTERNS/backend/tenancy-license-gate.md` (§ Platform org picker) · `KB § PATTERNS/architect/seed-canonical-defaults.md` · `KB § PATTERNS/frontend/product-internal-wiring.md`
