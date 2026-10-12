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

**Today's status**: none fired. S1 shipped to dev (not applied on prod).

> Every slice carries a test-recipe AND a verify-recipe (live state). Tests-green ≠ verified-in-production.

## Phase 1 — the membership list exists (SHIPPED to dev)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.0 | accept-invite works for first-time invitees | EDIT `products/core/backend/app/routers/team.py`, `seed/lib/backend/noctusai_lib/testing/mocks.py` (opt-in `strict_single`) | **shipped (dev `d73a333bf`)** | after prod deploy: rerun the pending invite's accept → 200; invitee profile in the inviting org; invitation `accepted` |
| P1.1 | `public.org_memberships` + mirror trigger + backfill | NEW `products/core/backend/migrations/079_org_memberships.sql`, NEW `products/core/backend/tests/test_migration_org_memberships.py` | **shipped (dev)** — replay green ×2 | after `migrate_product core`: membership count == profile count; inserting a profile creates its membership |

**Behavior guarantee**: no runtime change — nothing reads `org_memberships` yet; `noctus_users` stays the source for every reader.

**Why ship now**: every later slice reads it; expand-only is zero-risk.

## Phase 2 — members can switch orgs (DEFERRED — T1 ∧ T2 ∧ T3)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P2.1 (S2) | resolver + selection store accept members; role = membership role in the EFFECTIVE org | `seed/lib/backend/noctusai_lib/api/auth/effective_org.py`, `org_selection.py`, framework `dependencies.py` (`get_org_id`, `get_user_role`) + Fake store | T1∧T2∧T3 | a member of 2 orgs gets each org's data + role on social-wiring; owner-in-A/viewer-in-B is viewer in B (`verify_db_guards`) |
| P2.2 (S3) | `current_org_id_for` honours member selections + re-checks membership; ending a membership ends live selections | NEW core migration + `sql_templates.py` renderer (parity keeper re-baselined together) | T1∧T2∧T3 | RLS probe: a removed member's selection falls back to home on the next query |
| P2.3 (S4) | accept-invite adds a membership (no 409); remove-member ends it (no profile delete); SSO admits any licensed membership | core `team.py`, `sso.py` | after S2 | invite an existing user into a 2nd org → 200; both orgs listed |
| P2.4 (S5) | picker lists member orgs; required only with >1 choice; AppShell switcher | `seed/lib/frontend/src/org-selection.ts`, `OrgSelectionGate.tsx`, layout | after S2 | a 2-org owner switches between orgs in the shell |
| P2.5 (S6) | pilots: social-wiring, community, igig (already picker-ready) → fan-out | per-product | after S5 | wiring audit per pilot |

**Why not now**: T2/T3 — semantics undecided and a sibling branch owns the same resolver.

## Phase 3 — the brand is the org's (DEFERRED — after Phase 2 pilots)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P3.1 | seed org brand: `public.org_brands` (tokens, logo, palette, type) + `/api/me/brand` + `BrandProvider` organ theming the AppShell | core migration, seed lib/framework | Phase 2 done | switching org re-themes the shell |
| P3.2 | social-wiring `is_primary` marca = projection of the org brand (never authored twice); extra marcas stay for multi-brand companies | social-wiring | P3.1 | the company kit shows as the company org's brand |
| P3.3 | therapy `clinic_branding` onto the org brand (N=2 consumer) | therapy | P3.1 | clinic theme comes from the org brand |

## Phase 4 — absorb the legacy org (DEFERRED — T4; needs S1 on prod)

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

- **Q1** Do regular members need MFA (aal2) to switch orgs, or only staff?
- **Q2** Must a multi-org user choose on every product entry, or only when the last-active org isn't licensed for it?
- **Q3** `noctus_users.org_id`: follows the last selection, or a fixed home?
- **Q4** Should `pessoa_fisica` marcas eventually become personal orgs?
- **Q5** One brand per org, or per-product overrides?
- **Q6** Does joining a second org need approval from the invitee's home org?

## Decision log

- **2026-10-12**: Generalize the platform org picker (architect Phase-0) instead of a new mechanism; S1 expand-only membership table shipped to dev; accept-invite first-time-invitee 404 fixed on dev.
- **2026-10-12**: Mock fidelity — the shared mock's lenient `.single()` hid the 404. `strict_single` opt-in shipped; flipping the default reds 5 more core tests (licenses check-access ×3, products detail ×2, website-settings rollback) — same probable live-404 class. NOC-REMEDIATE destination: slice "mock-fidelity" here (fix those call sites, then default `strict_single=True` fleet-wide).

## Retrospective (filled at first trigger fire)

*To be filled.*

## Composes with

`KB § PATTERNS/backend/tenancy-license-gate.md` (§ Platform org picker) · `KB § PATTERNS/architect/seed-canonical-defaults.md` · `KB § PATTERNS/frontend/product-internal-wiring.md`
