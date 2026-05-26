# Engineer-output linter — mechanize the two-leg footer rule

**What it is.** A mechanical check that a dispatched-engineer's return text carries the mandatory `drift-found:` + `scoped-improvement:` two-leg footer. Replaces social-contract enforcement ("architect eyeballs the return") with deterministic detection.

**Status**: v4.0-beta follow-up (F1 from `automation-orchestration-followup-2026-06.md`).

## The rule it enforces

Per `KB § CONTEXT/PATTERNS/common/scoped-auto-improvement.md`, every dispatched engineer's return text MUST carry:

```
drift-found:
  - <leftover OUTSIDE the slice brief; surfaced not resolved>
  - ...

scoped-improvement:
  - <slip / improvement IN-slice; applied if cheap, surfaced if expanded scope>
  - ...
```

Both sections required. Both must be non-empty OR carry a sentinel (`none`, `n/a`, `nothing`). Anything else is a compliance gap.

## What `engineer_output_lint(text)` returns

```python
{
  "ok": bool,                  # True iff both legs present + non-empty (or sentinel)
  "missing": list[str],        # section headers absent entirely
  "empty": list[str],          # section present but no body + no sentinel
  "warnings": list[str],       # format-drift hints (not blocking)
}
```

## Tolerances

- **Case insensitive**: `Drift-Found:` / `DRIFT-FOUND:` / `drift-found:` all match.
- **Bold wrapping**: `**drift-found:**` matches.
- **Sentinels accepted as "intentional empty"**: `none`, `n/a`, `(none)`, `no drift`, `no drift found`, `no improvements`, `nothing`.
- **Format-drift WARNING (not blocking)**: text contains a `Co-Authored-By` trailer but no footer — likely a commit message instead of an engineer return.

## When to use

- **Architect integration step**: before merging an engineer's branch, paste the return text into `noctus.dev.engineer_output_lint` → confirm compliance.
- **Pre-commit hook leg** (FUTURE): when a dispatched engineer commits, validate their commit message contains the footer (sibling rule applied to commits).

## Why it stays warning-severity (when wired to a keeper)

The two-leg footer is a SOCIAL contract turned mechanical. False positives are possible (a brief that legitimately produced no drift + no improvements should still have sentinel-acknowledged sections; sentinel detection covers the common case). Severity stays advisory because the linter is the floor, not the ceiling — architect review remains the final check.

## Anti-patterns

- **DON'T** demand semantic richness in the sentinel path. `none` is a valid answer. Forcing prose where there's nothing to say creates worse-than-noise content.
- **DON'T** wire to a hard blocking gate. Composition keeper (`check_dispatched_engineer_returns`?) is a future evolution but currently advisory.

## Composes with

- [`scoped-auto-improvement`](scoped-auto-improvement.md) — the rule this enforces.
- [`drift-fix-on-contact`](drift-fix-on-contact.md) — the `drift-found:` leg surfaces what fix-on-contact addresses or escalates.
- `engineer_brief_compose` (MCP tool) — authors the brief that mentions the requirement; this lints the return.
