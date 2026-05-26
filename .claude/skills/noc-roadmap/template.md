# <slug>-YYYY-MM — <one-line title>

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: <one-line — surfaced question / observed gap / strategic decision>.
> Decision: **<what we chose to do today vs. defer>.**

## Origin

<2–4 sentences. What surfaced the need for this roadmap? Who asked, when, in response to what? Future-you needs the why.>

## Trigger conditions (the "when")

Migration / next-phase kicks off when **ANY** of the following fires:

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | <named condition> | <observable signal — branches per week / disk usage / user-reported friction> | <one-line rationale> |
| T2 | <...> | <...> | <...> |

**Today's status**: <which triggers fired, which didn't>.

## Phase 1 — <what shipped in this commit> (SHIPPED)

| # | Title | Files | Status |
|---|---|---|---|
| P1.1 | <slice title> | <NEW path or EDIT existing> | **shipped** |
| P1.2 | <...> | <...> | **shipped** |

**Behavior guarantee**: <what should and shouldn't change at runtime today>.

**Why ship now**: <option value rationale>.

## Phase 2 — <what's deferred> (DEFERRED — fires when <trigger>)

| # | Title | Files | Trigger |
|---|---|---|---|
| P2.1 | <slice> | <files> | <T1/T2/...> |
| P2.2 | <...> | <...> | <...> |

**Trigger**: <when this phase fires>.

**Why not now**: <opportunity cost / no benefit yet>.

## Phase 3 / 4 / N — <if applicable>

<Same shape. Each phase is gated on one or more triggers.>

## Anti-goals (explicit non-goals)

- ❌ "<thing we'll NOT do>." <One-line why.>
- ❌ "<...>" <...>

## Open questions (to revisit at trigger time)

- **Q1**: <question + why it's deferred>
- **Q2**: <...>

## Cost shape change (if applicable)

- **Today**: <current cost shape>.
- **Phase N**: <new cost shape + estimated $-impact>.

## Decision log

- **YYYY-MM-DD**: <decision + rationale>.

## Retrospective (filled at first trigger fire)

*To be filled when Phase 2+ fires. Capture:*
- *Which trigger actually fired (T1/T2/...)?*
- *Was the Phase 1 abstraction / decision sufficient, or did we discover gaps?*
- *Time-to-execution vs. estimate.*
- *Lessons absorbed back to KB / MEMORY.md.*

## Composes with

- `KB § PATTERNS/common/<related-pattern>.md` — <relationship>.
- <other roadmaps>.

## File trail

- <new file 1>
- <new file 2>
- This doc.
