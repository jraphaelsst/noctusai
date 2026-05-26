---
name: noc-roadmap
description: Use when authoring a multi-session initiative plan — triggers "roadmap", "create a roadmap", "trigger conditions", "phase 2+ deferred", "Phase 1 / Phase 2", "trigger when N≥...", "T1 / T2 trigger". Drops the canonical roadmap template at `project-history/roadmaps/<slug>-YYYY-MM.md` so multi-slice work has a durable home that survives /clear + context summarization.
version: 1.0.0
---

# noc-roadmap — multi-session roadmap authoring

Multi-slice initiatives are **roadmaps**, not projects. Project folders are ephemeral (delete-on-archive); KB is methodology-only; ndjson is event-shaped. Roadmaps live in `project-history/roadmaps/<slug>-YYYY-MM.md` — durable, mutable, structured.

## When to invoke

- Authoring a plan that spans **>1 session** OR has **>3 slices**.
- Capturing a **deferred decision** with trigger conditions ("we'll do X when Y fires").
- Multi-phase work where Phase 1 ships today and Phase N is conditional.

If the work fits in one session and one PR — it's a project, not a roadmap. Use the project-execution flow instead.

## Workflow

1. **Slug + month** — `<kebab-slug>-YYYY-MM.md`. Example: `cache-backend-portability-2026-05.md`. Month is when the roadmap was AUTHORED (decisions decay; the month signals freshness).
2. **Drop the template** — copy `templates/roadmap.md` (see Template section below) into `project-history/roadmaps/<slug>-YYYY-MM.md`. Fill the sections in order — don't skip "Open questions" or "Anti-goals"; those are the gold.
3. **Trigger conditions are first-class** — every deferred phase MUST list a named trigger (T1/T2/...). "When the trigger fires" beats "when we feel like it" for surviving context-resets.
4. **Decision log** — append to it; don't rewrite. Old decisions explain current state.
5. **Retrospective** — fill at first trigger fire. Captures lessons absorbed back to KB/memory.

## Required sections

| Section | Why |
|---|---|
| **Origin** | Captures the moment the roadmap was authored — the question or surfaced gap. Future-you needs the why. |
| **Trigger conditions (T1–TN)** | The "when" of deferred phases. Each trigger names a SIGNAL that can be observed, not a feeling. |
| **Phase 1 (SHIPPED)** + **Phase N (DEFERRED)** | Phase 1 lands in the same commit as the roadmap. Phase N is gated on triggers. Mixing them is a mis-shape. |
| **Anti-goals** | Explicit non-goals — prevents scope creep at trigger fire. Often the gold of the roadmap. |
| **Open questions** | The "we'll revisit at trigger time" list. NOT a TODO; an explicit deferral. |
| **Decision log** | Append-only. Each entry is `YYYY-MM-DD: <decision>`. |
| **Retrospective** | Filled at trigger fire. Lessons → KB/MEMORY. |
| **Composes with** | KB pattern siblings. Keeps the roadmap honest about overlap. |

## Optional sections (use when applicable)

- **Cost shape change** — explicit $-impact estimate when migrating from free to paid.
- **Anti-goals** — sub-list of "things we EXPLICITLY won't do."
- **File trail** — list of files this roadmap touched.

## Guardrails

- ❌ DON'T author a roadmap for single-PR work. Project folders or in-line decisions are correct there.
- ❌ DON'T mix Phase 1 (shipping) with Phase 2+ (deferred) — separate sections. Reader needs to know what landed vs. what's pending.
- ❌ DON'T forget trigger conditions. "Defer until later" without a trigger = silent never.
- ❌ DON'T mutate Phase 1 after the commit. Phase 1 is the SHIPPED state — mutations belong in a new commit (decision log captures the why).
- ✅ DO link from KB patterns to the roadmap when applicable. The roadmap is the migration plan; KB is the methodology.
- ✅ DO close roadmaps to `closed/<slug>-YYYY-MM.md` when ALL phases have shipped OR all triggers permanently can't fire.

## Template

See `.claude/skills/noc-roadmap/template.md` — drop this verbatim, fill the bracketed sections.

## Depth

- KB § PATTERNS/common/roadmap-tracking.md — the pattern this skill implements.
- Reference exemplars: `project-history/roadmaps/cache-backend-portability-2026-05.md` (Phase 1 SHIPPED + 4 deferred phases + 5 named triggers + anti-goals).
