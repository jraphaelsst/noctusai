# KB baselines — ratified-canonical snapshots

Each `*.json` file is a durable ratification of `kb_validate_owns_kb()` findings at a point in time. See [`KB § CONTEXT/PATTERNS/common/vector-baseline.md`](../../KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/vector-baseline.md) for the full pattern.

**Filename**: `YYYY-MM-DD-<short_corpus_sha>.json`.

**Schema**: see KB pattern doc § Storage.

**Read-only by convention** — never overwrite a baseline. New decisions create new files (append-only ledger).

Created/updated via `noctus.dev.kb_ratify` (MCP) or `mcp/noctusai/cli.py --kb-ratify <reason>` (CLI).
