# Code recurrence baseline — ratified-canonical layer for code findings

**What it is.** A durable ratification mechanism for code recurrence findings. Sister of [`vector-baseline`](vector-baseline.md) (which ratifies `owns_kb` validation findings); same shape, applied to `code_recurrence_promote.scan()` output instead. Born 2026-05-26 (post-close batch on automation-orchestration-2026-05).

**The principle.** Same as vector-baseline: *snapshot what's been reviewed → subsequent runs report only deltas → signal stays sharp.* Reasoning-driven, not auto-tuning.

## Why this exists

Without ratification, `code_recurrence_promote.scan()` re-surfaces the same pairs every run. Some are real (will be absorbed Q3); some are intentional (seed↔per-product wrapper); some are false-positives that are fine. Without a "yes I've seen these, move on" mechanism the architect re-evaluates the same N pairs forever, drowning out NEW recurrence.

**Use case**:
1. `code_recurrence_promote.scan(threshold=0.7)` → 8 pairs.
2. Architect reviews: 3 will-be-absorbed-Q3, 2 are intentional (seed↔wrapper), 3 are noise.
3. `code_ratify("Q3 absorption plan covers 3; 2 intentional seed↔wrapper; 3 are noise")` → snapshot.
4. Next session: `code_baseline_diff()` shows only NEW pairs (vs. the 8 baselined).

## What's shipped

| MCP tool | Purpose |
|---|---|
| `noctus.dev.code_ratify(reason, matches?, threshold?)` | Snapshot current code recurrence matches as approved-canonical. `reason` REQUIRED. Optional `matches` for curated subset; `threshold` controls scan scope when matches=None. |
| `noctus.dev.code_baseline_diff(against?, threshold?)` | Diff current matches vs. baseline. Returns `new_matches` + `resolved_matches` + `code_corpus_drifted`. |
| `noctus.dev.code_baseline_list()` | Chronological summary of every ratified baseline. |

CLI: `--code-ratify <reason>` · `--code-baseline-diff [<id>]` · `--code-baseline-list` · `--check-code-recurrence-drift`.

## Storage

`project-history/code-baselines/<YYYY-MM-DD>-<short_code_corpus_sha>.json`. Each file:

```json
{
  "ratified_at": "2026-05-26T...",
  "reason": "Q3 absorption plan covers 3; 2 intentional seed↔wrapper; 3 are noise",
  "code_corpus_sha": "a3f8c19b...",
  "threshold": 0.7,
  "pair_count": 8,
  "matches": [
    { "score": 0.91, "band": "strong",
      "a": {"path": "...", "symbol_name": "...", "kind": "function"},
      "b": {"path": "...", "symbol_name": "...", "kind": "function"} },
    ...
  ]
}
```

**Durable, committed, append-only** — never overwrite a baseline. Same-day same-corpus second ratification gets a `-<N>` suffix.

## Corpus sha (what it captures)

The corpus_sha hashes the code-embeddings cache contents (sorted `(path, symbol_name, source_sha)` tuples). Identifies "which code state was ratified" — different cache state ⇒ different ratification target.

When `code_corpus_drifted: True` in a diff, `resolved_matches` may be artifacts of changed code (functions renamed/deleted), not real fixes. Surface but don't claim victory.

## Keeper

`check_code_recurrence_drift` (severity `warning`) fires when:
- **No baseline exists** AND current scan has pairs → suggests ratification.
- **Diff vs latest** > `_DRIFT_THRESHOLD` (default 3 — smaller than kb-baseline's 5 because code signal is sparser).
- **Code corpus drifted** since baseline.

## The 4-tier signal stack (composed with sister patterns)

```
                CANONICAL TRUTH (the source code on disk)
                              ↓ chunked + embedded
                  RAW VECTOR SIGNAL  (code_embeddings cache)
                              ↓ scan() over anchors
                  RAW RECURRENCE SIGNAL  (code_recurrence_promote.scan)
                              ↓  ratification (code_ratify)
                  RATIFIED BASELINE  (project-history/code-baselines/)
                              ↓  comparison (code_baseline_diff)
                  DRIFT SIGNAL (only NEW pairs since baseline)
```

`code_recurrence_promote.promote()` writes pairs to `auto-improvement.ndjson` — that's the IMPROVEMENT pipeline. `code_ratify()` is the SIGNAL-FILTERING pipeline. The two are orthogonal: ratify hides noise from `diff`; promote pushes signal toward codification regardless of ratification status.

## Composes with

- [`code-embeddings`](code-embeddings.md) — corpus source.
- [`vector-baseline`](vector-baseline.md) — sister pattern (owns_kb instead of code recurrence).
- [`vector-calibration`](vector-calibration.md) — threshold-reasoning duo: calibration reasons about THRESHOLDS, baselines reason about FINDINGS.
- `code_recurrence_promote` — the scan source this baselines.

## Anti-patterns (do NOT do)

- **DON'T auto-ratify on a schedule.** Ratification IS human review.
- **DON'T overwrite a baseline.** Append-only — each ratification is a durable decision.
- **DON'T promote to severity `high`.** Advisory layer; ratification is opt-in.
- **DON'T mix promote and ratify intent.** They serve different purposes: promote pushes pairs toward codification (s1→s4 pipeline); ratify hides reviewed pairs from the discovery diff.
