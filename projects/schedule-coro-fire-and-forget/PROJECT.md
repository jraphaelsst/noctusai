# schedule-coro-fire-and-forget — Project Document

> **Living document.** Revise phases as we learn.

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** Phase 0 ✅ + Phase 1 ✅ → Phase 2 ready
- **Owner / stakeholders:** USER (joaoraphaelsst@gmail.com) · architect · engineer
- **Related docs:** `KB § PATTERNS/seed-lib-layout.md`, `KB § PATTERNS/logging.md`, memory `feedback_recurrence_rule.md`, memory `feedback_no_silent_errors.md`
- **Project slug:** `schedule-coro-fire-and-forget` — at `projects/schedule-coro-fire-and-forget/` (cross-cutting; touches seed-lib + 3 products' backends).

---

## 1. Context & Purpose

Three product backends manually create event-loop tasks for fire-and-forget side-effects (webhook dispatch, queued Job execution, deferred TJSP processing). Each one expresses the same idea — *"run this coroutine on the running loop, don't await it, don't crash on exception"* — with subtly different hand-rolled scaffolding (try/except for `RuntimeError`, scattered `logger.warning` on exception, no `add_done_callback` in any of them so loop-level `Task exception was never retrieved` errors are the only surfacing path for swallowed exceptions).

The recurrence rule (`KB § PATTERNS/project-execution.md § 2.7`) fires at N=3 → MUST formalize. The right home is `noctusai_lib.primitives.tasks` (per `seed-lib-layout.md` decision tree: pure stdlib asyncio shaping, no FastAPI, no IO, no domain, no config, no testing infra → primitives layer).

**Win:** one canonical helper (`schedule_coro`) that:
- Schedules a coroutine on the running loop.
- Logs every exception via `logger.exception(...)` (not `warning`, not silent) — `# silent-ok` is forbidden platform-wide.
- Surfaces a clear error in non-async contexts (no running loop) instead of a bare `RuntimeError` from `asyncio.get_running_loop()`.
- Returns the `Task` so callers that want to track it (e.g. the certidoes per-org idempotency dict) can.

After absorbing, all three callsites import the helper.

---

## 2. Confirmed constraints

- **Brief said N=4 across AdConnect (`orders_service.py:96`, `financial_service.py:122`) + core (`billing.py:199`) + adconnect cart (`cart.py:88`). Engineer-side recount on the actual `schedule-coro-fire-and-forget` branch (rebased from origin/main @ `51db601`) shows N=3 in production code:**
  - `products/erp-imobiliario/backend/app/services/certidoes_service.py:1099` — `task = asyncio.create_task(_delayed_tjsp_process(...))` with explicit task tracking via `_tjsp_scheduled_tasks[org_id] = task`.
  - `products/erp-imobiliario/backend/app/services/job_service.py:121` — `asyncio.ensure_future(_run_job(job))` with no task tracking.
  - `products/core/backend/app/routers/billing.py:202` — `loop.create_task(webhook_delivery.dispatch(...))` inside a try/except `RuntimeError`.
  - The seed `domain/jobs/worker.py:21` is a **docstring example**, not actual code — does not count.
  - `products/adconnect/` does NOT contain `orders_service.py` / `financial_service.py` / `cart.py:88 fire-and-forget` on this branch — those files live on a different branch (the AdConnect MVP branch the brief was authored against). They will be retroactively swept by the same canonical helper if/when they merge to main.
  - **Conclusion:** N=3 in main-branch production → MUST formalize per recurrence rule. Brief's count was based on a sibling branch's tip; project still warranted.

- **Destination per `KB § PATTERNS/seed-lib-layout.md` decision tree**:
  - Q1 (network/DB/SDK)? NO.
  - Q2 (FastAPI request shape / middleware)? NO — `schedule_coro` works equally inside a sync FastAPI handler, an APScheduler job, a CLI, or a plain script.
  - Q3 (platform-wide business rule)? NO — pure asyncio shaping.
  - Q4 (test infra)? NO.
  - Q5 (config/secrets)? NO.
  - Q6 (stateless pure helper)? YES → `primitives/tasks.py`.

- **No silent-ok.** The platform-wide `# silent-ok` retirement (memory `feedback_silent_ok_is_not_a_substitute_for_logging`) means the done-callback MUST log via `logger.exception(...)` — never `pass`, never `warning` (warning loses the traceback), never silent.

- **No monkey-patching of our own code in tests.** The existing `test_certidoes_service.py` patches `app.services.certidoes_service.asyncio.create_task` — that's a borderline case (patching the stdlib re-export, not our own function). Acceptable per the existing rule: external API. In the new tests for `schedule_coro` itself we use real coroutines + a `caplog` fixture for log assertions.

- **Existing baselines.** `products/adconnect/backend/pytest` baseline noted in brief is 19 failures; `erp-imobiliario` and `core` have their own baselines. Our refactors must not introduce NEW failures.

---

## 3. Design principles

1. **One canonical helper, three named call shapes.** `schedule_coro(coro, *, logger=None, name=None)` covers every adopter; if a caller wants the Task back (certidoes idempotency dict), the function returns it.
2. **Exceptions surface — never swallow.** `add_done_callback` ALWAYS attaches a callback that calls `logger.exception(...)` if the task raised. Even when callers don't pass a logger, the module-level `noctusai_lib.primitives.tasks` logger handles it.
3. **Sync-context error is explicit and typed.** Calling `schedule_coro` from a context with no running loop raises `NoRunningLoopError` (a clear seed-lib exception subclassing `RuntimeError`) — not a bare stdlib `RuntimeError` whose message reads "no running event loop".
4. **No magical sync fallback.** We do NOT silently spin up a temporary loop. Fire-and-forget without a running loop is almost always a bug; surface it.
5. **Cancellation is not an error.** A `CancelledError` from the wrapped coroutine is logged at `debug` level, not `exception`, so shutdown-time cancels don't pollute prod logs with stack traces.

---

## 3a. Seed-first analysis (REQUIRED)

Run the six-question checklist (`KB § GUIDES/seed-first-design.md § The seed-first checklist`):

1. **Is the contract identical for every product?** YES — every adopter wants "schedule this coroutine, log if it fails, return the task if I care".
2. **Is the data source product-specific?** NO — there is no data source; pure asyncio shaping.
3. **Is the placement product-specific?** NO — destination is `noctusai_lib.primitives.tasks`.
4. **Is the visibility / permission rule the same?** NO permission concern — module-level helper, no auth/RLS surface.
5. **Does the seam already exist in seed?** NO — `noctusai_lib/primitives/` exists but no `tasks.py` module yet.
6. **Default-on or opt-in?** OPT-IN — adopters import the helper. No automatic insertion at the framework level.

**Litmus — per-product code count this design requires:**
- [x] **0 lines** — pure cross-product concern; lives entirely in seed. Products inherit by importing the helper. *Each adopter REPLACES its existing fire-and-forget call with a single import + call. Net product code count drops by N lines.*

**Phase plan implications:** §6 below builds the helper at the seed in Phase 1, then refactors three products in Phase 2-3. No replication framing; the helper is authored ONCE and consumed three times.

---

## 4. Scope

**In scope:**
- New seed-lib module: `seed/lib/backend/noctusai_lib/primitives/tasks.py` exposing `schedule_coro` + `NoRunningLoopError`.
- New tests: `seed/lib/backend/tests/test_tasks.py` covering schedule-and-await, exception logging, sync-context error, cancellation behavior, optional-logger path, and the returned-Task contract.
- Refactor `products/core/backend/app/routers/billing.py:202` to use the helper.
- Refactor `products/erp-imobiliario/backend/app/services/certidoes_service.py:1099` to use the helper.
- Refactor `products/erp-imobiliario/backend/app/services/job_service.py:121` to use the helper.
- Update `noctusai_lib.primitives.__init__` exports.

**Out of scope (for now — with reason):**
- AdConnect `orders_service.py:96` / `financial_service.py:122` / `cart.py:88` refactors — those files don't exist on `main` yet (they live on the AdConnect MVP branch). Their fix lands when that branch merges; the canonical helper will already be in place.
- Replacing the seed `domain/jobs/worker.py:21` docstring example with a `schedule_coro` example — drive-by polish; will fold in if cheap.
- A general task-tracking registry (named-task lookup, per-org dedupe). That's a feature on top of the primitive, not the primitive itself; out of scope for N=3 absorption.

---

## 5. Architecture / Data Model

```
seed/lib/backend/noctusai_lib/primitives/tasks.py
    NoRunningLoopError(RuntimeError)
    schedule_coro(
        coro: Coroutine[Any, Any, Any],
        *,
        logger: logging.Logger | None = None,
        name: str | None = None,
    ) -> asyncio.Task[Any]

seed/lib/backend/tests/test_tasks.py
    TestScheduleCoro:
        test_schedules_and_runs_to_completion
        test_returns_task_for_caller_tracking
        test_logs_exception_via_supplied_logger
        test_logs_exception_via_module_logger_when_none_supplied
        test_cancelled_error_logged_at_debug_not_exception
        test_no_running_loop_raises_NoRunningLoopError
        test_optional_name_propagates_to_task
```

**Refactor pattern (each adopter):**
```python
# Before
import asyncio
loop = asyncio.get_running_loop()
loop.create_task(some_coro(...))

# After
from noctusai_lib.primitives.tasks import schedule_coro
schedule_coro(some_coro(...), logger=logger, name="webhook_dispatch")
```

For certidoes (which keeps the Task in a dict for idempotency):
```python
# Before
task = asyncio.create_task(_delayed_tjsp_process(...))
_tjsp_scheduled_tasks[org_id] = task

# After
task = schedule_coro(_delayed_tjsp_process(...), logger=logger, name=f"tjsp_{org_id}")
_tjsp_scheduled_tasks[org_id] = task
```

---

## 6. Implementation phases

### Phase 0 — Audit + decision lock ✅

- [x] Re-grep N across actual branch tip; find N=3 in production code.
- [x] Read each callsite to confirm shape parity.
- [x] Run seed-lib-layout decision tree → `primitives/tasks.py`.
- [x] Confirm no existing `tasks` module in seed.
- [x] Run absorption-search MCP scans (cross-product, within-product, service-line) for adjacent recurrences.
- [x] Document findings + decision in this PROJECT.md.

**Improvements:**
- Brief over-counted N at N=4 by referencing files on a sibling AdConnect MVP branch. Recount on actual base SHA `51db601` shows N=3 production callsites. Recurrence rule still fires; project warranted. Lesson logged in §11.
- Cross-product helper scan + service-line scan flagged ZERO additional fire-and-forget recurrences — the helper-name scan threshold is N≥2 distinct products and our pattern is buried inside hand-rolled blocks (no helper name to match), the line-recurrence scan filter is ≥60 chars and our patterns are shorter. Both miss the absorption shape. Generalizable: short-line / hand-rolled patterns evade automated scans; the architect-eyes Phase 0 audit IS the detector here.

### Phase 1 — Build the primitive ✅

- [x] Author `seed/lib/backend/noctusai_lib/primitives/tasks.py` with `schedule_coro` + `NoRunningLoopError`.
- [x] Update `seed/lib/backend/noctusai_lib/primitives/__init__.py` docstring inventory (no auto-re-export — consumers import the submodule per primitives layer convention).
- [x] Author `seed/lib/backend/tests/test_tasks.py` covering 8 tests (added one for the omitted-name default behavior on top of the 7 in scope).
- [x] Run `pytest tests/test_tasks.py -v` — 8/8 green.
- [x] Cross-check: `pytest tests/test_parsing.py tests/test_timeutil.py tests/test_tasks.py tests/test_jobs.py` — 120/120 green. Other seed-lib tests have BASELINE collection errors (`httpx`, `pytest-asyncio` missing in this Python 3.10 system env) unrelated to my change.

**Improvements:**
- Considered using `logger.exception(...)` inside the done-callback but that requires an active `sys.exc_info` — and inside a Task.add_done_callback the raised exception is NOT in `sys.exc_info`. Switched to `logger.error(..., exc_info=exc)` which explicitly attaches the captured exception's traceback. Same end result (full traceback logged), correct mechanism. This is documented inline in the helper.
- The bare-coroutine close-on-error path (`coro.close()` before raising NoRunningLoopError) prevents a confusing `RuntimeWarning: coroutine was never awaited` on top of the real error. Caught while writing `test_no_running_loop_raises_typed_error`.
- Tests use the `asyncio.run(driver())` pattern (matching `test_jobs.py`) instead of `pytest.mark.asyncio` to keep the seed test surface stable across the Python 3.10 / pytest-asyncio gap. Generalizable convention for primitives that need a running loop.

### Phase 2 — Refactor core/billing.py

- [ ] AST-edit `products/core/backend/app/routers/billing.py:199-205` to use `schedule_coro`.
- [ ] Drop the local `try/except RuntimeError` block (helper handles it).
- [ ] Run `cd products/core/backend && pytest tests/routers/test_billing*.py -v` — must stay green.

### Phase 3 — Refactor erp-imobiliario callsites

- [ ] AST-edit `certidoes_service.py:1099` to use `schedule_coro` (preserve task-tracking dict assignment).
- [ ] AST-edit `job_service.py:121` to use `schedule_coro`.
- [ ] Update affected tests where they patch `asyncio.create_task` — switch to patching the new helper, OR remove the patch and rely on real-task-with-mock-coroutine pattern (pref).
- [ ] Run `cd products/erp-imobiliario/backend && pytest` — no NEW failures vs baseline.

### Phase 4 — Project close

- [ ] Final §11 update + flip phases to ✅.
- [ ] One bundled proposal at `projects/schedule-coro-fire-and-forget/proposals/`.
- [ ] Phase-learning logs via `noctus.dev.phase_learning_log`.
- [ ] Three-way sync if methodology gaps surfaced (KB / CLAUDE / memory).
- [ ] Archive via `noctus.dev.archive`.
- [ ] Final commit + push to branch (NEVER to main).

---

## 7. Open questions

1. **Should `schedule_coro` accept a `loop` parameter for non-running-loop fallback?** — Recommendation: NO. Caller knows whether they're async; if not, caller should restructure (run via `asyncio.run` or `asyncio.run_coroutine_threadsafe` with explicit loop). Out-of-scope for primitive.
2. **Should the helper register with a global `WeakSet` to prevent task GC?** — Per CPython docs, an awaited Task is held by the loop until it completes; Tasks created via `loop.create_task` are also tracked in the loop's `_all_tasks` set in current asyncio. **Recommendation:** rely on stdlib's loop tracking (current behavior of all 3 callsites — no leaks observed). Re-evaluate if a future N=4 callsite uses very-short-lived Tasks where GC could intervene.

---

## 8. Dependencies & blockers

- None blocking.

---

## 9. Success criteria

- `noctusai_lib.primitives.tasks.schedule_coro` exists with documented contract + 7 tests green.
- All three production callsites import + use `schedule_coro` (zero local fire-and-forget hand-rolling).
- All affected product test suites green / no NEW failures vs baseline.
- One bundled proposal filed; phase-learning logged; three-way sync (if any methodology gap surfaced).

---

## 10. How to use this plan

Follows the standard execution workflow. Per-phase commits locally; final push at project close on branch `schedule-coro-fire-and-forget`. Never push to main.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | Initial draft after Phase 0 audit + N-recount on this branch (N=3 prod code) | engineer (claude-opus-4-7) |
| 2026-05-10 | Phase 0 ✅ — audit + decision lock (`primitives/tasks.py`); cross-product + service-line MCP scans returned zero additional fire-and-forget findings (short-line / hand-rolled patterns evade them) | engineer |
| 2026-05-10 | Phase 1 ✅ — `schedule_coro` + `NoRunningLoopError` shipped; 8/8 tests green; primitives `__init__.py` docstring inventory updated. Used `logger.error(..., exc_info=exc)` (not `logger.exception`) inside done-callback because the latter requires active `sys.exc_info` which isn't set inside Task callbacks | engineer |
