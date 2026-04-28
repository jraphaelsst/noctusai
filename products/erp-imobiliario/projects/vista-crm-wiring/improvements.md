# Improvements — Vista CRM Wiring — Project Document

> **Auto-generated** from `PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `PROJECT.md`
**Plan status:** Design locked → Phase 1 ready
**Completed phases:** 0 of 4.
**Phases with recorded improvements:** 0 of 0 completed.

## Improvements by phase

_No improvements recorded yet. As each phase completes, the agent should append an `**Improvements:**` block to that phase section in the plan, then re-run this tool._

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- Writing ERP canonical rows from Vista payloads — deferred to the later migration-seed project the user explicitly postponed.
- Bi-directional sync or write-back into Vista — deferred because v1 is showcase-only.
- Background sync jobs, webhooks, cron ingestion, or persistent cache tables — deferred because the user asked for live-read now.
- Customer-facing/public listing exposure — deferred because access is admin-only in phase 1.
- Generic multi-CRM abstraction — deferred because the user explicitly chose a Vista-specific adapter first.
- Automatic field-by-field migration reconciliation — deferred until the future DB-population phase.

## Open questions still blocking

- **Which exact Vista endpoint families are reachable with this tenant's credentials?** — needs answer before Phase 1 ends / decided by execution against the real tenant.
- **What is the safest home for the Vista credentials in phase 1: existing ERP env config only, or a future admin-managed connector config?** — needs answer before Phase 2 / decided by user + repo conventions.
- **Should every tab expose raw JSON inspection, or only a subset?** — can be decided during Phase 3 / decided by execution agent with user confirmation if the UI becomes noisy.
- **Do any Vista domains require special pagination, nested fetch choreography, or per-item expansion calls that make “all tabs in v1” too expensive?** — needs answer during Phase 1 / decided by live API exploration.
- **Should the page include side-by-side “future ERP landing entity” hints in v1?** — can be decided in Phase 3 / decided by user after first browse.
- **What request volume / latency is acceptable for live-read admin browsing?** — can be answered in Phase 4 after real-tenant testing / decided by measured behavior.
