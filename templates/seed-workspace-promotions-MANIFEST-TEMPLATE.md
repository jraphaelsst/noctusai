---
slug: <addition-slug>
origin: <workspace-relative-path>          # OR newline list of paths
intended_noc_destination: <noc-relative-path>
layer_rationale: |
  Why this destination — invoke the seed-lib 6-layer model
  (KB § PATTERNS/seed-lib-layout.md) when the addition is a lib/seed
  primitive. State the layer (primitives / config / testing /
  integrations / domain / api) and why it sits there.
seed_first_analysis: |
  Q1 — Cross-product candidate? <YES/NO + which products benefit>
  Q2 — Variance across products? <none / what varies>
  Q3 — Existing seed coverage? <none / what already exists>
  Q4 — Fake+Real+factory shipped? <yes — Fake ships alongside / N/A pure-logic>
  Q5 — Migration cost into noc? <low/med/high + why>
  Q6 — Premature-lift risk? <low/med/high + the N= recurrence that clears the bar>
  readiness: N=<count>          # consumer count that justifies the lift
dependencies_on_other_additions: []        # OR newline list of other slugs
promoted_on: not-yet                        # auto-rewritten to ISO date on promotion
---

## Why this addition exists

<Prose: what problem this solves, why it was built in the workspace, why it
belongs in noc rather than staying product-local.>

## Integration notes for noc-side

<Prose: what to wire up, what to test, what migrations to run, which
existing consumers to adapt. Written so a future noc agent can promote +
integrate this WITHOUT the originating workspace being available.>
