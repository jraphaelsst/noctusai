# Scoped auto-improvement — durable surfaces + consult-before-editing

**What it is.** The third keeper-mirror cache in the family (after [[keeper-pattern-cache]] + [[agent-context-architecture]]) — a structured, queryable home for the **drift / improvement observations** every dispatch surfaces. Codifies the user mandate (2026-05-26 Phase B): *"agents are scoped auto-improving … the improvement should follow the pattern of the wiring the agents pointer system has — a keeper drift detector pattern, cached for consultation in cached memory not the actual file for patterns before editing docs/agents."*

**Why.** Without a durable, queryable store, engineer / tech-lead surfaces live only in session chat. Chat decays at compaction; next session re-discovers yesterday's slip. The cache makes those surfaces **consultable** — agents query the cache BEFORE editing a doc/agent so authoring incorporates the most-recent observations, not yesterday's stale state.

## The 3-leg keeper-mirror contract (third in the family)

Same shape as `keeper-pattern-cache` and `agent-context-cache`:

| Leg | Mechanism |
|---|---|
| Eager pre-commit refresh | `scripts/hooks/pre-commit`: if `project-history/auto-improvement.ndjson` is staged → `cli.py --refresh-auto-improvement-cache` runs before the commit lands. |
| Lazy query-time refresh | `auto_improvement.query()` compares `cache_meta.source_sha` vs live `sha256(ndjson)`; mismatch → rebuilds + answers — cache self-heals on use. |
| Loud freshness gate | `check_auto_improvement_cache_freshness` (severity high) — fails `validate` when stale. |

## Storage layout

```
project-history/auto-improvement.ndjson      ← source of truth (committed)
.claude/cache/auto-improvement.sqlite        ← derived mirror (gitignored)
```

The **ndjson lives under `project-history/`** alongside `worktree-salvage.ndjson` — it's a permanent ledger, observable in git history. The sqlite is a derived cache (gitignored, mole tradition).

## ndjson schema (one JSON object per line)

```json
{
  "ts":          "2026-05-26T...",        // ISO-8601 UTC
  "agent":       "backend-engineer",       // who surfaced (engineer name | 'tech-lead' | 'architect' | null)
  "scope":       "scoped",                 // 'scoped' (engineer-slice) | 'broad' (tech-lead cross-cutting)
  "kind":        "drift",                  // 'drift' | 'improvement'
  "target":      ".claude/agents/<x>.md",  // the doc/agent/file the surface is ABOUT (path or '*' for cross-cutting)
  "description": "verbatim surface text",
  "status":      "s1-emergent",            // 's1-emergent' | 's2-memory' | 's3-kb' | 's4-keeper' | 'closed'
  "source_ref":  "commit:abc123 | session:..." // optional provenance
}
```

**Status flow** maps directly to the codification pipeline (`KB § PATTERNS/methodology-codification-pipeline.md`):
`s1-emergent` (just surfaced) → `s2-memory` (lands in MEMORY) → `s3-kb` (lands in a KB doc) → `s4-keeper` (gets a detector) → `closed` (resolved, no further work).

## sqlite schema

```sql
CREATE TABLE auto_improvement (
  rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  agent       TEXT,
  scope       TEXT NOT NULL,
  kind        TEXT NOT NULL,
  target      TEXT NOT NULL,
  description TEXT NOT NULL,
  status      TEXT NOT NULL,
  source_ref  TEXT,
  cached_at   TEXT NOT NULL
);
CREATE INDEX idx_auto_target ON auto_improvement(target);
CREATE INDEX idx_auto_status ON auto_improvement(status);
CREATE INDEX idx_auto_kind ON auto_improvement(kind);

CREATE TABLE cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- keys: 'source_sha' (sha256 of ndjson), 'populated_at'
```

## Public API

- `noctus.dev.auto_improvement_log(scope, kind, target, description, agent?, status?, source_ref?)` — append one entry to the ndjson.
- `noctus.dev.auto_improvement_query(target?, agent?, kind?, status?, open_only?, limit?)` — consult the cache; most-recent-first.
- `noctus.dev.auto_improvement_refresh(force?)` — re-populate cache; idempotent.
- CLI: `python mcp/noctusai/cli.py --refresh-auto-improvement-cache [--force]` · `--auto-improvement-query <target>` · `--check-auto-improvement-cache-freshness`.

## The consult-before-editing discipline

Mirrors [[keeper-check-before-docing]]. Before authoring or modifying:

| Surface | Consult target |
|---|---|
| `.claude/agents/<x>.md` | `target = ".claude/agents/<x>.md"` |
| `KB § PATTERNS/<x>.md` (or any KB doc) | `target = "KB § PATTERNS/<x>.md"` (or substring like `"KB § PATTERNS/"`) |
| `CLAUDE.md` § 1 | `target = "CLAUDE.md"` |
| `compliance.py` | `target = "mcp/noctusai/tools/noctus/dev/compliance.py"` |
| Cross-cutting (no specific file) | `target = "*"` |

```bash
python mcp/noctusai/cli.py --auto-improvement-query "<target-or-substring>"
```

Returns open (non-closed) surfaces, most-recent-first. The author incorporates relevant items in the same edit (and updates the entry's `status` to `closed` if the edit resolves it).

## How surfaces land in the ledger

**Engineer side** (scoped — engineer-slice):
The engineer's `drift-found:` / `scoped-improvement:` lines in their short-form return are TEXT — they don't write to the ledger directly (file-disjoint discipline / commit-own-branch-only). The **tech-lead** transcribes via `noctus.dev.auto_improvement_log(...)` after reading the engineer's report.

**Tech-lead side** (broad — cross-cutting):
The tech-lead logs directly when surfacing methodology-level observations during the session (architectural slips, doc-tool coherence drift, recurrence patterns).

## Why the role-split persists at the ledger layer

The same surface-don't-resolve role separation from [[drift-fix-on-contact]] § Roles carries through to who writes the ndjson:
- Engineers SURFACE in their return text.
- Tech-lead WRITES to the ledger (the durable form).
- Anyone (engineer OR tech-lead, future sessions) CONSULTS the cache.

Read = open. Write = funnel through the tech-lead. Authority-of-codification stays at the tech-lead competence boundary (the methodology-codification-pipeline parent rule).

## Anti-patterns

- **Skip the consult.** Editing a doc/agent without first querying the cache means yesterday's surfaced observations might not be incorporated. The cache lookup costs ~10ms.
- **Engineer writes the ndjson directly.** Breaks file-disjoint commit hygiene + skips the tech-lead's broad-context filter. Engineers surface in text; tech-lead transcribes.
- **Never update status.** A perpetual `s1-emergent` entry is noise; the status flow (s1→s2→s3→s4→closed) IS the codification visibility.
- **Surface in chat but not in the ledger.** Chat decays; ledger persists. Tech-lead's transcription leg is non-negotiable.

## Composes with

[[keeper-pattern-cache]] (first cache; the contract pattern) · [[agent-context-architecture]] (second cache; sibling) · [[keeper-check-before-docing]] (cache-query-upfront discipline, applied here as consult-before-editing) · [[drift-fix-on-contact]] (§ Roles + § Scoped auto-improvement — the engine that produces the surfaces this cache stores) · [[methodology-codification-pipeline]] (the status flow s1→s4 maps to the pipeline stages) · [[safety-nets-become-learnings]] (the philosophy parent — safety net firing IS the methodology working) · [[always-hardening-posture]] (umbrella).
