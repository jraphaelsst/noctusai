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
  "source_ref":  "commit:abc123 | session:...", // optional provenance
  "resolve_when": "keeper:check_x",         // OPTIONAL resolution handle (predicate, or list AND-combined)
  "resolve_to":   "closed"                  // OPTIONAL target status when resolve_when passes (default 'closed')
}
```

**Status flow** maps directly to the codification pipeline (`KB § PATTERNS/common/methodology-codification-pipeline.md`):
`s1-emergent` (just surfaced) → `s2-memory` (lands in MEMORY) → `s3-kb` (lands in a KB doc) → `s4-keeper` (gets a detector) → `closed` (resolved, no further work).

## Reconcile — landed drift self-closes (heal-on-contact)

**The bug this kills.** The ledger is append-only and the hot-drift surface (the `/contextualize` protocol) shows every OPEN `s1`/`s2-memory` entry. The recurring failure: a drift's fix LANDS, but the resolving session APPENDS a fresh `closed`/`s4-keeper` row (a new `ts`+`target`+`description`) instead of promoting the ORIGINAL — so the original `s2-memory` row never dies and re-surfaces as "hot drift" every session, until someone re-investigates and discovers it was already done. Observed 2026-06-01: 4 entries resolved at 00:39 via appended rows, still surfaced by the 00:53 cache rebuild. `auto_improvement_promote` keys on the exact `(ts,target,description)` triple the resolver rarely has handy.

**The fix.** Each entry carries an optional `resolve_when` — a declarative predicate describing the real-world condition that means *resolved*. `noctus.dev.auto_improvement_reconcile` evaluates it against the live tree and auto-advances the ORIGINAL row's `status` to `resolve_to` (default `closed`), stamping `resolved_ts` + `resolved_by` for audit. A landed fix stops re-surfacing WITHOUT anyone flipping status by hand.

**Predicate grammar** (`auto_improvement._eval_predicate`; a list is AND-combined; unknown grammar ⇒ unmet, never silently resolved):

| Predicate | Satisfied when |
|---|---|
| `keeper:<name>` | `def <name>(` exists in `compliance.py` |
| `path_exists:<relpath>` | file/dir exists under repo root |
| `grep_present:<term>@<path>` | ≥1 file under `<path>` contains `<term>` |
| `grep_max:<n>:<term>@<path>` | ≤ `n` files under `<path>` contain `<term>` |
| `superseded_by:<target_substr>` | a LATER entry at a terminal status (`s4-keeper`/`closed`) has `target` ⊇ substr |

**Heal-on-contact at the READ path (the structural guarantee).** `auto_improvement_query(open_only=True)` — the canonical hot-drift / orientation read path — auto-runs reconcile in dry-run and **excludes any entry whose `resolve_when` already passes**. So a fresh environment can NEVER re-detect already-done work, *regardless of whether anyone remembers to run reconcile*. This is the fix for the "implement it → next session it's still recommended → re-discover it's done" loop: the surface is correct on every read. (`skip_reconcile=True` returns the ledger's literal not-closed set — used by the apply path + tests.) The ledger row may still read `s2`/`s3` in git until an explicit close; running `auto_improvement_reconcile dry_run=False` (atomic ndjson rewrite + cache refresh) + committing makes git truthful too. Reconcile NEVER mutates silently inside a read — the ndjson is a committed source-of-truth, so the *write* is always explicit + committed; only the *display filter* is automatic. Idempotent: terminal rows (`s4-keeper`/`closed`) are never re-touched, and an entry already at its `resolve_to` is skipped (no re-stamp churn).

**Auto-promote, not just auto-close.** `resolve_to` defaults to `closed` but can target any status: an `s3` entry with `resolve_when: keeper:<name>` + `resolve_to: s4-keeper` auto-promotes to `s4` the moment its keeper lands. So the pipeline advances itself: s2→closed when the fix lands, s3→s4 when the keeper lands.

**Discipline (gated).** Keeper `check_open_drift_has_resolution_handle` (severity `medium`) flags any OPEN entry past s1 — `s2-memory`, `s3-kb`, `s3-codified` — lacking a `resolve_when`; it cannot self-close/auto-promote and would rot (re-surface as hot drift or as a perpetual radar candidate). `s1-emergent` is exempt (too freshly-surfaced); `s4-keeper`/`closed` are terminal. So: log an open entry WITH its resolution handle, and reconcile retires/advances it for you when the work lands. (`check_s2_drift_has_resolution_handle` is a back-compat alias — the keeper was born s2-only on 2026-06-01 and widened to all gated statuses the same day.)

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
