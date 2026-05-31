# automation-workflow-absorption-2026-05 — absorb the productivity-assistant repo into noc

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> NOT to be confused with `automation-orchestration-followup-2026-06.md` (that one is
> methodology-automation tooling — linters, query tools). THIS is the absorption of an
> EXTERNAL repo the user built: a command-driven personal-productivity assistant.

## Goal

`automation_workflow` is a **separate repo the user created to develop automations** — not a
noctus product itself, but it holds features/tools worth **propagating into real noc products**
(seed/lib for the generic parts; daily-life for the productivity-domain parts). It surfaced
on 2026-05-31 as a 12-table schema in the noctusai prod DB that **no product code references**
(`grep -rl automation_workflow products/ seed/ mcp/` = empty). Treatment = **feature/tool
absorption**, not migrate-or-drop. RLS was hand-applied to all 12 tables as defense-in-depth
while the data sits (see `feedback_rls_sweep_and_orphan_schema`).

## Feature surface (inferred from the prod schema — the LOGIC lives in the external repo, not yet read)

| Cluster | `automation_workflow` tables | Likely absorption target | Seed-first note |
|---|---|---|---|
| Command dispatch + NLU | `commands`, `command_history`, `intent_patterns`, `context_rules` | **seed/lib** (`noctusai_lib.domain.chatbot` / a new `commands` domain) | Generic command router + intent matcher = reusable by every product's chat/command layer. Check overlap with existing `noctusai_lib.domain.chatbot.delivery`. |
| Adaptive learning | `learned_promotions` | **seed/lib** | A learn-from-usage promotion mechanism — generalize cautiously; may overlap the methodology codification pipeline. |
| Productivity domain | `tarefas`, `metas`, `notas`, `eventos`, `sessoes_foco`, `metricas_produtividade`, `checkins` | **daily-life** product | Heavy overlap with daily-life's existing domain — absorb as features into daily-life's schema, don't fork a new product. |

## Slices (provisional — firm up after the repo is inventoried)

| # | Title | Depends on | Tier | Status |
|---|---|---|---|---|
| A0 | **Locate + inventory the external repo** — clone/read; map each table to its service/router/logic; confirm the cluster split above | repo access | BLOCKER | **blocked — need repo location** |
| A1 | Absorb command-dispatch + NLU → seed/lib (Protocol+Fake+Real+factory; consume in ≥1 pilot) | A0 | HIGH | pending |
| A2 | Absorb adaptive-learning primitive → seed/lib (or fold into codification pipeline if duplicative) | A0, A1 | MED | pending |
| A3 | Absorb productivity-domain features → daily-life (schema + services + FE surfaces) | A0 | MED | pending |
| A4 | Decide the fate of the prod `automation_workflow` schema + data (migrate rows into the absorbing schemas, then drop the orphan schema) | A1-A3 | LOW | pending |

## Open questions / blockers

1. **Where is the `automation_workflow` repo?** (URL / local path / access). The prod tables show the
   data shape but not the dispatch/intent/learning LOGIC — A0 can't start without it.
2. Is there **live data** in the 12 prod tables to preserve (real usage), or is it dev/seed scaffolding?
   (`SELECT count(*)` per table will tell — informs whether A4 needs a data migration or just a drop.)
3. Does the command-dispatch layer overlap enough with `noctusai_lib.domain.chatbot` to **extend** rather
   than add a sibling? (absorption-search duty — run `noctus.seed.scan_fusions` against the imported code.)

## Decision log

- 2026-05-31 — Reframed from "orphan schema, migrate-or-drop?" to "absorption source." RLS hand-applied
  to all 12 tables (defense-in-depth) so the holding state is safe. Roadmap opened; A0 is the gate.

## Retrospective

_(on close — absorb lessons → KB/memory.)_
