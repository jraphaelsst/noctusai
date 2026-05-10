# containerization-backlog-closure — Orchestration Findings

> Per `KB § 01-PHILOSOPHY.md § Knowledge tracking` + `KB § PATTERNS/branching-and-merging.md §17`. Append-as-you-go during dispatch; synthesized at project close.

---

## Errors encountered

_(none yet — Wave 1 dispatch pending)_

---

## Mistakes / slips

_(none yet)_

---

## Lessons learned (durable rules)

- **(2026-05-10, orchestrator at scaffold time)** Three-way-syncing the methodology BEFORE dispatching teams under it is the right ordering. The teams operate under the rule that they're supposed to be exemplifying; if the rule isn't documented when they execute, the methodology amendment is post-hoc and weaker. Capture-first-execute-second.

---

## Interesting findings (surprises, discoveries)

_(none yet)_

---

## Knowledge pieces (durable patterns)

- **Pause-on-dependency event log shape.** Each pause-and-resume gets a row here:
  - **Event:** _(none yet)_
  - **Surfaced by:** engineer-name
  - **Gap:** what was missing
  - **Dependency team dispatched:** team-name + brief slug
  - **Resume signal:** when the original chunk re-dispatched
  - **Resumed brief delta:** what changed in the re-dispatch vs. the original

---

## Wave-by-wave speed-gain log (per `feedback_TEMP_methodology_validation_in_progress.md`)

| Wave | Engineers | Wall-clock parallel | Estimated serial | Speed gain | Tokens | Notes |
|---|---|---|---|---|---|---|
| 1 | 6 | _pending_ | _pending_ | _pending_ | _pending_ | T1-T6: backend Dockerfile / frontend / VITE args / postgres / registry / healthcheck |
| 2 | 2 | _pending_ | _pending_ | _pending_ | _pending_ | T7-T8: dev override / prod overlay |
| 3 | 1 | _pending_ | _pending_ | _pending_ | _pending_ | T9: CI workflow (matrix + registry push + scan) |
| **Cumulative** | **9** | **pending** | **pending** | **pending** | **pending** | First orchestration under §18 wave-dispatch methodology |

This is the first orchestration under the new §18 methodology. Track diligently for the validation log.
