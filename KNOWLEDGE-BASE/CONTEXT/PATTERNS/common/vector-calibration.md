# Vector calibration — reasoning-driven, NOT threshold-blind

**The principle.** The vector system has tunable parameters (similarity thresholds, top-K, chunk sizes, model choice). **Calibrating them is a reasoning task, not an auto-tuning task.** Codified 2026-05-26 (W2-E7) per user mandate:

> *"You are to evaluate when we have signals from the numbers. Evaluate canonical truth and evaluate if the signal makes sense or not. You are to do the reasoning, not only accept blindly what numbers tells us, we gotta understand why, where it came from."*

This module is an **observatory + reasoner**, not a knob-turner. It surfaces hypotheses; the architect evaluates against context the tool can't see + makes the call.

## Why reasoning, not auto-tuning

Vector signals are **lossy proxies for truth**. A high similarity score means *the chunks look alike to the embedding model*, NOT that they're semantically equivalent in the way the human / methodology defines equivalence. Conversely, a low score doesn't mean "unrelated" — the model may not have been trained on the relevant concept.

Auto-tuning over signals optimizes for *what the embedding model thinks*, which can systematically diverge from canonical truth (the `owns_kb` declarations, the manual codification decisions, the human's domain-specific definition of "similar enough"). The right approach is:

1. **Observe**: log signals across sessions to see distributions + trends.
2. **Reason**: cross-reference signals against canonical truth + surface hypotheses for WHY a signal looks the way it does.
3. **Decide**: the architect makes the call with explicit reasoning. The decision lands in a durable ledger with rationale.
4. **Validate**: after a calibration call, observe whether the change actually improved outcomes (the methodology codification pipeline applied to vector tuning itself).

## Architecture (3 ledgers + 2 tools)

```
                                  CANONICAL TRUTH
                              (owns_kb / auto-improvement
                              status progression / human codification
                              decisions / corpus content)
                                       ↑
                                       │
project-history/vector-signals.ndjson  │
       ↑                               │
       │  (every tool call             │  (cross-reference)
       │   logs to it)                 │
                                       │
       ↓                               ↓
LIVE TOOLS ──────→ vector_calibration_analyze ──────→ REASONED REPORT
(kb_search / radar /                                  (score distribution +
 neighbors / etc.)                                     hypotheses + alignment
                                                       + recommended next step)
                                                       │
                                                       ↓
                                                ARCHITECT REVIEWS
                                                + makes the call
                                                       │
                                                       ↓
                          vector_calibration_decide(reasoning=...)
                                                       │
                                                       ↓
                          project-history/vector-calibration.ndjson
                                          (decision log w/ rationale)
```

## Tools shipped (4 MCP)

| Tool | Purpose |
|---|---|
| `noctus.dev.vector_signal_log(signal_type, params, result, context?)` | Observatory: append a signal observation. Called from vector tools after a query. |
| `noctus.dev.vector_calibration_analyze(signal_type?, since?)` | Reasoner: read signals + canonical refs, produce structured analysis with reasoning lines. |
| `noctus.dev.vector_calibration_decide(signal_type, parameter, old, new, reasoning, evidence?)` | Decision: record a calibration call with REQUIRED reasoning. |
| `noctus.dev.vector_calibration_history(signal_type?)` | Read the decisions log — see WHY past calls were made. |

## Signal types

`kb_search` · `kb_neighbors` · `kb_similar` · `kb_validate_owns_kb` · `codification_radar` · `code_search` · `code_recurrence` (future when code-embeddings ships).

## Known parameters

`similarity_threshold` · `top_k` · `min_score` · `min_cluster_size` · `max_chunk_chars` · `chunking_strategy` · `embedding_model`.

Extending the set requires adding to `KNOWN_PARAMS` in `vector_calibration.py` (the validation gate ensures typos don't silently rot the decision log).

## Schemas (the durable ledgers)

```
project-history/vector-signals.ndjson — one line per tool invocation
{
  "ts":          "2026-05-26T...",
  "signal_type": "codification_radar",
  "params":      {"threshold": 0.75, "limit": 200},
  "result":      {"clusters": [...], "total_entries": 12},  // or summary
  "context":     {"session": "...", "user_action": "..."}    // optional
}

project-history/vector-calibration.ndjson — one line per architect decision
{
  "ts":           "2026-05-26T...",
  "signal_type":  "codification_radar",
  "parameter":    "similarity_threshold",
  "old_value":    0.75,
  "new_value":    0.80,
  "reasoning":    "20 signal observations show mean=0.81 — current 0.75 is too inclusive, yielding low-precision clusters. Raising to 0.80 cuts the noise band by 60% based on observed Q25.",
  "evidence":     {"analyze_run_ts": "...", "signal_count": 20}
}
```

## How the reasoner works (the analysis output)

For a given `signal_type`, `analyze()` produces:

- **score_distribution** — count, mean, median, stdev, Q25/Q75/Q90, 5-bin histogram. The shape of observed scores.
- **current_threshold_observed** — last-used threshold (extracted from params).
- **canonical_alignment** — alignment of vector signals vs canonical truth (e.g., for `kb_validate_owns_kb`: did the suggested owner re-assignment match a subsequent human change to owns_kb?). v1 = framework + TODO; per-signal-type analyzers land as follow-ups.
- **reasoning** — discrete reasoning lines (NOT a single recommendation). Each line is a hypothesis or observation the architect evaluates. Example: *"Threshold (0.75) is BELOW the 25th percentile (0.81) — most observations pass. ⇒ Likely yielding low-precision hits. Consider raising toward Q75 (0.88). WHY: a threshold that doesn't discriminate isn't a threshold; it's the floor."*
- **recommended_next_step** — explicit advisory framing: architect reviews + makes the call.

## Reasoning lines: example outputs

These are *templates* the analyzer fills with real numbers. Each is shaped to PROMPT thinking, not produce conclusions:

- **Threshold below Q25**: "Most observations pass the threshold ⇒ likely low-precision. Consider raising. WHY: a threshold that doesn't discriminate isn't a threshold; it's the floor."
- **Threshold above Q75**: "Most observations fail ⇒ likely missing useful hits. Consider lowering. WHY: a threshold the data rarely crosses is tuned for a different distribution than what you have."
- **60%+ in lowest bin (0.0-0.2)**: "Weakly-related results dominate. Hypothesis: corpus doesn't match query intent (re-chunk OR wrong domain)."
- **50%+ in highest bin (0.8-1.0)**: "Extremely confident matches dominate. Hypothesis: either querying for exact known content (grep would work — low vector signal value) OR corpus has near-duplicates. Investigate."
- **Canonical alignment <70%**: "Vector signals frequently diverge from canonical decisions; threshold/chunking likely off. Manual review of disagreement cases recommended before tuning."

## Anti-patterns

- **Auto-tune from numbers** — let a script bump thresholds based on percentiles without architect reasoning. Loses the "evaluate canonical truth" step. The user mandate forbids this.
- **Log decisions without reasoning** — `log_decision()` REQUIRES the `reasoning` field; pass-empty-string rejected. Future sessions need to know WHY.
- **Skip the observation phase** — pre-tune a parameter without first accumulating ≥30 signals. Statistical reasoning over <10 observations is noise.
- **Trust similarity scores in absolute terms** — a 0.8 between two chunks means "the embedding model sees them as 80% aligned in its learned space," not "these are 80% the same in the way you mean." Always cross-reference against canonical truth.
- **Tune without rollback plan** — a calibration call shifts behavior across all downstream signals. Record the old_value so reverting is one-line.

## Composes with

[[scoped-auto-improvement]] (the codification pipeline this tool calibrates a sensor for) · [[kb-vector-search]] (the working cache whose signals are observed) · [[methodology-codification-pipeline]] (the s1→s4 progression that defines canonical truth for codification) · [[agent-context-architecture]] (the `owns_kb` declarations that define canonical truth for ownership signals) · [[claude-md-router-discipline]] (the markdown-as-canonical sibling principle — vectors are advisory, markdown is truth).
