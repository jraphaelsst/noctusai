# Doc-to-code drift — surface KB patterns whose code referent drifted

**What it is.** A sensor that walks KB pattern docs, extracts referenced code symbols (backtick-quoted `check_*`, `noctus.dev.*`, `*.py`), and scores doc↔code semantic similarity. Flags when the doc no longer describes what the code does. Born v4.0-beta follow-up (F4).

## Why

KB pattern docs name implementations: "`check_six_way_sync` enforces ...". The link looks stable in text, but the SEMANTICS of either side can drift independently:

- Code refactors → function does something different from what the doc says.
- Doc revisions → emphasis shifts away from the original code's intent.

Line-diffs don't catch this — only one side changed at a time. **Vector distance over time IS the signal.**

## What it surfaces

```python
{
  "ok": True,
  "threshold": 0.5,
  "scanned_docs": N,
  "scanned_referents": M,
  "drift_findings": [
    {
      "kb_path": "CONTEXT/PATTERNS/common/foo.md",
      "referent": "check_foo_bar",
      "code_path": "mcp/.../compliance.py" | None,
      "score": float | None,
      "severity": "below_threshold" | "referent_not_found",
    },
    ...
  ],
}
```

## Two severity classes

| Severity | What it means | Action |
|---|---|---|
| `referent_not_found` | Doc names a symbol that doesn't exist in the code corpus | **HARD drift** — either rename in doc, or the function was deleted. |
| `below_threshold` | Symbol exists; doc-vs-code cosine < threshold | **SOFT drift** — they may have diverged in intent. Review. |

## Threshold

Default **0.5** — empirical lower bound for doc-vs-code similarity (the prose registers differ; perfect match is never reached). The SIGNAL is in the DELTA over runs: same pair, score dropping from 0.65 → 0.45 = drift in progress.

## Status — advisory sensor, not a keeper (yet)

Surfaces drift; doesn't block commits. False-positive rate is real (a small doc revision can dip the score below 0.5 with no actual drift). Promotion to keeper requires:
- Per-pair score history (track over time, not single-snapshot).
- Calibrated threshold per doc class.

That's a future iteration. Current shape: on-demand scan; architect reviews.

## When to use

- After a refactor: "did I break any doc?" Run scan; check findings.
- Periodic sweep: monthly drift audit.
- Before a doc-set release (e.g. v4.0 → v4.1): drift-clean before tagging.

## Composes with

- [`kb-vector-search`](kb-vector-search.md) — the KB embedding source.
- [`code-embeddings`](code-embeddings.md) — the code embedding source.
- [`eight-way-sync`](eight-way-sync.md) — doc-to-code drift is ONE leg of "methodology surfaces stay aligned" applied across the doc↔code boundary specifically.
