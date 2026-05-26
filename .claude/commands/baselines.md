---
description: Show kb + code recurrence baselines and current diff vs. latest ratification. Surfaces what's NEW since last review.
---

# /baselines — ratified-canonical layer overview

You are running the **baselines** protocol. The user invoked `/baselines $ARGUMENTS`.

The kb_baseline + code_baseline pair is the signal-vs-noise differentiator for vector findings: every run re-surfaces the same false positives unless they've been ratified. This command shows current baseline state + the diff against current findings, so the architect knows what's NEW since last review.

## Protocol

1. **List baselines** — `noctus.dev.kb_baseline_list` + `noctus.dev.code_baseline_list`. Report id / timestamp / reason / count for each.

2. **Diff against latest** — `noctus.dev.kb_baseline_diff` + `noctus.dev.code_baseline_diff`. Report:
   - `new_findings` (NEW drift to review)
   - `resolved_findings` (gone since baseline — verify they're real fixes, not corpus drift artifacts)
   - `unchanged_count` (still flagged, but already-reviewed → ignore)
   - `kb_corpus_drifted` / `code_corpus_drifted` (True = corpus changed; resolved may be artifacts)

3. **If `--ratify <reason>` arg** — call `noctus.dev.kb_ratify(reason)` AND/OR `code_ratify(reason)` to snapshot current findings as approved. Persists durable JSON to `project-history/{kb,code}-baselines/`.

## Output shape

```
┌─ KB baselines ────────────────────────────────────────┐
│  N=<count>  latest=<id>  on <date>                    │
│  Reason: "<the human-readable rationale>"              │
└───────────────────────────────────────────────────────┘
Diff vs latest:
  new:        <N findings>         ← REVIEW these
  resolved:   <N findings>
  unchanged:  <N> (baselined; ignore)
  corpus_drifted: <true|false>     ← if true, resolved may be artifacts

┌─ Code recurrence baselines ───────────────────────────┐
│  N=<count>  latest=<id>  on <date>                    │
│  Reason: "<...>"                                       │
└───────────────────────────────────────────────────────┘
Diff: <same shape>
```

## When to use

- Start of session: see what's NEW vs reviewed.
- Before claiming "no recurrence" — diff shows it.
- Before authoring a new helper: check if `code_baseline_diff` already surfaces an unbaselined duplicate.
- After absorbing recurrence to seed: re-ratify so the absorption is "approved" and won't re-surface.

## Composes with

- `KB § CONTEXT/PATTERNS/common/vector-baseline.md` (the KB pattern)
- `KB § CONTEXT/PATTERNS/common/code-recurrence-baseline.md` (sister pattern)
- `/codification-radar` — radar surfaces s1→s3 candidates; baseline surfaces ratified-reviewed findings. Read together for full signal picture.
