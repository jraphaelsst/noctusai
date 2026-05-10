# schedule-coro-fire-and-forget — Orchestration Findings

> Transcribed by the orchestrator post-merge per `KB § PATTERNS/branching-and-merging.md § 17.6.1`. Engineer B kept the 5-category content folded into PROJECT.md §11 + the bundled proposal + the SQLite phase-learning DB (entries IDs 32-35) after the harness blocked their `findings.md` Write call; this file curates the synthesis from their report.

## Errors encountered

None.

## Mistakes / slips

- **Brief over-counted callsites by referencing files on a sibling branch.** Brief said N=4 referencing AdConnect's `orders_service.py:96`/`financial_service.py:122`/`cart.py:88` + core `billing.py:199`. Those AdConnect files don't exist on `main` (they live on the AdConnect MVP branch). Re-grep on actual base `51db601` returned **N=3 production callsites**. Recurrence rule still fired (N≥3). **Lesson:** engineer-side recount on actual base SHA before trusting brief-asserted N=X counts. (This is a sibling slip to Engineer C's prerequisite-merge gap — both root-cause to the orchestrator dispatching from a stale main.)
- **Architect-side guess on destination was wrong.** Brief suggested `noctusai_lib.api.tasks` (HTTP-adjacent assumption). Engineer walked the seed-lib decision tree per `KB § PATTERNS/seed-lib-layout.md` and chose `noctusai_lib.primitives.tasks` (pure asyncio shaping; no FastAPI/IO/domain). Engineer's deterministic walk overruled the architect's guess. **Lesson:** when uncertain, defer destination to the engineer's evidence-based walk rather than guessing in the brief.

## Lessons learned (durable rules)

- **`logger.exception(...)` inside `Task.add_done_callback` is a trap** — `sys.exc_info` isn't set inside the callback (the exception was raised on a previously-resolved task). Use `logger.error(..., exc_info=task.exception())` instead. Phase 1 technical learning.
- **Two distinct failure surfaces in fire-and-forget code**: sync arg-resolve vs. async coroutine-raise. Refactor must NOT merge the two outer try/excepts. Phase 2 technical learning.
- **Patch at the consumer-side import binding, never at the producer-side definition** — survives refactors that rename the seed helper. Phase 3 technical learning. **Codified into KB § PATTERNS/testing.md Pattern 2** as a drive-by amendment in this project.
- **Engineer-side recount on actual base before trusting brief-asserted N=X counts.** Phase 0 methodology learning. The brief over-counted because it referenced files on a sibling branch.

## Interesting findings (surprises, discoveries)

- **Pre-existing baseline failures encountered (NOT introduced by this project)**:
  - `products/core/backend/tests/routers/test_test_accounts_router.py::test_create_test_account_as_admin` — `MockSchemaError: public.plans has no column 'is_active'`. The branch's `001_noctusai_core.sql` migration uses `ativo` (Portuguese) not `is_active`; `app/routers/test_accounts.py` queries `is_active`. Unrelated to fire-and-forget refactor; baseline on `seed-hardening-from-youtube-crawler` branch from which this branch derives.
  - Multiple seed-lib tests fail to collect due to `httpx`/`pytest-asyncio` missing in system Python 3.10. Unrelated; collection-only error.
- **Harness blocked findings.md Write despite explicit authorization** — surfaced as part of the §17.6.1 N=5 recurrence formalize.

## Knowledge pieces (durable patterns)

- **`schedule_coro(coro, *, logger=None, name=None) -> asyncio.Task`** — schedules + attaches `add_done_callback` that logs exceptions via `logger.error(..., exc_info=exc)` (full traceback). Cancellations log at `debug`. Returns the Task for callers that track it. Lives at `seed/lib/backend/noctusai_lib/primitives/tasks.py`.
- **`NoRunningLoopError(RuntimeError)`** — typed wrapper for `asyncio.get_running_loop()`'s bare `RuntimeError("no running event loop")`. Same module.
- **Failure-surfaces section in `tasks.py` module docstring** documents the sync-resolve-args vs async-coroutine-raise distinction so future refactors don't merge the two outer try/excepts.
- **Refactored callsites** (3 production):
  - `products/core/backend/app/routers/billing.py:202`
  - `products/erp-imobiliario/backend/app/services/certidoes_service.py:1099`
  - `products/erp-imobiliario/backend/app/services/job_service.py:121`

## Phase learnings logged via `noctus.dev.phase_learning_log`

IDs 32-35 in the local SQLite DB at `mcp/noctusai/data/phase_learnings.db`. Methodology learnings (engineer-side recount) and technical learnings (logger.exception trap, two failure surfaces, consumer-side patching) — both classes captured durably.

## Deferred items (with destinations)

1. **Sweep AdConnect MVP branch for fire-and-forget callsites when it merges to `main`.** Trigger: AdConnect MVP merge (now landed on main via this batch's conftest-driven merge — AdConnect's `_schedule_coro` helpers in orders_service.py:96 + financial_service.py:122 should now be migrated to `schedule_coro` import in a follow-up sweep). **DRIVE-BY OPPORTUNITY for next AdConnect-touch session.**
2. **`noctus.dev.seed_lib_destination` MCP tool** that walks the 6-question seed-lib decision tree. Future project-shaped work; MCP-first opportunity.
