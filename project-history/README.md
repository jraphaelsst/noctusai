# Project History — Global Ledger

> Auto-stamped record of every project this repo has shipped (closed, deleted, split, or deferred). Intended for human review **and** future AI training on cost-efficiency × proven-solutions patterns.
>
> Design + decisions live in **`projects/project-history-ledger/PROJECT.md`** — this README mirrors the executable surface.

---

## Contents

| File | Role | Edited by |
|---|---|---|
| `ledger.ndjson` | Canonical structured store. One JSON record per line, append-only. | `noctus.dev.history_record` (Phase 1) + `noctus.dev.archive` (Phase 2) |
| `PROJECT-HISTORY.md` | Human-readable view, auto-generated. | `scripts/render-project-history.py` (Phase 3) — **do not hand-edit** |
| `README.md` | This file. | Methodology updates only. |

---

## Record format (NDJSON)

Each line in `ledger.ndjson` is a self-contained JSON object. Standard fields (locked in §7 Q4 of the PROJECT.md):

```json
{
  "slug": "project-history-ledger",
  "scope": "cross-product",
  "status_at_close": "shipped",
  "dates": {"created": "2026-05-02", "closed": "2026-05-XX"},
  "phases": [
    {"name": "Phase 0 — Scaffold + tokenizer", "status": "shipped", "tokens": 1234},
    {"name": "Phase 1 — Schema + writer", "status": "shipped", "tokens": 5678}
  ],
  "short_summary": "1-3 sentence what + why",
  "short_review": "5-10 bullet steps in retrospect",
  "token_count": {
    "project_doc_tokens": 12345,
    "improvements_tokens": 1234,
    "proposals_tokens": 567,
    "code_delta_tokens": 89012,
    "total": 103158
  },
  "outcome_signals": ["pytest 1816/1816 green", "CLAUDE.md trim 38%"]
}
```

Optional fields (deferred to v2): `tags`, `linked_artifacts`, `prior_projects`, `backfilled`.

`scope`: `cross-product` | `single-product` | `core-control`
`status_at_close`: `shipped` | `abandoned` | `split` | `deferred` | `historical` (backfill)

---

## When are entries stamped?

- **Project close** (status → ✅ Done) → entry written.
- **Project deletion** (folder removed via `apply-inline-then-delete`) → entry written if not already.
- **Project split** (e.g. methodology-extraction → mirror split) → one entry per side.

All three trigger via `noctus.dev.archive` (Phase 2 integration) — the close-protocol step stamps the ledger BEFORE git-mv'ing the folder to `archive/`.

---

## Rendering

`scripts/render-project-history.py` reads `ledger.ndjson`, sorts by `dates.closed` descending, emits `PROJECT-HISTORY.md` (table + per-project narrative blocks). Idempotent. Wired into the pre-commit hook so the human view never drifts from the structured source.

---

## Tokenizer

Static counting via `tiktoken` (`cl100k_base` encoding) — Anthropic-compatible enough for cost-efficiency comparisons. Dynamic per-turn telemetry is out of scope until a harness hook exists.

---

## Pointers

- `projects/project-history-ledger/PROJECT.md` — full design + open questions + change log.
- `KB § PATTERNS/project-execution.md § 11` — where the close-protocol step is documented (after Phase 2 amends it).
- `mcp/noctusai/tools/noctus/dev/history.py` — the writer MCP tool (Phase 1).
