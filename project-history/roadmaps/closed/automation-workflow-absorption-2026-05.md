# automation-workflow-absorption-2026-05 — absorb the external productivity-CLI's command layer

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> NOT to be confused with `automation-orchestration-followup-2026-06.md` (methodology-automation tooling).
>
> ⚠️ **DISAMBIGUATION (verified 2026-05-31 by a 4-agent eval — read before acting):**
> The source of this schema is **NOT** the on-disk sibling folder `repository/NoctusAI/automations/`.
> That folder is the superseded **`noctus-starter`** methodology scaffold (markdown spec only — an
> early Agno dev-team blueprint that current noc already SHIPPED + surpassed; zero productivity
> tables; zero matches for `intent_patterns`/`sessoes_foco`/`learned_promotions`). The
> `automation_workflow` schema comes from a **separate standalone command-driven productivity CLI
> that exists in NONE of the 11 sibling repos on disk** (exact-table-name greps = zero across all).
> They merely share the word "automation." Two unrelated artifacts.

## Goal

Decide whether the external productivity-CLI behind the prod `automation_workflow` schema holds any
**dispatch/NLU/learning logic** worth absorbing into noc — given that noc's chatbot stack is already
mature and deliberately **LLM-first**.

## Current state (what's already captured vs the real gap)

- **The 12 prod `automation_workflow` tables are EMPTY (0 rows, 2026-05-31)** → drop candidate, **no data migration needed**. RLS hand-applied to all 12 as defense-in-depth while they sit (see `feedback_rls_sweep_and_orphan_schema`).
- **The data model is ALREADY mirrored in the `daily-life` product** (schema `daily_life` == the same 12 tables). daily-life ported the **domain-CRUD half** — `tarefas`/`metas`/`notas`/`eventos`/`sessoes_foco`/`metricas_produtividade`/`checkins` (services + brief). So the productivity-domain absorption is **largely already done**.
- **The UN-captured half = the 5 command-knowledge tables**, left UNWIRED in daily-life: `commands`, `command_history`, `intent_patterns`, `context_rules`, `learned_promotions`. THIS is the only potential prize.

## The one potential prize (conditional on getting the external repo)

A **rules-based command layer**: 3-tier dispatch cascade (direct → pattern → LLM, tier recorded per
call); regex/keyword/fuzzy **intent recognition** with confidence thresholds; per-user `context_rules`
parameter resolution; and an adaptive **`learned_promotions`** loop that auto-promotes repeated LLM
resolutions to cheap deterministic patterns after ≥3 hits (with token/latency telemetry) — structurally
analogous to noc's own s1→s3 codification pipeline.

**⚠️ LLM-first tension (decision gate before any absorption):** noc's command dispatch is deliberately
**LLM function-calling** (`LLMDispatcher` / `OpenAIToolOrchestrator`, Fake+Real+factory), NOT a
rules/intent engine. A rules router **earns its place ONLY** if it covers deterministic / offline /
cost-reducing command routing the LLM path genuinely doesn't (cheap fast offline commands + a
learn-to-promote ladder that lowers LLM spend over time). Otherwise absorbing it is a **regression** —
reject it and close this roadmap.

## Slices (provisional — firm up after the repo is inventoried)

| # | Title | Depends on | Tier | Status |
|---|---|---|---|---|
| A0 | **Locate + read the external productivity-CLI repo** — the DATA shapes are already known; only the LOGIC (dispatch/intent/learning) is missing | repo access | BLOCKER | **blocked — repo not on disk, location unknown** |
| A1 | Judge the rules-layer against the LLM-first tension gate — does it cover deterministic/offline/cost-reducing routing the LLM path lacks? If NO → reject, close roadmap | A0 | HIGH | pending |
| A2 | If YES: absorb dispatch + NLU + learned-promotions → seed/lib, **extending `noctusai_lib.domain.chatbot`** (absorption-search first: `noctus.seed.scan_fusions`) | A0, A1 | MED | pending |
| A3 | Wire the 5 command-knowledge tables into daily-life (the CRUD half is already there) | A2 | LOW-MED | pending |
| A4 | Drop the empty prod `automation_workflow` schema (0 rows; reconcile shape against `daily_life`, then drop) | A1–A3 decided | LOW | ready (no data to migrate) |

## Open questions / blockers

1. **Where is the external productivity-CLI repo?** (URL / path / access). NOT on disk in any sibling — the prod tables reveal data shape only, never the dispatch/intent/learning LOGIC. A0 can't start without it.
2. ~~Live data to preserve?~~ **RESOLVED 2026-05-31: all 12 prod tables EMPTY (0 rows)** → no migration; A4 is a clean drop once A1 decides.
3. Does the rules-layer clear the LLM-first tension gate (deterministic/offline/cost-reducing), or is it a regression against noc's intentional LLM-function-calling dispatch?

## Decision log

- 2026-05-31 — Opened as "orphan schema, migrate-or-drop?"; user reframed as "absorption source."
- 2026-05-31 — 4-agent eval **corrected a name-collision conflation**: the schema's source is the
  external CLI, **NOT** the on-disk `automations/` folder (that's superseded `noctus-starter`). Verified
  by exact-table-name greps across all 11 siblings = zero matches.
- 2026-05-31 — Found the data model is **already mirrored in daily-life** (CRUD half done); only the
  5 command-knowledge tables are uncaptured. Prod tables EMPTY → drop, not migrate.
- 2026-05-31 — Recorded the **LLM-first tension**: a rules/intent engine must justify itself vs noc's
  intentional LLM-function-calling dispatch, or it's a regression.

## CLOSED — 2026-05-31 (no prize on disk)

Resolved without absorbing anything. Findings at close:

- **The schema's source CLI is not on this machine** — the user pointed at the sibling `automations/`
  folder, but that folder is the **methodology/dev-team design workspace** (its own AUDIT.md/PROJECT.md
  prove it, with user quotes), NOT the productivity CLI. Zero productivity code in it. The two "automation"
  things are unrelated; the name collision misled both user and assistant.
- **The productivity domain is already captured** in the daily-life product (`daily_life` schema). The only
  uncaptured piece was the rules-based command layer — and its code is off-disk/unreadable, while noc is
  deliberately LLM-first (a rules engine would need to clear the deterministic/offline/cost-reducing gate
  to not be a regression). No code to judge → no absorption.
- **The prod `automation_workflow` schema** — `DROP SCHEMA … CASCADE` was run, but the schema was in
  **PostgREST's exposed-schemas list**, so the drop broke the REST schema cache (`PGRST002`, fleet-wide
  503 for ~30 min during the deploy). Recovered by **recreating the empty schema** + `NOTIFY pgrst,
  'reload schema'`. So the schema now EXISTS again as an inert empty namespace; a clean drop is
  **deferred pending unexpose-first** (dashboard → API → Exposed schemas). See
  `feedback_postgrest_exposed_schema_drop`.
- **The `automations/` folder was salvaged-then-deleted** — its unique provenance (AUDIT.md + PROJECT.md)
  preserved at `project-history/provenance/methodology-origin-2026-04/`; the superseded scaffold removed.

## Retrospective

**Lesson (→ memory `feedback_rls_sweep_and_orphan_schema`):** a shared word in two names ("automation") is
enough to silently fuse two unrelated artifacts across BOTH a human's memory and an assistant's inference.
The fix that caught it: **verify by unique identifier, not by name** — exact-table-name greps (`sessoes_foco`,
`learned_promotions`) across all siblings = zero, which is stronger evidence than any folder name. When an
investigation hinges on "is X the same as Y?", anchor on a content fingerprint, never the label.
