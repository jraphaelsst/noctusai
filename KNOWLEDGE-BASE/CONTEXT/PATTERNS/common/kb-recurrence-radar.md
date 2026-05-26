# KB recurrence radar — semantic consult-before-editing

**What it is.** A semantic-search layer over `auto-improvement.ndjson` open entries. Given a path being edited or free text being authored, ranks open auto-improvement entries by cosine similarity to the query. Born 2026-05-26 (post-close batch on automation-orchestration-2026-05).

**Sibling pattern.** [`code-embeddings § Use case 2 (pre-authoring radar)`](code-embeddings.md) does this for CODE; THIS does it for **decisions** (auto-improvement entries). Together they form a two-corpus consult-before-edit surface.

## Why this exists

`auto_improvement.query(open_only=True)` is the keyword-based consult: returns entries whose `target` matches a string. But entries are often phrased abstractly — an entry about "engineer dispatch stale-base hazard" might never mention `task_branch.py` by name even though it's load-bearing context if you're touching `task_branch.py`.

`kb_recurrence_radar` bridges that gap: embed the surface being edited → cosine vs every open entry's description → top-K ranked hits.

## What's shipped

| MCP tool | Purpose |
|---|---|
| `noctus.dev.kb_recurrence_radar(text?, path?, top_k, min_score, open_only, limit_entries)` | Semantic consult. Provide EITHER `text` OR `path`. Returns `[{entry, score, key_overlap}]` ranked desc. |

When `path` ends with `.md`, the consult prepends the H1 title for stronger signal. When `text` is provided, that's the query verbatim.

## How it composes

- **`auto_improvement.query`** (keyword) — exact-target lookups.
- **`kb_recurrence_radar`** (semantic) — fuzzy-intent lookups, surfaces entries that describe the surface without naming it.
- **`codification_radar.cluster`** — groups OPEN entries among themselves by cosine; surfaces promotion candidates. Different intent (promotion vs. consult).

## In-session embedding cache

Open entries are embedded ONCE per process (cache keyed by `sha256(description)`). For a typical N≤100 open entries, that's one OpenAI batch. Subsequent calls reuse the cache.

## When to use

| Scenario | Best tool |
|---|---|
| "Find every entry mentioning task_branch.py" | `auto_improvement.query` (keyword) |
| "Find every entry about dispatch / branching, even if they don't name task_branch" | `kb_recurrence_radar` (semantic) |
| "What's currently clustering toward s3 promotion?" | `codification_radar.cluster` |
| "What did we DECIDE about this surface?" | `kb_recurrence_radar` |

## Anti-patterns (do NOT do)

- **DON'T use as a replacement for `auto_improvement.query`.** Keyword search is precise; semantic is fuzzy. Use the right tool.
- **DON'T treat low scores as zero signal.** A score of 0.3 may still be relevant if `key_overlap=True`. The `key_overlap` flag is your sanity check on the semantic match.
- **DON'T pass huge `limit_entries` for ad-hoc queries.** The first call embeds all entries; pick a reasonable cap (500 default) unless you really want exhaustive recall.

## Composes with

- [`code-embeddings`](code-embeddings.md) — sister consult pattern for code.
- [`scoped-auto-improvement`](scoped-auto-improvement.md) — the ledger source.
- [`vector-calibration`](vector-calibration.md) — if score thresholds need tuning.
