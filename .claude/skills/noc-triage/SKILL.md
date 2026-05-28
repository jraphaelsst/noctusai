---
name: noc-triage
description: Use at every divergence / discovery / surfaced-pattern decision point — triggers "should we accept this?", "what about X?", "divergence found", "F/R/A", "accept-with-rationale", "triage this", "this came up". Every finding lands on [F]ormalize / [R]eject / [A]ccept with paperwork — accept without rationale is silent-error shape.
version: 1.0.0
---

# noc-triage — accept-with-rationale at decision time

🔴 **The trap:** a peer-product / sibling / discovery surfaces a pattern. Reflexive answer: "ok, we'll keep that one for later." That answer evaporates the moment the folder/branch/note is deleted. "Accept" is a real landing ONLY with paperwork — otherwise the recurrence reincarnates next quarter.

## Workflow

1. **Count the recurrence FIRST** — before triaging the new sighting, check N.
   - `noctus.dev.scan_recurrence` for code/function/test/migration patterns.
   - `noctus.dev.auto_improvement_query` (or `kb_recurrence_radar consult=true`) for prose/methodology patterns.
   - **N=1** → triage = note in catalog · **N=2** → triage = architect-eyes · **N=3+** → triage is overridden — MUST formalize. → `KB § PATTERNS/architect/project-execution.md` (DRY recurrence rule).

2. **Classify [F]/[R]/[A] with one-line rationale:**
   - **[F]ormalize** — extract to seed / shared-lib / KB / keeper. Use when: cross-cutting, generalizes, or N≥3 forces this regardless of preference. Rationale = the abstraction's name + its single canonical home.
   - **[R]eject** — strip the customization, conform to the seed default. Use when: the divergence is coincidence, not principle; the seed default is the canonical answer. Rationale = why the seed already handled this.
   - **[A]ccept** — keep the local divergence as-is. Use when: genuinely product-specific (not generalizable), or a deliberate variance with a stated reason. **Rationale REQUIRED** + catalog row.

3. **Write the paperwork — the row survives folder deletion.**
   - Methodology / cross-cutting surface → `noctus.dev.codify_log` entry (s1-emergent or s2-memory) with `target=<the-pattern>` + `description=<rationale>` + `source_ref=<session-id>`. → `KB § PATTERNS/common/methodology-codification-pipeline.md`.
   - Product-local accept → row in the product's `02-LANDSCAPE.md` "Accepted divergences" section (or a `NOC-REMEDIATE[accept]` marker at the divergence site with the rationale inline).
   - Vendored skill / external pattern → row in `KB § PATTERNS/common/accept-with-rationale.md` vendored-skill register.

4. **Replication-to-seed symmetry sanity check** — before finalizing [A], re-read the rationale: does it contain "per-product" or "across N" or "mount everywhere"? Those phrases ARE the slip signal — the right count for cross-cutting concerns is ZERO. If the rationale leaks that language, the verdict should have been [F]. → `KB § PATTERNS/architect/project-execution.md` (replication-to-seed symmetry).

5. **Surface the verdict in-session** — the user sees the F/R/A line + rationale before the commit lands. Verdicts going silent into a catalog row = silent decision-making shape.

## Guardrails
- "Accept without paperwork" = silent-error shape (mirrors the no-silent-errors rule). NEVER ship an accept-verdict that doesn't land in catalog/memory/KB/marker the same commit.
- N=3 forces [F] regardless of preference — the 4th instance is structurally forbidden. The triage at N=3 isn't "should we?", it's "where does this formalize?".
- For verdicts you can't decide alone (cross-product impact, methodology shift, contract change), the verdict is [SURFACE] not [A] — block on tech-lead approval via `noctus.dev.file_proposal kind=surface` → `KB § PATTERNS/common/dispatch-with-project-and-notes.md`.
- The triage runs AT decision time (during the work), not at wrap — wrapping a session with pending un-triaged divergences = pre-condition the `noc-wrap-up` survey flags as unresolved.

## Depth
`KB § PATTERNS/common/accept-with-rationale.md` (the canonical home) · `KB § PATTERNS/architect/project-execution.md` (DRY recurrence rule + replication-to-seed symmetry) · `KB § PATTERNS/common/methodology-codification-pipeline.md` (s1→s2→s3→s4 progression) · `KB § PATTERNS/common/remediation-markers.md` (the in-code form).
