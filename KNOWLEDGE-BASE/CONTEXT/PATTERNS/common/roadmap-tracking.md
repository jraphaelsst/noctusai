# Roadmap tracking — multi-session structured project plans

**What it is.** A durable home for **multi-session, mutable, structured project plans** — the artifact that doesn't fit anywhere else in noc's existing durable layers. Codified 2026-05-26 after the gap surfaced ("we need a durable record for a multi-slice automation initiative — `projects/<slug>/` is ephemeral").

**The gap this fills.**

| Layer | What it's for | Why a roadmap doesn't fit |
|---|---|---|
| `KNOWLEDGE-BASE/` | Methodology / patterns / guides | A project plan isn't methodology — it's "we're doing X." Polluting KB erodes the "every doc = methodology" signal. |
| `MEMORY.md` + `memory/*.md` | Agent behavioral memory across sessions | Memories = preferences / rules / lessons, not project state. |
| `project-history/auto-improvement.ndjson` | Append-only ledger of surfaces (drift / improvement observations) | NDJSON suits events; doesn't suit long-form slice descriptions / decision rationale / retrospective. |
| `project-history/worktree-salvage.ndjson` | Recovery pointers (mechanical event log) | Same — event log, not plan. |
| `projects/<slug>/PROJECT.md` | Active project workspace | **Ephemeral** — archived when done. Decision log lost on archive. |
| `archive/` | Dead projects | For corpses, not living roadmaps. |
| `CLAUDE.md` / `CONTEXTUALIZE.md` | Always-loaded routers | Roadmap doesn't need to be auto-loaded; needs to be findable. |

**The home: `project-history/roadmaps/<slug>.md`.** Sibling of the existing ledgers under `project-history/`. Committed in git → durable + diffable. Markdown → human + AI readable, mutable for status updates, supports the long-form sections (rationale, decisions, retrospective) that ndjson can't hold cleanly.

## Naming convention

`project-history/roadmaps/<slug>-YYYY-MM.md` where `<slug>` is kebab-case + descriptive.

Examples:
- `automation-orchestration-2026-05.md`
- `cross-product-recurrence-detection-2026-06.md`
- `seed-deploy-config-contract-2026-05.md` (if we had wanted one)

The `YYYY-MM` suffix disambiguates if the same topic gets revisited later (e.g., `agent-context-2026-05.md` for Phase A + a hypothetical `agent-context-2027-02.md` for a future revision).

## Document shape (template)

```markdown
# <slug> — <descriptive title>

> Durable record (per KB § PATTERNS/common/roadmap-tracking.md).
> Lives here because [brief — why this isn't a KB doc / memory / ndjson].
> On close: absorb lessons → KB/memory, optionally move to closed/.

## Goal
What success looks like. Concrete + measurable.

## Slices
| # | Title | Files-to-modify | Agent | Status | Wave | Verify recipe | SHA |
|---|---|---|---|---|---|---|---|

Status ∈ {pending, in-flight, blocked, shipped, abandoned}. Update as slices land.

**Every slice carries a verify-recipe, not only a test-recipe.** Tests-green ≠ verified-in-production — the unit surface stops at module boundaries; the *verify-recipe* is the explicit live-state proof (provider reachable, ndjson written, MCP round-trip, page shows real data). An empty cell is a positive *"no live check needed"* claim, not a skip. Born 2026-05-26 (automation-orchestration roadmap close: 7 slices shipped tests-green but un-exercised against live caches/MCP). Mirrors the `noc-roadmap` skill Required-sections row + `templates/roadmap.md` column.

## Decision log
| Date | Decision | Why |

Capture non-obvious calls + the rationale. The "why" matters more than the "what."

## Open questions
Numbered list of pending decisions / known unknowns. Resolve as work progresses.

## Retrospective (filled at close)
Surprise wins, drift surfaces, methodology improvements, costs vs. estimates.

## Composes with
Links to KB patterns / sibling roadmaps / depth references.
```

## Lifecycle

1. **Author** — when a multi-slice initiative starts. Tech-lead writes the roadmap doc in the same session as the work begins.
2. **Update** — as slices ship: update the SHA column, append to decision log, resolve open questions, append running lessons to the retrospective section.
3. **Close** — when all slices ship (or the initiative is abandoned):
   - Fill the retrospective fully.
   - **Absorb durable lessons** into KB pattern docs / memory entries (per [[persistent-files-absorption]] — recovery pointer ≠ absorbed lesson).
   - Optionally move to `project-history/roadmaps/closed/<slug>.md` for organizational clarity (git preserves it either way).
4. **Revisit** (rare) — if a topic gets a v2: new file with year-month suffix; reference the prior roadmap in `## Composes with`.

## Anti-patterns

- **Roadmap in `projects/<slug>/PROJECT.md`.** Gets archived; decision log lost. Use `project-history/roadmaps/` for the durable record; `projects/<slug>/` for ephemeral worktree-scoped state.
- **Roadmap as a KB pattern doc.** KB is canonically methodology — adding project state muddies the contract.
- **Roadmap as NDJSON.** Ndjson suits events; roadmaps need long-form sections (rationale, retrospective) that ndjson can't render readably.
- **Skipping the retrospective on close.** The retrospective IS the absorption-to-KB sieve — what we learned, what we'd do differently. Skip it → lessons stay buried in commit history.
- **Letting status drift from reality.** Status column must reflect actual state. Stale roadmaps mislead future agents.

## Composes with

[[persistent-files-absorption]] (the absorb-on-close discipline — recovery pointer ≠ absorbed lesson) · [[scoped-auto-improvement]] (the ledger that captures in-flight surfaces during slices; absorbed lessons may promote ledger entries to s3-kb) · [[claude-md-router-discipline]] (sibling discipline: durable, structured, location-fixed) · [[methodology-codification-pipeline]] (retrospective lessons feed s1→s4 promotions).
