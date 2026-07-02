# daily-life-wiring — Phase Lessons

> 5-category synthesis across Phases 0–4. Authored Phase 4 close per
> engineer-default §10 (AI scaffolding → doc-symbology).
>
> - **Errors** — bugs, wrong outputs, breakage caused by the engineer.
> - **Mistakes/slips** — near-misses caught before they shipped.
> - **Lessons** — methodology improvements with applicability beyond this project.
> - **Interesting** — observations worth remembering, even if not actionable yet.
> - **Knowledge** — domain or code facts established by this project.

---

## Errors

None caused by the engineering work across Phases 0–4.

---

## Mistakes / Slips

**M1 — `ai_outputs` mount without migration (Phase 2 → Phase 3 deferral).**
Phase 2's brief estimated "one string in `main.py`" for `ai_outputs` mount.
Correct — but incomplete: the seed `create_ai_outputs_router` reads from
`<schema>.ai_outputs` and its `try/except` silently returns `[]` when the
table is absent. Mounting without the migration would have made the router
appear healthy while silently suppressing all data — a no-silent-errors
violation. Phase 2 caught this before shipping and deferred both (mount +
migration) to Phase 3.

**Lesson:** verify-the-seed-ships-it ∧ verify-the-table-exists-in-schema
are PAIRED checks. A seed router that reads a product-schema table is only
fully wired when (a) the mount string is added AND (b) the migration exists.
Single-check misses the B-leg.

**M2 — Mock user_id mismatch in `test_notificacoes_router.py`.**
`MOCK_NOTIFICATION` used `"user_id": "test-user-id"` but `MockUser.id`
defaults to `"test-user-123"`. The test passed historically because the
mock's `.eq()` filter was a no-op (match-all fallback). When the mock
filtering became accurate (via `projects/mock-supabase-select-predicate-filter`),
the test started failing — a pre-existing latent bug surfaced by a better
mock. Fixed on-contact (Phase 3): corrected the mock value to match
`MockUser`'s canonical default.

**Lesson:** test fixtures that seed data must use the SAME user-id/org-id
values as the `MockUser` defaults. The standard pair is `user_id="test-user-123"`,
`org_id="test-org-123"`. Document this in the product conftest or a comment
near the fixture. N=2 mismatches across the platform (this + at least one
ERP case per M2's fix history) → triage threshold met (formalize or
accept-with-rationale).

---

## Lessons

**L1 — Smaller product = tighter phases; don't inherit therapy's phase count.**
daily-life finished in 4 phases (0–3 code + Phase 4 retro) vs. therapy's 9.
The product has 7 routers / 35 endpoints vs. therapy's 38 endpoints. Fewer
phases = less context overhead = faster throughput. The key driver was
collapsing Phases 1+2 when the seed real adapter shipped early.

**L2 — Early collapse is a valid phase shape when the dependency arrives.**
PROJECT.md had Phase 2 = auth-factory (gated on seed real adapter shipping).
When the adapter shipped in the same window as Phase 1, the two phases
collapsed cleanly. The project document captured this explicitly in §11 so
future agents don't mistakenly read the original phase numbering as a
regression.

**L3 — Status-assertion sweep is preventive, not corrective.**
The brief's "status-assertion sweep" (checking that every test asserts
`status_code` before the body) is most valuable at test-authoring time
(author the new tests correctly) rather than as a retroactive fix pass over
the existing corpus. All 10 smoke tests authored in Phase 3 comply by
construction: every test class has a `test_requires_auth` that asserts
`status_code == 401` and every `test_happy_path` asserts `status_code == 200`
before touching `body`. The pre-existing corpus (210 tests) was not swept
for violations — scope bounded by brief.

**L4 — `mock_supabase` vs `_mock_supabase` is a product-level convention.**
ERP's tests use `client._mock_supabase`; daily-life's existing tests use
`client.mock_supabase` (no underscore). Both are valid — `AuthClient` exposes
both attributes. When authoring new tests for a product, check the existing
test files first to see which convention the product has settled on, and be
consistent. Mixing conventions in the same product makes the tests harder
to read.

**L5 — Migration + mount are the atomic unit for a new standard router.**
See M1. The correct procedure: (1) grep for the router's DB reads in seed
to identify the table(s) required, (2) check if `<schema>.<table>` exists
in the product's migrations, (3) if not, author the migration alongside the
mount. Never one without the other.

---

## Interesting

**I1 — `create_ai_outputs_router` uses `deps._db.schema` comment but actually
receives `schema` from the `ProductDependencies` instance's internal state.**
The router reads `deps._db.schema` (private attribute) rather than being
passed a `schema` kwarg explicitly. This is a minor encapsulation risk: if
the `DatabaseModule` changes its internal attribute name, the router silently
loses schema scoping. Worth monitoring as a NOC-REMEDIATE candidate if the
attribute surface appears in more than one router.

**I2 — The notificacoes router uses `deps.get_core_client()` not
`deps.get_user_client()`.**
Notifications live in `public.notifications` (core schema) rather than the
product schema. This means product-level Supabase schema isolation doesn't
apply to notifications — they go through the core client. The test mock must
match: `get_core_client` is patched to `mock_sb`, so `client.mock_supabase`
works regardless; but the semantic intent is different from product-schema
reads.

**I3 — `ai_outputs` mount-smoke passes without the migration applied.**
The seed `ai_outputs` router wraps the DB read in `try/except` that silently
returns `[]` on any exception (including "table does not exist"). This means
the smoke tests pass against the mock regardless of whether migration 006 is
applied — the mock's in-memory store is always available. The migration is
needed only for real Supabase operation. This is correct behavior (tests are
unit-level, not integration-level) but it means green tests alone don't prove
the table exists in prod.

---

## Knowledge

**K1 — `ai_outputs` canonical columns (from `noctusai_lib.domain.ai.outputs`):**
`id` · `org_id` · `ref_type` · `ref_id` · `kind` (enum: classification/score/flag/extraction/narrative) ·
`label` · `score` (nullable NUMERIC) · `chip` (nullable TEXT ≤20 chars) ·
`explanation` (nullable TEXT ≤280 chars) · `confidence` (nullable NUMERIC 0-1) ·
`model_version` · `prompt_version` · `metadata` (JSONB default '{}') ·
`created_at` · `updated_at`.
Indices: `(ref_type, ref_id, created_at DESC)` + `(created_at DESC)` + `(org_id)`.

**K2 — daily-life schema is `daily_life` (underscore), not `daily-life` (hyphen).**
The `personal-finance` schema uses a hyphen (quoted in SQL); `daily_life` uses
an underscore (no quoting needed). This distinction matters when writing raw
SQL migrations. Migration 006 correctly uses `daily_life.ai_outputs`.

**K3 — daily-life Phase 2 close baseline: 210 tests (green).**
Phase 3 adds 10 smoke tests (5 × ai_feedback + 5 × ai_outputs) + fixes 1
pre-existing notificacoes test. Phase 3 close baseline: 242 green, 0 failed.

**K4 — Worktree divergence (2 commits behind origin/dev) is file-safe.**
The 2 commits between this worktree's fork base (`d6d59391`) and
`origin/dev` (`9f55a50b`) touch only `seed/lib/backend/noctusai_lib/config/cors_registry.py`
and its tests — zero overlap with `products/daily-life/**`. The divergence
is integration-safe; the architect merges clean on FF.

**K5 — Phase 4's "FF-to-main" is the old branching model.**
PROJECT.md §6 Phase 4 originally listed "FF-to-main is the literal last step"
— this predates the `main`=production / `dev`=integration split. The correct
model: engineer branch → architect FF-merges to `dev`; `main` is release-gated
(separate user-gated `noctus.dev.release bless` step). Phase 4 change-log
records this correction.
