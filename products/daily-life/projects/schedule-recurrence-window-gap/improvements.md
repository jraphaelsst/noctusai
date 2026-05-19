# Improvements — Schedule Recurrence Window Gap — Project Document

> **Auto-generated** from `PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `PROJECT.md`
**Plan status:** Phase 0 ✅ — Q1/Q2 decided (§2), §3a audit `[A]` (no seed-lift); **P1/P2 unblocked, awaiting user "continue"** (phase-by-phase cadence)
**Completed phases:** 1 of 4.
**Phases with recorded improvements:** 1 of 1 completed.

## Improvements by phase

### Phase 0 — Audit + decisions

- The original defect (imported-but-uncalled `expandir_recorrencias`) is a class — a keeper could flag "module-level import used nowhere in the file" for router/service modules. Deferred → standing absorption/keeper queue (out of this project's bounded scope; named, not silent).
- `expandir_recorrencias` default window (today−30 … today+90) silently caps an unbounded query; acceptable but the cap should be explicit/asserted when P1 changes the fetch — captured for P1.
*Phase proposal:* none filed — Phase 0 is decisions+audit; the two improvement bullets are deferred-with-destination (above), no bundle warranted.

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- Redesigning the scheduling/recurrence engine — too broad; this is a bounded correctness gap.
- Cross-product seed lift — only if the P0 scan shows `N≥3` unifiable duplication (then it becomes the `[F]` destination, not pre-decided here).
- erp/PF financial-recurrence + therapy session-recurrence — different domains; out unless P0 proves a shared contract.

## Open questions still blocking

- ✅ **RESOLVED (Phase 0, §2)** — window-filter semantic = recurrence-aware lower-bound drop. P1 unblocked.
- ✅ **RESOLVED (Phase 0, §2)** — pagination contract = `count` = parent-row count, occurrences derived/not separately paginated. P2 unblocked. Larger occurrence-pagination = named future follow-up `schedule-occurrence-pagination` (not this project).
- ✅ **RESOLVED (Phase 0 audit, §2)** — `[A]` accept-with-rationale; recurrence-expansion domain-divergent, no `N≥3` unifiable contract, no seed-lift. Cataloged in `KB § PATTERNS/accept-with-rationale.md`.
