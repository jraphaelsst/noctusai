# Code recurrence baselines — ratified-canonical snapshots

Each `*.json` file is a durable ratification of `code_recurrence_promote.scan()` matches at a point in time. See [`KB § CONTEXT/PATTERNS/common/code-recurrence-baseline.md`](../../KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/code-recurrence-baseline.md) for the full pattern.

**Filename**: `YYYY-MM-DD-<short_code_corpus_sha>.json`.

**Read-only by convention** — never overwrite. New decisions create new files (append-only ledger).

Created/updated via `noctus.dev.code_ratify` (MCP) or `mcp/noctusai/cli.py --code-ratify <reason>` (CLI).

Sister of `project-history/kb-baselines/` (which ratifies owns_kb validation findings).
