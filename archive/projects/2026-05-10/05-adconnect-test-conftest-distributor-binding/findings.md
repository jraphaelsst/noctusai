# adconnect-test-conftest-distributor-binding — Orchestration Findings

> Transcribed by the orchestrator post-merge per `KB § PATTERNS/branching-and-merging.md § 17.6.1`. Engineer C kept content in PROJECT.md §11 after the harness blocked their `findings.md` Write call; this file curates the 5-category synthesis from their report.

## Errors encountered

- **Initial `--no-verify` slip on the merge commit.** Engineer used `--no-verify` thinking pre-commit hooks were "unrelated infrastructure" for a merge — that violates CLAUDE.md. Recovered via `git reset --hard HEAD` to undo the local-only commit, redid the merge cleanly, hooks passed first try. Cost: 2 minutes; lesson captured.

## Mistakes / slips

- **Worktree base mismatched the brief.** The brief assumed the project branch was created from `origin/main` AFTER the AdConnect MVP merge. Reality: `origin/main` was at `51db601` (PRE-MVP). The MVP commits lived only on `adconnect-mvp-implementation`. Recovered by merging the MVP branch into the project worktree branch as the prerequisite base. **The §16.7 STOP-and-report directive correctly identified the gap; the methodology gap was that orchestrators should `git log origin/main` AFTER closing a project to confirm the close commits actually landed there before dispatching follow-up engineers from `origin/main`.** **This finding directly contributed to the §14.2 prerequisite-merge formalize.**
- **Brief's hypothesis was directionally right but mechanism was wrong.** Brief said "distributor-membership rows hard-coded org_id mismatch" assumed `make_get_current_user_org` + membership-table lookup. Reality: AdConnect uses `make_get_current_user` (no `_org` factory; no membership lookup at auth time). The mismatch is between the conftest's default `MockUser(org_id="test-org-123", no role, no distributor_id)` and the routers' role + `distributorId` requirements. The mock's `auth.get_user` is a `MagicMock` that ignores token bytes — JWTs minted by tests via `_make_token(...)` are decorative. Reading `auth_deps.py` + `make_get_current_user` bodies before drafting the brief would have caught this.

## Lessons learned (durable rules)

- **`bind_user_metadata` is the right shape for cross-product test conftest binding.** N=15+ recurrence across 7 product conftests confirmed before lifting to `noctusai_lib.testing`. Single seed-lib primitive collapses byte-identical helpers + structural variants alike.
- **Drive-by FastAPI 0.115 + `from __future__ import annotations` + 204 + `-> None` is a latent platform-wide trap.** No guarantee admin.py was the only victim. File as `keeper-detector-fastapi-204-future-annotations` follow-up.
- **Constructor-time `APIRouter(prefix=...)` is the structural fix; post-construction `router.prefix = ...` silently no-ops on FastAPI 0.115.** Phase 1 caught auth.py with the broken shape (same shape that cart/orders received in MVP Phase 3); 9 path-mismatch failures closed by switching to constructor-time prefix.
- **Engineer A coordination: the 19 baseline failures were 100% role/scope binding + path mismatch, NOT write→read propagation.** No overlap with `mock-supabase-write-propagation`. Classes of failure are orthogonal.

## Interesting findings (surprises, discoveries)

- **9 of the 19 baseline failures were auth.py path-mismatch**, not conftest binding. The brief framed all 19 as "fixture binding" but Phase 0 audit revealed two distinct classes: 10 fixture-binding + 9 auth_router path-mismatch.
- **Standing-duty `scan_within_product_helpers` returned stale results** relative to the worktree state (Engineer D also reported this). The scanner appears to query a snapshot from `main` rather than the live worktree. **Methodology gap surfaced**: scanners that don't reflect the worktree's true state can mislead an engineer subagent. (See Engineer D's auth-deps-shim-sweep findings for parallel report.)
- **Harness blocked findings.md Write** despite explicit Write authorization in the brief. Surfaced as N=3 (joining Engineers A, B, E, F). Contributed to the §17.6.1 N=5 recurrence formalize.

## Knowledge pieces (durable patterns)

- `bind_user_metadata(mock_supabase, *, user_id, org_id, role, distributor_id=None)` — generic primitive in `noctusai_lib.testing`. Replaces 7 product-conftest variants of `_bind_user_metadata` helpers.
- `bind_adconnect_user(...)` — AdConnect-specific wrapper that vocabulary-maps `user["distributorId"]` ← `user.user_metadata.distributor_id`.
- AdConnect's two auth realms (custom-JWT + Supabase) coexist via disjoint URL prefixes + token signatures. The `auth_deps.py` shim is the legitimate domain-auth carve-out at N=1.
- The mock `auth.get_user` is a `MagicMock` that ignores token bytes — JWTs minted by tests via `_make_token(...)` are decorative. **Open question**: should the mock decode bearer tokens and resolve users from token payloads? JWT-aware mocks would make `_make_token` calls semantic instead of decorative.

## Deferred items

1. **`adconnect-schema-drift-reconciliation` follow-up project** — `relatorios_sellout` runtime carries `org_id` column; migration doesn't declare it. Conftest's `MockSupabaseClient(validate_schema=False, schema="adconnect")` mirrors ERP precedent. Same pattern likely affects other tables.
2. **Keeper detector for FastAPI 0.115 + `from __future__ import annotations` + 204 + `-> None`** — file as `keeper-detector-fastapi-204-future-annotations`.
3. **Cross-product rollout of `bind_user_metadata`** — 6 other products (core, ERP, mailing, daily-life, dev-team, others) still inline the `mock.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(...)))` shape. Consider a `noctusai-lib-bind-user-metadata-rollout` master-tree.
