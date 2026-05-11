# seed-team-router-accept-real-adapter — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ⏳ **EXECUTING — Phase 1 ✅ 2026-05-11 (commit `06b5eeb`).** Engineer QQ shipped seed-side router fix (5 broken call sites — wider than spec) + 7 integration tests at `seed/framework/backend/tests/routers/test_team_router_accept.py`; 55/55 seed/framework tests green. **Phase 2 (per-product migrations + accept_invitation domain helper update) PENDING** — orchestrator dispatches after Wave 13 settles to avoid file-overlap with parallel therapy/PF/imobi engineers.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `seed-team-router-accept-real-adapter`
- **Related docs:**
  - Engineer JJ's detailed proposal: `archive/projects/.../personal-finance-wiring/proposals/phase-6-seed-team-router-accept-drift.md` (after PF archive)
  - `seed/framework/backend/noctusai_seed/routers.py:153-175` — router site
  - `seed/lib/backend/noctusai_lib/domain/invitations.py:116,168` — domain helpers
  - `products/seed/backend/migrations/005_invitations.sql` (or equivalent) — schema gap

---

## 1. Context & Purpose

Engineer JJ discovered during PF P6 audit:

```python
# seed/framework/backend/noctusai_seed/routers.py:153-175
# Router invokes (kwargs):
validate_invitation(db=db, schema=schema, token=token)
accept_invitation(db=db, schema=schema, token=token, user_id=..., email=..., password=..., name=...)
```

But the actual domain helpers:

```python
# seed/lib/backend/noctusai_lib/domain/invitations.py:116
def validate_invitation(db, table: str, token):  # 3 positional!
# :168
def accept_invitation(db, table: str, invitation_id):  # 3 positional!
```

**Result**: TypeError on first call. Every adopting product (PF, ERP, therapy, etc.) is broken at `/api/team/accept` runtime.

Plus migration `005_invitations.sql` lacks `accepted_at` + `accepted_by` columns that the domain code references.

**Why this survived**: no seed integration test calls `client.post("/api/team/accept", ...)` against `_create_team_router(...)`. Build-time tests pass (signatures parse); request-time tests don't exist.

## 2. Confirmed constraints

- **Runtime-broken in production** — every product mounting standard `team` router has this bug.
- **JJ's proposal includes the fix** — align router caller-side to match domain signatures + add missing migration columns + add integration test.
- **Caller-side fix preferred over domain-side** — domain signatures are simple `(db, table, token)`; router's `schema=` keyword is the divergence; fix router to compute `table = f"{schema}.invitations"` and pass positionally.
- **Migration mirror rule applies** — schema fix lands as a new migration in `products/<each-adopter>/backend/migrations/`.

## 3. Design principles

1. **Fix at the seed**, NOT at each consumer. The router is the canonical surface.
2. **Add integration test** that calls `/api/team/accept` against `_create_team_router(...)` so future drift surfaces immediately.
3. **Migration column additions are per-product** — each adopter ships its own `00N_invitations_accepted_columns.sql`. Or, if scaffold ships canonical 005, fix at scaffold + backfill recipe for existing products.

## 3a. Seed-first analysis

- **Cross-product?** YES — every product mounting `team` router is broken.
- **Seed home?** `seed/framework/backend/noctusai_seed/routers.py` (caller fix) + `seed/lib/backend/noctusai_lib/domain/invitations.py` (no change unless signature should accept schema=).
- **Per-product code count for cross-cutting fix?** 0 at the router; per-product migration to add columns IF needed.

## 4. Scope

- **In scope:**
  - Fix router caller-side at `seed/framework/backend/noctusai_seed/routers.py:153-175`.
  - Add integration test exercising `/api/team/accept` end-to-end against `_create_team_router(...)`.
  - Verify migrations have `accepted_at` + `accepted_by` columns; add via per-product migration if missing.
  - Smoke-test against PF (the only product Engineer JJ tested wires AcceptInvite).
- **Out of scope:**
  - Domain signature redesign (keep `(db, table, token)`; router adapts).
  - Frontend changes.

## 5. Architecture / Data Model

Fix shape per JJ's proposal:

```python
# seed/framework/backend/noctusai_seed/routers.py
async def accept_handler(payload: AcceptInvitePayload):
    table = f"{schema}.invitations"
    # validate_invitation(db, table: str, token)
    inv = validate_invitation(db, table, payload.token)
    # accept_invitation(db, table: str, invitation_id)
    return accept_invitation(db, table, inv.id)
```

Plus migration:

```sql
ALTER TABLE invitations
  ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS accepted_by UUID REFERENCES auth.users(id);
```

## 6. Implementation phases

### Phase 0 — Confirm scope + read proposal ✅ *(2026-05-11)*

- [x] Read JJ's proposal (after PF P6 archive) for the exact fix shape.
- [x] Confirm domain function signatures via direct read of `invitations.py:116,168`. **Confirmed positional `(db, table, token|id)`**; also verified 3 sibling helpers (`create_invitation`, `cancel_invitation`, `list_pending_invitations`) use the same `(db, table, ...)` shape — drift was wider than spec.
- [x] Check each product's `005_invitations.sql` for `accepted_at`/`accepted_by` — list which need migrations. **Deferred to Phase 2 dispatch** (per-product scan + migration writes are Phase 2 work).

**Improvements (Phase 0):** none identified — scope-confirmation phase only; the wider-than-spec finding (5 call sites broken, not just /accept) was surfaced by QQ in Phase 1, not at Phase 0 read time.

### Phase 1 — Fix router + add integration test ✅ *(2026-05-11)*

- [x] Edit `seed/framework/backend/noctusai_seed/routers.py` per the architecture shape. **Wider than spec — 5 call sites broken** (lines 130 invite-create, 156 accept-validate, 164 accept-post, 185 invitations-list, 195 invitation-delete), all using `db=admin, schema=deps._db.schema, X=Y` kwargs. Fixed all 5 in one pass via libcst per `feedback_no_quick_fixes`.
- [x] Add integration test at `seed/framework/backend/tests/routers/test_team_router_accept.py` — 7 test cases against `_create_team_router(...)`. Status-code-assertion-rule honored on every assertion.
- [x] Verify test FAILS before the router fix + PASSES after — confirmed via Engineer QQ's pre-fix run (6/7 with literal `TypeError: validate_invitation() got an unexpected keyword argument 'schema'`) + post-fix run (7/7).

**Improvements (Phase 1):**
- **Wider-than-spec fix**: Phase 1 closed 5 broken call sites, not just `/accept`. No-quick-fixes rule fired — applying the literal `/accept` scope would have left 4 TypeError landmines.
- **User-creation seam gap surfaced**: pre-fix `/accept` body was `{token, user_id, email, password, name}` — implying user creation. The domain layer has no such surface; those kwargs were dead before TypeError. If frontend (PF AcceptInvite) expected user creation, the seed needs a `user_creator: Callable` injection seam. Filed as follow-up candidate `seed-team-router-user-creation-seam`.
- **`accept_invitation` domain helper does NOT write `accepted_at` + `accepted_by`** — only sets `status="accepted"`. Phase 2 must update both the domain helper AND each product's migration in lockstep.
- **`deps._db.schema` is a public accessor with a leading underscore** — cosmetic rename deferred (catalog candidate).
- **`seed/framework/backend` lacks `.venv` hydration** in `scripts/bootstrap-worktree.sh` — engineer fell back to `mcp/noctusai/.venv/bin/python` + manual `pip install apscheduler`. Follow-up candidate.
- **libcst `cst.Comma()` defaults collapse to `f(a,b,c)`** — use `cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))` for PEP-8. Candidate addition to `KB § PATTERNS/ast.md`.

### Phase 2 — Per-product migrations + smoke

- [ ] For each product missing `accepted_at`/`accepted_by`: add migration `00N_invitations_accepted_columns.sql`.
- [ ] Apply via Supabase MCP (pass `worktree_path=`).
- [ ] Smoke against PF AcceptInvite happy path.

### Phase 3 — Close

- [ ] All adopters' pytest + integration test green.
- [ ] Improvements + §11 + archive.

## 7. Open questions

- Q1: Should the domain signature change to accept `schema=` kwarg? **Default rec: NO** — keep simple positional shape; fix at router. Domain functions become testable in isolation.

## 8. Dependencies & blockers

- None blocking — fix is well-scoped.

## 9. Success criteria

- [ ] Integration test calls `/api/team/accept` against seed router; green.
- [ ] All adopter products have `accepted_at` + `accepted_by` columns.
- [ ] PF AcceptInvite happy path works end-to-end (smoke).

## 10. How to use this plan

Single-engineer dispatch via worktree. Pattern locked by JJ's proposal — pure mechanical fix.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer JJ's PF P6 (commit `0c45079`) surfaced runtime-broken seed team /accept handler across all adopters. TypeError on first call. Drift survived because no seed integration test exercises the endpoint. Mechanical fix at router caller-side + integration test + per-product migration columns. | claude-opus-4-7 |
| 2026-05-11 | **Phase 1 closed by Engineer QQ** (commit `a51c29c` → cherry-picked to main as `06b5eeb`). Caller-side fix at `seed/framework/backend/noctusai_seed/routers.py` — **5 broken call sites** (not just `/accept` as spec'd): lines 130, 156, 164, 185, 195. All converted from `db=admin, schema=deps._db.schema, X=Y` kwargs to positional `(admin, f"{schema}.invitations", ...)`. `/accept` body simplified from `{token, user_id, email, password, name}` (5 fields, 4 dead) to `{token: str}`. New integration test `tests/routers/test_team_router_accept.py` with 7 cases; status-code-assertion-rule honored throughout. Pre-fix run: 6/7 FAILED with literal `TypeError: validate_invitation() got an unexpected keyword argument 'schema'`. Post-fix run: 7/7 PASSED. Seed/framework suite: 55/55 green (was 48). Keeper `--review --product seed` → 0 issues. **Phase 2 dependencies surfaced**: (1) `accept_invitation` domain helper does NOT write `accepted_at`/`accepted_by` — needs lockstep update with per-product migrations; (2) user-creation seam may be needed if frontend expected user creation in old `/accept` — filed as follow-up candidate `seed-team-router-user-creation-seam`. | engineer-subagent QQ |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
