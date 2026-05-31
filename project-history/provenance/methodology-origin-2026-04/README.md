# methodology-origin-2026-04 — provenance of the NoctusAI methodology

> **Salvaged 2026-05-31** from the (now-deletable) sibling workspace
> `repository/NoctusAI/automations/` before that stale folder was removed.
> This is **historical provenance — not live methodology.** The live methodology is
> `CLAUDE.md` + `KNOWLEDGE-BASE/` in this repo, which superseded everything here.

## What this is

On **2026-04-30** the user opened a consolidation workspace (the sibling folder literally named
`automations/`) to merge two pre-existing artifacts into one home:

1. **`noctus-starter/`** — a stack-agnostic methodology scaffold (~4,400 lines of docs) extracted
   from a working multi-product SaaS.
2. **`dev-team.md`** — a v0.1 reference spec for an 11-agent Agno dev-team (+ 3 sub-teams, incl.
   `incident_response_team`) in a hybrid coordinate/collaborate architecture.

The plan: the methodology becomes the team's behavioural charter; the Agno team replaces the
single-assistant model; the keeper's deterministic detectors survive as a tool the Security agent
calls; a reference stack (FastAPI + Supabase + React + Vite + TanStack + Zustand + Tailwind)
populates `seed/`. It reached **Phase 0–4** (the audit + methodology restructure docs); **Phase 5
(building the actual code) never happened in that folder** — the implementation went into THIS repo
(`noctusai`) instead and far surpassed the spec.

## The two files

- **`AUDIT.md`** (464 lines) — the canonical Phase-0 audit: every design decision, tension
  resolution, and proposed phase, **with the user's original quotes preserved**. This is the
  irreplaceable artifact — the origin story / decision record that seeded the current methodology.
- **`PROJECT.md`** (402 lines) — the living project doc for the consolidation (phases, constraints,
  confirmed user answers).

## Why it was salvaged then the folder deleted

A 4-agent evaluation (2026-05-31) confirmed **everything substantive in the `automations/` folder is
already shipped and surpassed in this repo**: the Agno dev-team → `dev_team/` + `products/dev-team/` +
`noctus.team.*` + `KB § PATTERNS/architect/dev-team.md`; scoped per-agent KB reads → the agent-context
architecture; every behavioural rule → `CLAUDE.md` §1 + KB (hardened with keeper-mirror caches, skills,
agents). The **only** unique value was this provenance/decision narrative — preserved here. The stale
folder (markdown-only, empty git, no commits) was then removed.

> Not to be confused with the `automation_workflow` Postgres schema — an UNRELATED external
> productivity-CLI's data (see `roadmaps/closed/automation-workflow-absorption-2026-05.md`). The two
> merely shared the word "automation."
