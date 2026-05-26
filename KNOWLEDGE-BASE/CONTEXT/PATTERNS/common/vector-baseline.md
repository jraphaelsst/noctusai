# Vector baseline — ratified-canonical layer (signal-vs-noise differentiator)

**What it is.** A durable ratification mechanism for vector-derived findings. Specifically: snapshot the `kb_validate_owns_kb` output at a reviewed point in time, then surface only NEW drift on subsequent runs instead of re-showing previously-reviewed cases. Born 2026-05-26 (W2-E6 of the automation-orchestration-2026-05 roadmap).

**Sister pattern.** Composes with [`vector-calibration`](vector-calibration.md): that one reasons about **thresholds** (numbers that need tuning); THIS one reasons about **specific findings** (cases reviewed). Both are reasoning-driven, not auto-tuning. User mandate (W2-E7): *"evaluate canonical truth and evaluate if the signal makes sense or not."*

## The problem this solves

Raw `kb_validate_owns_kb()` returns N findings every run — some real (fix), some noise (false positives that are fine). Without ratification:

1. Every session re-surfaces ALL findings, even ones already reviewed.
2. The 2 real fixes get drowned in 5 unchanged false positives.
3. New drift (a real signal!) hides in the same haystack as the chronically-flagged noise.

**The fix**: ratify the current findings as approved-canonical. Subsequent diffs show only DELTA — what changed since approval. Signal sharpens; noise is opted-out per case, not per threshold.

## What's shipped

| MCP tool | Purpose |
|---|---|
| `noctus.dev.kb_ratify(reason, findings?)` | Snapshot current findings as approved canonical. `reason` REQUIRED. Optional `findings` lets you ratify a curated subset. |
| `noctus.dev.kb_baseline_diff(against?)` | Diff current validation vs. baseline. Returns `new_findings` + `resolved_findings` + `kb_corpus_drifted`. Default: latest baseline. |
| `noctus.dev.kb_baseline_list()` | Chronological summary of all ratified baselines. |

CLI: `--kb-ratify <reason>` · `--kb-baseline-diff [<id>]` · `--kb-baseline-list` · `--check-kb-semantic-drift`.

## Storage

Baselines live in `project-history/kb-baselines/` as JSON:

```
project-history/kb-baselines/
  2026-05-26-a3f8c19b.json
  2026-06-12-b7d2e0a4.json
  ...
```

**Filename**: `YYYY-MM-DD-<short_corpus_sha>.json`. The corpus_sha encodes "which KB state was ratified" — different corpus ⇒ different filename even on the same day.

**Each file**:

```json
{
  "ratified_at": "2026-05-26T15:42:18+00:00",
  "reason": "Reviewed 3 high-drift cases; 2 are false-positive (KB structure intentional), 1 is real (moved to backend-engineer)",
  "kb_corpus_sha": "a3f8c19b87...",
  "finding_count": 3,
  "findings": [
    { "path": "CONTEXT/PATTERNS/...", "current_owner": "...", "suggested_owner": "...", "current_score": 0.72, "suggested_score": 0.74, "drift": -0.02 },
    ...
  ]
}
```

**Durable**: committed to git. Diff-able. Reviewable. Each new ratification creates a new file (history preserved — append-only ledger of decisions).

## The 3-tier signal stack

```
                CANONICAL TRUTH (the KB itself, on disk)
                              ↓
                  RAW VECTOR SIGNAL  (kb_validate_owns_kb)
                              ↓  ratification (kb_ratify)
                  RATIFIED BASELINE  (snapshot in project-history/kb-baselines/)
                              ↓  comparison (kb_baseline_diff)
                  DRIFT SIGNAL (only NEW findings since baseline)
```

The keeper `check_kb_semantic_drift` fires on the **drift signal**, not the raw signal — once ratified, only deltas count.

## Workflow

```bash
# 1. See raw findings:
noc-cli --kb-search '...'    # or use kb_validate_owns_kb directly via MCP
# → 5 findings surfaced

# 2. Architect reviews: 3 real, 2 false-positive. Fix the 3.
# (edits done; commit)

# 3. Refresh embeddings, re-validate:
noc-cli --refresh-kb-embeddings
# kb_validate_owns_kb → 2 findings (the false positives) — already known.

# 4. Ratify the current state:
noc-cli --kb-ratify "Reviewed: 3 mis-owns fixed (commit abc123); 2 remaining are FP — intentional KB structure where vector-centroid disagrees with manual ownership."

# 5. Future session re-runs validation:
# kb_validate_owns_kb → 2 findings (same FPs) + 1 NEW finding (drift!)
noc-cli --kb-baseline-diff
# → new_findings: [the 1 NEW one], resolved: [], unchanged: 2
# Signal sharpened: only the NEW case demands review.
```

## Keeper: check_kb_semantic_drift

Fires (severity `warning`) when:

- **No baseline exists** AND current validation has findings → suggests ratification.
- **Baseline exists** AND new_findings exceeds `_DRIFT_THRESHOLD` (default 5) → surfaces drift.
- **KB corpus shifted** since baseline → resolved_findings may be artifacts; flag for re-ratification consideration.

Severity stays `warning` because ratification is **human-reasoning, not auto-tuning** — the keeper surfaces; the architect decides.

## Composes with

- [`kb-vector-search`](kb-vector-search.md) — the source of the raw signal (`kb_validate_owns_kb`).
- [`vector-calibration`](vector-calibration.md) — sister reasoning tool for thresholds. Use `vector_calibration_decide` to log a threshold change with reasoning; use `kb_ratify` to log a findings-set as approved.
- [`scoped-auto-improvement`](scoped-auto-improvement.md) — drift findings that get repeated review can be logged as auto-improvement entries with `s2-memory` status.
- [`roadmap-tracking`](roadmap-tracking.md) — this slice (W2-E6) lives in `project-history/roadmaps/automation-orchestration-2026-05.md`.

## Anti-patterns (do NOT do)

- **DON'T auto-ratify on a schedule.** The whole point is human review. A cron that auto-baselines every drift defeats the signal-vs-noise differentiator.
- **DON'T overwrite a baseline.** Each ratification is a durable decision; if a new state is approved, it gets a NEW file. History preserved.
- **DON'T promote to severity `high`.** Ratification is opt-in; absence of baseline shouldn't block commits.
- **DON'T treat resolved_findings as automatically-fixed.** When `kb_corpus_drifted: True`, those might be artifacts of changed KB structure, not real fixes. Verify before claiming victory.

## Deferred next-slices

| Future tool | Status | What it does |
|---|---|---|
| `code_baseline` | sketch | Same pattern, applied to `code_embeddings` cross-product recurrence findings — ratify "yes these N similar helpers ARE the duplication; not absorbed yet, planned for Q3" so subsequent runs don't re-flag them. |
| `kb_ratify_partial` | sketch | Ratify SOME findings of a run while leaving others as "still open" — currently expressible by passing `findings=[subset]` but could ship a curated UI. |
| Auto-archive of stale baselines | sketch | When N+ newer baselines exist and the corpus has fully shifted, archive ancient baselines to `closed/`. |
