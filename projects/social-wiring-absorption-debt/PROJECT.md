# social-wiring-absorption-debt

> **Filed 2026-05-17** as the `fix-on-contact` balloon-to-project destination
> for social-wiring's absorbed-from-earlier-epoch debt surfaced during the
> consolidation pass (commit `ef35a62`). NOT surface-only — this is the
> concrete, scoped fix-in-motion. Self-contained (durable-docs rule): all
> substance inline, no archive/conversation anchors.

## 1. Context & Purpose

`social-wiring` was developed externally and absorbed (branch
`feat/social-wiring-absorption`, Wave-1..4). It grew under an earlier
methodology epoch, so it carries pre-existing debt the current keeper set now
flags. `check_all_products()` attributes **174 issues** to social-wiring (the
single largest product contributor; baseline-verified pre-existing at branch
HEAD `7137af0`, NOT regressions from the consolidation). This project clears
that 174 to bring the absorbed product onto the current contract.

## 3a. Seed-first analysis

Every fix MUST go through a seed seam, not a product-local patch:
- **RLS `service_role_bypass`** is a fleet contract (keeper
  `check_*service_role_bypass`; erp migration `029_service_role_bypass_backfill.sql`
  is the reference shape). social-wiring's single `001_social-wiring.sql` ships
  **zero** such policies → admin-client writes silently fail under RLS. Fix =
  add the policy per flagged table, mirroring erp's backfill migration shape +
  Supabase-MCP mirror (`feedback_mcp_migrations_mirror_file`,
  `feedback_single_001_migration` — edit 001 in place OR additive `002_*`).
- **`standard_routers` auditability** — `app/main.py` passes `_standard` (a
  registry-derived variable), keeper "cannot audit; review manually." Triage:
  inline the resolved list literal at the `create_product_app(...)` call site
  (auditable) OR accept-with-rationale if the registry indirection is a
  deliberate seam (decide at execution, record the triage).
- e2e fixture drift is product-local test debt (no seed seam) — fix in the
  product test.

## 4. Scope

**In:** the 174 social-wiring `check_all_products()` issues —
- **RLS `service_role_bypass` (19+)** for tables: `campaigns`,
  `automation_enrollments`, `contacts`, `notifications`, `send_logs`,
  `sender_domains`, `unsubscribes` (+ any others the full list enumerates;
  re-run `check_all_products()` filtered to social-wiring for the live set).
  Files calling admin `.table()`:
  `backend/app/modules/email_marketing/{scheduler.py,routers/{unsubscribe,settings,analytics,webhooks}.py}`,
  `backend/app/services/ai_pipeline.py`.
- **`standard_routers` literal** — `backend/app/main.py`.
- **e2e fixture** — `tests/integration/test_e2e_flows.py::TestTeamFlow::test_list_members_returns_data`
  seeds `noctus_users` but the seed `team` standard-router queries with an
  org filter the seeded rows don't satisfy → `/api/team` returns `[]`. Align
  the fixture to the seed `team` router's actual data contract (read the seed
  router first — `seed/framework/.../routers/` or `noctusai_lib`).
- **`tests/services` pytest-timeout hang** — the social-wiring `tests/services`
  dir hangs the suite indefinitely (network-touching tests, no `pytest-timeout`).
  This is the live instance of the E4-AUDIT pytest-timeout CI-hazard. Add
  `pytest-timeout` + a per-test timeout (or mark+skip the network tests).

**Out:** the platform-wide debt (→ `platform-compliance-baseline`); the
`score==100` gate contract (→ user decision, see that project §7).

## 6. Implementation phases

- **P0 — audit.** Re-run `check_all_products()`; emit the exact social-wiring
  174 list grouped by detector. Confirm RLS table set. Read the seed `team`
  router data contract + erp `029_*` RLS shape.
- **P1 — RLS backfill.** Additive migration (`002_service_role_bypass.sql` or
  001-in-place per single-001 rule) + Supabase-MCP mirror. One policy/table.
  Pilot-verify: admin writes succeed under RLS.
- **P2 — standard_routers triage** (inline literal OR accept-with-rationale).
- **P3 — e2e fixture + pytest-timeout.** Fix the TeamFlow fixture; add
  `pytest-timeout`; un-hang `tests/services`.
- **P4 — verify.** social-wiring backend suite fully green (incl.
  `tests/services`); `check_all_products()` social-wiring contribution → 0.

## 9. Success criteria

- social-wiring `check_all_products()` issue count: 174 → 0.
- `cd products/social-wiring/backend && pytest` fully green (no hang, no skip-as-hide).
- RLS policies present in migration AND mirrored to the live DB.
- No new frozen literals (registry-derive); triage decisions recorded.

## 10. How to use this plan

`cd` to a fresh worktree off `feat/social-wiring-absorption` (the branch that
owns social-wiring; NOT main). Start P0: `python -c "from
mcp.noctusai...compliance import check_all_products"` filtered to
social-wiring. Read seed `team` router + erp `029_*` BEFORE editing. Engineers
obey `.claude/agents/engineer-default.md`.
