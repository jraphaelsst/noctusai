# Phase 6 follow-up — Seed `team` standard router /accept handler is broken

**Status**: deferred-with-destination (PF Phase 6.b engineer cannot touch seed in standalone-mode dispatch).
**Severity**: high (runtime-broken on every product mounting `team` standard router; symptom = HTTP 500 on POST /api/team/accept).
**Effort estimate**: medium (seed router fix + domain helper extension + integration test + adopters re-validate).
**Affected products**: PF (N=1 today), ERP / therapy / daily-life / mailing (N=4+ at scale — every product in `standard_routers=["team", ...]` inherits the broken path; seed/framework/backend tests exercise build-time, not request-time).
**Surfaced by**: PF wiring Phase 6 engineer (worktree-agent-a0ae8b7bce8e0cd0f, 2026-05-11).

---

## 1. Evidence

`seed/framework/backend/noctusai_seed/routers.py:153-175` — the seed `_create_team_router` factory mounts two endpoints that invoke the domain helpers with the wrong signature:

```python
@router.get("/accept/validate")
async def validate_invite(token: str = Query(...)):
    admin = deps.get_admin_client()
    result = validate_invitation(db=admin, schema=deps._db.schema, token=token)
    ...

@router.post("/accept")
async def accept_invite(body: dict):
    admin = deps.get_admin_client()
    result = accept_invitation(
        db=admin,
        schema=deps._db.schema,
        token=body["token"],
        user_id=body.get("user_id"),
        email=body["email"],
        password=body.get("password"),
        name=body.get("name"),
    )
    ...
```

`seed/lib/backend/noctusai_lib/domain/invitations.py:116,168` — actual signatures:

```python
def validate_invitation(db, table: str, token: str) -> dict: ...
def accept_invitation(db, table: str, invitation_id: str) -> None: ...
```

Drift surface:
- Router passes `schema=`, function takes `table:` → TypeError on first call.
- Router passes 7 kwargs to `accept_invitation`, function takes 3 positional → TypeError on first call.
- Function only flips `status` to `"accepted"` — no auth user creation, no profile linking. The router's call shape implies a richer flow (email/password/name → create supabase auth user) that **does not exist in the domain layer.**

`AcceptInvitePage` (seed frontend, `seed/lib/frontend/src/design-system/components/AcceptInvitePage.tsx:81-83,136-140`) calls:
- GET `${apiBaseUrl}${acceptEndpoint}/validate?token=...` → hits the broken `validate_invitation` call.
- POST `${apiBaseUrl}${acceptEndpoint}` with `{token, nome, password}` → hits the broken `accept_invitation` call.

Migration `005_invitations.sql` (PF copy, also therapy/mailing/etc.) only has columns `id, org_id, email, role, invited_by, token, status, expires_at, created_at` — **no `accepted_at`, no `accepted_by`** — so even if the domain helper is fixed, the schema doesn't store who accepted when.

## 2. Why this didn't surface in PF tests

PF Phase 0 test inventory recorded `test_team_router.py` exists for PF. The team router tests likely cover the GET `/team` list-members happy path + the `/invite` POST + role gating, but **do not exercise the validate/accept POST round-trip** (which would fail at function-call time). Seed-framework tests at `seed/framework/backend/tests/test_build_standard_routers.py` cover `build_standard_routers(...)` returns a valid `APIRouter` — they do NOT make HTTP calls.

The integration gap is structural: seed tests are build-time, product tests are router-mock-time. The drift between router-handler and domain-helper signatures is a request-time runtime gap. **Recommend the formalize fix include a seed-framework integration test that does `client.post("/api/team/accept", json={...})` against a real `_create_team_router(...)` with `MockSupabaseClient` deps.**

## 3. Proposed fix (formalize at seed level)

Three sub-deliverables, ordered:

### 3.1 Fix the signature drift (minimum bar)

- Update `validate_invitation` callsite to `validate_invitation(db=admin, table="invitations", token=token)`.
- Update `accept_invitation` callsite to match the actual `(db, table, invitation_id)` signature — but this requires re-resolving the token to an invitation_id first, OR extending the domain helper.

### 3.2 Extend the domain helper to cover the implied flow (the real fix)

The router's 7-kwarg shape (token, user_id, email, password, name) implies a flow:
1. Validate the token (re-uses `validate_invitation` → returns invitation row).
2. Create or link a Supabase auth user (`db.auth.admin.create_user(...)` with the email + password).
3. Insert a `noctus_users` row linking the auth user to the org_id from the invitation.
4. Mark the invitation as `accepted` (the current `accept_invitation` shape).

Extend `noctusai_lib.domain.invitations` with a single `complete_invitation(db, admin_auth, table, token, email, password, name)` that orchestrates 1-4 atomically. Update the router to call the new helper.

### 3.3 Migration `005_invitations.sql` adopters add `accepted_at, accepted_by` columns

For audit-trail completeness. New migration `005b_invitations_accepted_at.sql` per affected product (or a one-shot seed migration applied via Supabase MCP). Optional but recommended.

### 3.4 Integration test

Add `seed/framework/backend/tests/test_team_router_accept_flow.py` exercising:
- POST /accept with bad token → 400.
- POST /accept with expired token → 400.
- POST /accept with good token + valid signup → 200 + `noctus_users` row inserted + invitation `status="accepted"`.
- GET /accept/validate?token=... → 200 with email/role/org_name in response.

This is the test that would have caught the drift on day one.

## 4. Adopter list (recompute when filing the seed project)

Every product whose `main.py` has `standard_routers=[..., "team", ...]`:

```bash
grep -rn 'standard_routers=' products/*/backend/app/main.py | grep '"team"'
```

Expected: personal-finance, erp-imobiliario, therapy-platform, mailing, daily-life, dev-team, adconnect, possibly others. All currently broken on /accept runtime path.

## 5. Recommended project framing

Slug: `seed-team-router-accept-real-adapter`.
Parent: none (cross-cutting seed project; not under any single product).
Filed-under: `projects/seed-team-router-accept-real-adapter/PROJECT.md`.
First sub-task: re-run grep to confirm adopter count → if N≥2 (likely all 6+), this is N=6+ "verify-the-seed-ships-it" rule firing — MUST formalize.

## 6. Interim posture for PF

- PF Phase 6 ticks all sub-tasks (per "verify the wiring on the consumer side"); the broken runtime path is a seed bug, not a PF bug.
- Manual browser QA at Phase 7 will surface the runtime symptom (HTTP 500 on Accept Invite click) — record there as "blocked on `seed-team-router-accept-real-adapter`".
- No PF code change recommended in advance of the seed fix; if PF needs a working invite flow before the seed fix lands, options are: (a) write a PF-local `/accept` override that does the right thing (rejected — violates seed-first), (b) accept-with-rationale a `_create_team_router` fork in PF (rejected — same), (c) prioritize the seed project. **Option (c) is the only acceptable path.**
