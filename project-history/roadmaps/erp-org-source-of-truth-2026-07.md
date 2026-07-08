# Roadmap — ERP org source-of-truth hardening + platform super-admin

**Slug:** `erp-org-source-of-truth` · **Opened:** 2026-07-07 · **Owner:** tech-lead (Raphael)

## Goal

Collapse the org/identity "single source of truth" onto `public.noctus_users` (DB,
server-side) so the app's notion of a caller's org can never drift from what RLS
enforces via `current_org_id()`. Introduce a clean **platform super-admin** primitive
(`is_platform_admin()`, keyed on `noctus_users.role='admin'`) that gives the operator
cross-org visibility, replacing the inconsistent `erp.user_roles` global bypass.

## Why (incident that opened this)

`api/matriculas/extrair` 500'd on upload for `marina@one.com.br`, a freshly-provisioned
user. Root cause: the endpoint sourced `org_id` for the INSERT from the **JWT**
(`user_metadata.org_id`), which was null/stale, while RLS derives org from the **DB**
(`noctus_users`). Two sources of truth → drift → NOT NULL / RLS reject → 500. Recon found
identity smeared across **5 places** (JWT metadata, `noctus_users.org_id`, `noctus_users.role`,
`noctus_users.org_role`, `erp.profiles.org_id`) and **3 role notions** (`noctus_users.role`,
`org_role`, `erp.user_roles.role`).

## Scope (measured against live schema 2026-07-07)

- **131** org-scoped RLS policies across **74** tables in the `erp` schema (candidates for the admin bypass).
- **21** ERP routers feed `org_id` from the JWT into DB writes.
- The `current_org_id()` RLS pattern is **seed-rooted** (`products/seed/backend/migrations/004_rls_current_org_id.sql`); the JWT-as-org-source is likewise seed-rooted (`make_get_current_user_org` resolves `raw_org` from `user_metadata`). ⇒ true fix is seed-first, fans to the whole fleet.

## Slices

| # | Slice | Status | Notes |
|---|---|---|---|
| 1a | Pilot: `matricula_extracoes.org_id DEFAULT current_org_id()` + router reads org from DB (`resolve_org_id_db`) + clean 400 for unprovisioned users | ✅ built, tested (2083 pass) on `feat/erp-org-source-of-truth-hardening` | migration `038`; **not yet deployed** — awaits ship gate |
| 1b | `public.is_platform_admin()` + cross-org bypass on the pilot table's policy | ✅ built (migration `038`) | Raphael already `noctus_users.role='admin'` ⇒ becomes platform super-admin on deploy |
| 2 | Fan out org-from-DB + admin bypass to the other 73 tables / 21 routers **via the seed** (harden `make_get_current_user_org`/`get_current_user_org` to resolve org from noctus_users) | ⏳ todo | parallelizable / wave-dispatch; pilot-first cadence — prove 1a on 3 pilots before full fan-out |
| 3 | Collapse the 3 role systems (`erp.user_roles` vs `noctus_users.role` vs `org_role`) onto the one source; retire the global `has_role` bypass in favour of `is_platform_admin()` + org-scoped roles | ⏳ todo | enables the requested per-team RLS (marketing can't see documents/contracts) |

## Decision log

- **2026-07-07** — Model chosen: **platform super-admin**, `noctus_users` as the single source of truth (vs. own-each-org / multi-org membership). Operator = `noctus_users.role='admin'`.
- **2026-07-07** — Prod RLS ships as migrations through dev-validate → prod-promote; **never hand-applied** to the live fleet DB. Marina's row-level provisioning (data, not schema) was applied directly and is fine.
- **2026-07-07** — Marina corrected to plain **member** of **One Consultoria** (Raphael's real-estate agency); she is the in-house lawyer, not a broker — `erp.user_roles.role='corretor'` for her is stale and should be revisited under Slice 3.

## Retrospective (fill on close)

- _pending_
