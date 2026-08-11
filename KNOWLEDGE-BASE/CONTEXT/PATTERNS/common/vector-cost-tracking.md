# Vector Cost Tracking

## Summary

Generic platform tool that records OpenAI embedding API usage — tokens +
estimated USD — to a durable NDJSON ledger. Cache modules opt in by calling
`log_refresh_batch(...)` at the end of each refresh run. Provides MCP tools
and CLI flags so users can audit cumulative spend without logging into the
OpenAI dashboard.

## Why it exists

Every embedding API call has a cost. Without instrumentation, cost is invisible:
no per-namespace breakdown, no trend, no budget gate. This pattern provides:
- A committed ledger (`project-history/vector-costs.ndjson`) that survives
  context resets and session changes.
- Per-namespace reporting so "kb-embeddings" vs "code-embeddings" costs are
  attributed separately.
- A lightweight module that any cache layer can opt into with ~5 lines.

## Ledger schema

One NDJSON line per refresh batch:

```json
{
  "ts":                   "2026-05-26T14:32:00.123456+00:00",
  "namespace":            "kb-embeddings",
  "model":                "text-embedding-3-small",
  "provider":             "openai",
  "doc_count":            12,
  "chunk_count":          48,
  "estimated_tokens":     21600,
  "estimated_cost_usd":   0.000432,
  "actual_tokens":        21987,
  "actual_cost_usd":      0.000440,
  "source_ref":           "session:2026-05-26"
}
```

`source_ref` is free-form — typically `"session:YYYY-MM-DD"` or a project slug.

## Real vs. estimated (the ground-truth leg)

`estimated_*` is the `len//4` (or `tiktoken`) heuristic computed BEFORE the call.
`actual_*` is the provider's **reported** `usage.total_tokens` from the API
response — the ground truth. It is captured by
`_embedding_corpus.capture_embedding_usage()` (a context manager) or
`install_capture_sink(acc)` (a begin/restore pair for linear batch loops), which
installs a chaining `UsageSink` on the LLM config so every embed inside the
block accumulates real usage. All 6 embedding call sites pass both: kb, code,
organ, generic `vectorize.embed_text`, and — via
`refresh_markdown_corpus(cost_namespace=...)` — corpus and memory.
`report()` / `total()` sum `actual_*` separately (with `actual_batch_count` for
partial-coverage periods) so you can read **estimate-vs-actual drift** — the
calibration signal for projecting future production cost. Pre-2026-05-29 rows
and the fake provider read back as `null` (fully back-compatible).

## Cost table (USD / 1M tokens)

| Model | Rate | Source |
|---|---|---|
| text-embedding-3-small | $0.02 | OpenAI pricing 2026-05-26 |
| text-embedding-3-large | $0.13 | OpenAI pricing 2026-05-26 |
| text-embedding-ada-002 | $0.10 | OpenAI pricing 2026-05-26 |

**Update cadence**: when OpenAI reprices, update `COST_PER_MILLION_TOKENS` in
`mcp/noctusai/tools/noctus/dev/vector_costs.py` AND this table in the same
commit (doc-code coherence rule).

## Token estimation

`estimate_tokens(text, model)` prefers `tiktoken` (cl100k_base encoding,
exact BPE count). Falls back to `len(text) // 4` when tiktoken is absent.
Both paths record the same schema; the fallback is accurate to ±20% for
English prose.

## API

Module: `mcp/noctusai/tools/noctus/dev/vector_costs.py`

### `log_refresh_batch(...)`

```python
log_refresh_batch(
    namespace="kb-embeddings",  # or "code-embeddings", etc.
    model="text-embedding-3-small",
    doc_count=len(refreshed),
    chunk_count=total_rows,
    estimated_tokens=estimated,
    # cost_estimate_usd=None → computed from cost table
    provider="openai",
    source_ref="session:2026-05-26",
)
```

Returns `{ok, path, row}`. Failures are logged as warnings, never raised
(cost tracking is advisory — never blocks a successful refresh).

### `estimate_tokens(text, model) -> int`

Tiktoken-first, `len // 4` fallback.

### `estimate_cost(tokens, model) -> float`

Table lookup × tokens / 1_000_000. Returns 0.0 for unknown models (warning
logged).

### `report(namespace?, since?, group_by?) -> list[dict]`

Aggregates the ledger by "day" | "week" | "month". Each bucket:
`{period, namespace, doc_count, chunk_count, estimated_tokens,
estimated_cost_usd, batch_count}`.

### `total(namespace?, since?) -> dict`

Quick sum: `{namespace, since, doc_count, chunk_count, estimated_tokens,
estimated_cost_usd, batch_count, first_ts, last_ts}`.

## MCP tools

| Tool | Purpose |
|---|---|
| `noctus.dev.vector_costs_log_batch` | Append a row (called by cache modules) |
| `noctus.dev.vector_costs_report` | Aggregate by period |
| `noctus.dev.vector_costs_total` | Quick total |

## CLI flags

```
python mcp/noctusai/cli.py --vector-costs-report [--namespace kb-embeddings] [--since 2026-05-01] [--group-by day]
python mcp/noctusai/cli.py --vector-costs-total [--namespace kb-embeddings] [--since 2026-05-01]
```

## Opting in (instrumentation recipe)

At the end of a `refresh()` function, AFTER all DB commits:

```python
if chunks_embedded > 0:
    try:
        from tools.noctus.dev import vector_costs as _vc
        _vc.log_refresh_batch(
            namespace="my-embeddings",
            model="text-embedding-3-small",
            doc_count=len(refreshed),
            chunk_count=chunks_embedded,
            estimated_tokens=chunks_embedded * (MAX_CHUNK_CHARS // 4),
            source_ref=f"session:{today}",
        )
    except Exception as _exc:
        logger.warning("vector_costs instrumentation failed: %s", _exc)
```

The try/except wrapper ensures cost tracking never propagates failures back
to the caller. Keep it additive — do not modify the existing refresh logic.

## Opt-in cost attribution from `vectorize.embed_text` (2026-05-26)

The original cost-ledger path required wrapping the `refresh()` call in
each cache module. That covered the BATCH refreshes (kb-embeddings,
code-embeddings) but missed direct `vectorize.embed_text()` callers
(kb_recurrence_radar, codification_radar) — they consumed OpenAI silently.

The fix (codified after the 2026-05-26 verify pass surfaced the gap):
`vectorize.embed_text` now accepts an OPTIONAL `namespace=` kwarg. When
provided, the successful embed logs to `vector-costs.ndjson` via
`log_refresh_batch(namespace, chunk_count=1)`:

```python
# vectorize.py
def embed_text(text: str, namespace: str | None = None) -> dict:
    ...  # do the embed
    if namespace:
        try:
            from . import vector_costs as _vc
            _vc.log_refresh_batch(
                namespace=namespace,                       # caller's attribution
                model=cfg.default_embedding_model,
                doc_count=1,
                chunk_count=1,
                estimated_tokens=max(1, len(text) // 4),
                provider=cfg.default_provider,
                source_ref=None,
            )
        except Exception:  # never block embed on logging failure
            pass
    return result
```

**Caller pattern**:
```python
# kb_recurrence_radar.py
result = vectorize.embed_text(text, namespace="kb_recurrence_radar")

# codification_radar.py
result = embed_text(description, namespace="codification_radar")
```

**Design choices**:
- **Opt-in, not opt-out**: generic callers (prototyping, debugging) don't
  spam the ledger. They get an unlabeled embed; the cost just doesn't show.
- **Per-call, not per-batch**: each `embed_text` produces ONE row. For
  high-volume callers, prefer a batch refresh pattern with one summary row.
- **Failure-tolerant**: logging errors never propagate to the embed result.

## Fold-into-commit — the ledger only ever changes inside a commit (2026-08-11)

The ledger is **committed, not gitignored** (see Constraints). But it is also
written as a *side-effect* of routine work — every embed (tool call) and every
`refresh()` appends a row — so without a discipline it sits **dirty in the
working tree** and gets re-surfaced as "drift" at the next `/contextualize`.
This recurred **5 times**, and ~**7 of every 30 commits** were manual
`chore(cost-log)` cleanups — pure toil. The root has two timings:

| Timing | Who appends | Why it lingered |
|---|---|---|
| **Mid-work** | MCP embed tools / cache `refresh()` during a session | dirty until the next commit happened to include it |
| **Push-time** | the pre-push embedding-cache refreshes (kb/code/corpus/**memory**) | appended **after** the last commit, so it can't be folded into *this* push (refs already negotiated) |

### The first fix, and why it was worse than the problem

The 2026-05-31 answer was symmetric hook legs: pre-commit auto-staged a dirty
ledger, and **pre-push swept the push-time churn into a `chore(cost-log)` commit**.
The tree did stay clean. But a commit created in pre-push **cannot join the push
that created it** — the refs are already negotiated — so it sat local, "ahead by
1", and rode the **next** push. That moved the branch tip, and `test.yml` carries
`concurrency: cancel-in-progress`, so it **cancelled the in-flight CI run for the
sha we actually cared about**. Five CI runs died that way in one session
(2026-08-10); `git log --grep=cost-log` showed **20+** commits of pure churn. The
user reported the friction three times before it was root-caused.

**The lesson is the shape, not the file**: the fix moved the *symptom* (dirty
tracked file) without moving the *cause* (a tracked file being written at a moment
when nothing can commit it). A cleanup step that runs where it cannot clean up
will always displace the mess somewhere less visible — here, into CI scheduling,
which is exactly where nobody was looking for a cost-ledger bug.

### The invariant that actually holds

> **The tracked ledger only ever changes inside a real commit.**

| Leg | Where | What |
|---|---|---|
| **write** | anywhere, any time | `log_refresh_batch()` appends to the **untracked** spool `project-history/.vector-costs-spool.ndjson` (gitignored). An untracked file is not a dirty tracked tree — no drift, no CI trigger, nothing to sweep. |
| **drain** | `scripts/hooks/pre-commit` leg 10c **only** | `--vector-costs-drain-spool` folds the spool into the ledger, then leg 10c `git add`s it. The rows ride along with whatever is being committed. `drain_spool()` is the **sole writer** of `LEDGER_PATH`. |
| **read** | `report()` / `total()` | concatenate **ledger + spool**, so an un-drained row is never missing from a report. Deferring the write must not silently under-report cost. |

Pre-push now creates **no commit at all**. The `NOCTUS_SKIP_COSTLOG_COMMIT`
escape hatch is gone with the block it disabled (removed from `session_end_sweep`
too — a flag nothing reads is dead routing).

Crash-safety: the ledger append is flushed **before** the spool is truncated, so
an interruption can at worst duplicate a row (harmless for telemetry) and can
never lose one. Ordering is write-order; `report()` buckets by `ts`.

**Pinned by** `mcp/noctusai/tests/test_vector_cost_spool.py` — including two
hook-text guards (`test_pre_push_makes_no_cost_log_commit`, and that pre-commit
drains *before* it stages), because re-adding the commit is a one-line edit that
no other suite would catch.

**General rule** (sibling of [[funnel-self-satisfies-preconditions]]): a
git-tracked file that is **machine-appended as a side-effect of routine work**
must be swept into commits *by the tooling*, never left for a human to notice.
But the sweep belongs at **commit time**, the only moment the tooling can put a
row where it belongs. If a side-effect fires where it cannot be committed, make
the side-effect land somewhere **untracked** and fold it in later — never invent
a commit to hold it. Auto-staging is **only** safe for this file class
(append-only, machine-generated, no line ownership); never auto-sweep
hand-authored content.

## Universality

This is a `common/` pattern — owned by no single agent; every agent inherits
via the `_AGENT_KB_UNOWNED_ALLOWLIST` in `compliance.py`. Any future cache
module (code-embeddings, conversation-embeddings, etc.) opts in with the
same recipe.

## Constraints

- The ledger is append-only; rows are never deleted or modified.
- The ledger is committed to the repo (not gitignored) so spend history
  persists across clones and session resets.
- Cost estimates are advisory (±20% on the fallback path). Real billing
  remains in the OpenAI dashboard.
