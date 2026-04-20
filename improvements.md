# Improvements — AI Expansion — Project Document

> **Auto-generated** from `AI-EXPANSION-PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `AI-EXPANSION-PROJECT.md`
**Plan status:** Phase 1 atlas + §5a Pattern Catalog shipped (enriched with lessons from ERP Metas build-out). Phase 2 (user triage) pending user review. Recommend triaging **by pattern** (P1–P6) rather than by opportunity — one pattern unlocks many rows.
**Completed phases:** 1 of 2.
**Phases with recorded improvements:** 1 of 1 completed.

## Improvements by phase

### Phase 1 — Opportunity Atlas

- The atlas reads each product's `services/` directory but doesn't consult the actual UI — some opportunities may misread what the user actually sees. Next iteration: cross-reference with `frontend/src/pages/` per product and trim anything that doesn't match an existing page or planned page.
- LGPD tags are rule-of-thumb from the KB rule, not individually traced. Items tagged `high` all need the formal 5-question LGPD review before they leave triage.
- Effort sizing is gut-feel. **First calibration point in from the Metas build-out**: "add a contextual indicator to a page" is realistically **S (<1d)** when the lib + `<AIIndicator/>` pattern exist, not the M tag I'd use without the pattern. Re-tag accordingly when triaging §5 items that are "indicator on a page" or "small notification" shapes — they're mostly S.
- **New grouping axis for triage**: instead of per-opportunity triage, **group opportunities by the pattern they need** (P1–P6). Building pattern P1 once unlocks ~10 §5 rows. Makes Phase 2 easier: pick 1–2 patterns to harden, then most of the atlas falls as low-effort follow-ups.

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- Streaming-based features — wait for lib support.
- Fine-tuning / custom models per org — wait for a real business case.
- Per-org usage dashboards / token billing — wait for cost pressure.
- Voice-first UX (wake word, dictation, full-duplex) — wait for lib audio streaming + latency work.
- Training a proprietary model — explicitly no.

## Open questions still blocking

- **Prioritization axis** — impact first, effort first, or product-by-product? *Needs answer before Phase 2.*
- **AdConnect timing** — hold all AdConnect opportunities until migration, or spec them now so migration + AI land together? *Needs answer in Phase 2.*
- **Streaming dependency** — should we invest in lib streaming (adds task.md Phase 11) before Phase 3, or ship non-streaming versions first? *Decide after Phase 2 — only relevant if `needs: streaming` opportunities land in the priority top-5.*
- **Per-product prompt versioning** — each opportunity's prompt needs a version tag for the response cache. Where does it live: constant in the service, DB row, or git-tagged file? *Decide during Phase 3 first implementation.*
- **LGPD review gating** — `high`-tagged items need formal review before implementation. Who approves? *Needs answer before the first `high` item enters a phase.*
