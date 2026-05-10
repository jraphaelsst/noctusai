# End-of-project bundle — schedule-coro-fire-and-forget

**Author:** claude-opus-4-7 (engineer subagent)
**Date:** 2026-05-10
**Project:** `projects/schedule-coro-fire-and-forget/`
**Branch:** `schedule-coro-fire-and-forget`
**Project final SHA at filing:** `046aa23` (will become tip after this proposal commits)

This bundle aggregates ALL improvements surfaced across Phases 0-3. Each item has its own brief title, linkage, application steps, risks, and independence flag. The reviewer can triage each separately.

---

## 1. Sweep AdConnect MVP branch when it merges to main (deferred-with-destination)

**Linkage:** Brief mentioned 4 callsites referencing AdConnect's `orders_service.py:96` + `financial_service.py:122` + `cart.py:88`. Those files don't exist on main yet (live on the AdConnect MVP branch). The canonical `noctusai_lib.primitives.tasks.schedule_coro` helper is now in place; future merge of AdConnect must consume it.

**Application steps:**
1. After AdConnect MVP branch merges to main, grep `products/adconnect -name '*.py' | xargs grep -nE 'asyncio\.create_task|ensure_future|loop\.create_task'`.
2. For each match, refactor to `schedule_coro(coro, logger=logger, name="<descriptive>")`.
3. If the file has a local `_schedule_coro` helper (per the brief's "Mirrors orders_service._schedule_coro" docstring evidence), DELETE the local helper after refactoring callers to the seed.
4. Run `cd products/adconnect/backend && pytest` — verify against the documented 19-failure baseline (no NEW failures).

**Risk:** None — the seed helper is already in place + tested; this is a mechanical follow-through.

**Independent:** YES — runs entirely on AdConnect's branch / post-merge tip.

---

## 2. Sweep `seed/lib/backend/noctusai_lib/domain/jobs/worker.py:21` docstring example (drive-by polish)

**Linkage:** The seed worker's wiring-recipe docstring shows `asyncio.create_task(worker.run_forever(stop_event=app_state.stop_event))` as the canonical example. Now that the seed ships `schedule_coro`, the example should use it (the helper is one layer up at `primitives/`, so `domain/jobs` may import it without violating the layer rule).

**Application steps:**
1. Open `seed/lib/backend/noctusai_lib/domain/jobs/worker.py`.
2. Update line 21 inside the docstring from
   ```python
   asyncio.create_task(worker.run_forever(stop_event=app_state.stop_event))
   ```
   to
   ```python
   from noctusai_lib.primitives.tasks import schedule_coro
   schedule_coro(worker.run_forever(stop_event=app_state.stop_event), name="job-worker-1")
   ```
3. Verify the docstring still parses (`python -c "import noctusai_lib.domain.jobs.worker"`).

**Risk:** Zero — docstring-only change, no runtime impact.

**Independent:** YES.

---

## 3. Document the "patch at consumer-side import binding" convention (methodology gap)

**Linkage:** Phase 3 surfaced the slip class where `patch("...service.asyncio.create_task")` becomes a silent no-op after a refactor renames the collaborator. The seed helper-rollout pattern is generalizable — every absorption that replaces a stdlib call with a seed helper will hit this same test-fragility surface.

**Application steps:**
1. Add a one-line bullet to `KB § PATTERNS/testing.md` under "Mocking conventions": *"Patch at the consumer-side import binding (`module.under.test.collaborator`), never at the producer-side definition (`noctusai_lib.X.collaborator`). Surviving refactors-of-seed-helpers depends on the local symbol-table entry, not the source-of-truth path."*
2. Cross-reference from this project's findings.

**Risk:** None — additive doc.

**Independent:** YES.

---

## 4. Promote `seed-lib-layout.md` decision tree to MCP tool exposure (methodology / MCP-first opportunity)

**Linkage:** Phase 0's destination decision (`primitives/tasks.py` vs `api/tasks.py`) was answered deterministically by walking the 6-question decision tree. The brief offered both as candidates; the tree resolved unambiguously. Generalizable: every "where does this helper go?" decision could be a 30-second MCP call instead of a 5-minute agent-side reread of the KB doc.

**Application steps:**
1. Add `noctus.dev.seed_lib_destination` MCP tool in `mcp/noctusai/tools/noctus/dev/`.
2. Tool accepts: helper-name + a one-line summary OR a list of imports the helper uses.
3. Walks the 6-question tree (each gate keyed on grep-for-imports + agent-confirm). Returns the layer + folder + reasoning trace.
4. Doc-stamp at `KB § PATTERNS/seed-lib-layout.md` pointing at the tool.

**Risk:** Low — tool is read-only; the agent still confirms before authoring.

**Independent:** YES — entirely a new MCP tool; doesn't touch existing absorption work.

---

## 5. Consider lifting the "two failure surfaces" pattern into seed docs (knowledge piece)

**Linkage:** Phase 2's improvement noted that fire-and-forget code has TWO failure surfaces (sync arg-resolve vs async coroutine-raise). Future agents refactoring similar shapes might miss this and merge the two outer try/excepts, dropping the sync-failure log path.

**Application steps:**
1. Add a one-paragraph section to `seed/lib/backend/noctusai_lib/primitives/tasks.py`'s module docstring under a new "Failure surfaces" heading.
2. Optionally cross-link from `KB § PATTERNS/logging.md`.

**Risk:** None — additive.

**Independent:** YES.

---

## Triage summary

| # | Title | Independent | Action class |
|---|---|---|---|
| 1 | Sweep AdConnect MVP branch on merge | YES | deferred-with-destination |
| 2 | Sweep seed worker.py docstring example | YES | apply-now (drive-by polish, ≤2-line edit) |
| 3 | Document "patch at consumer-side import binding" | YES | apply-now (KB single-line addition) |
| 4 | Promote seed-lib-layout decision tree to MCP tool | YES | defer (MCP-first opportunity, future project) |
| 5 | "Two failure surfaces" knowledge piece in seed docs | YES | apply-now (additive doc) |

**Engineer's recommendation:** Items 2, 3, 5 are ≤5-minute edits and applicable now per the architect's "engineer findings get applied immediately when applicable" rule. Item 4 is project-shaped (new MCP tool, sub-tasks, tests). Item 1 waits on AdConnect MVP merge (external dependency).
