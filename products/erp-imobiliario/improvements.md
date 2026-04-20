# Improvements — METAS — Implementation Plan

> **Auto-generated** from `METAS-PLAN.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `METAS-PLAN.md`
**Plan status:** **All phases backend-complete** ✅ — 1, 2, 3, 4, 5a, 5b, 6, 7 (MVP), 8, 9 shipped. 49 `/api/metas/*` routes live; 2 migrations applied to dev DB (016 + 017 + 018); trigger pipeline auto-populates `meta_eventos` from ERP entities. Frontend: `MetasDashboard.tsx` + `hooks/useMetasDomain.ts` + route `/metas/dashboard`. **Remaining:** detailed drill-down UIs (Phases 2.6, 3.7, 4.7, 6.6, 8.5, 10, 11 polish), 5b realdb tests, UI visual validation, optional component extraction to seed/lib.
**Completed phases:** 9 of 11.
**Phases with recorded improvements:** 0 of 9 completed.

## Improvements by phase

_No improvements recorded yet. As each phase completes, the agent should append an `**Improvements:**` block to that phase section in the plan, then re-run this tool._

## Completed phases missing an improvements block

These phases shipped without a recorded improvement observation. Either the agent genuinely had nothing to flag (rare), or they forgot. Back-fill with an `**Improvements:**` block when possible — or a line stating "no improvements identified" to make the absence intentional.

- Phase 1 — Foundation (migration + core models)
- Phase 3 — Periods & company meta
- Phase 4 — Point rules & scoring config
- Phase 5 — Events pipeline (triggers)
- Phase 6 — Leader & agent quotas
- Phase 7 — Dashboards
- Phase 8 — Closings & history
- Phase 9 — Rankings
- Phase 10 — Wire into existing ERP pages

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- **Forecasts** ("at this pace, team X will hit 78% of monthly meta") — deferred; user explicitly declined for MVP. Future phase.
- **Weighted auto-distribution** of VGV across teams based on historical performance — deferred; manual entry in MVP.
- **Standalone Reuniões module** — deferred; for now leader/owner logs attendance manually into `meta_eventos`.
- **Cross-product gamification adoption** (Therapy, PF, Daily Life) — only after patterns stabilize in ERP.
- **Public / agent-visible cross-team leaderboards** — privacy trumps spectacle; agents see own rank in their team only.

## Open questions still blocking

- **Captação timestamp** — add `erp.ativos.data_captacao` (distinct from `created_at`) or reuse `created_at`? — Decide during Phase 5, owner.
- **Exclusividade flag** — does current ERP track which listings/contracts are exclusive? Audit + add boolean column(s) or reuse existing metadata. — Audit in Phase 5.
- **Reunião module** — for now, owner/leader manually logs attendance events via Metas. Full module is a future product or phase. — Deferred.
- **Team color / branding** — DRAGÃO/LEÃO/ÁGUIA currently implicit; need visual palette. — Gather from owner in Phase 2.6 before UI.
- **Weighted VGV distribution** — currently manual input by owner. Future: auto-suggest based on historical performance. — Deferred until Phase 3+ observation.
- **Agent promotion to leader** — what happens to their team membership / metas? Likely: leave old team as member, add to new team as lider. — Decide in Phase 2 UX.
- **Mid-period team transfer** — agent's events stay attributed to their team at event time (via `equipe_id_snapshot`). Confirm UX in Phase 5.
- **UI framework choice for Configurações drag-and-drop** — use `dnd-kit` (already in ERP?) or a simpler select-based approach? — Needed before Phase 2.6.
