# Keeper-pattern cache — local SQLite mirror of the keeper module

**What it is.** `.claude/cache/keeper-patterns.sqlite` (gitignored) is a local mirror of the validation patterns embedded in `mcp/noctusai/tools/noctus/dev/compliance.py` + its colocated `tests/test_*.py` fixtures. Doc-authoring agents query the cache BEFORE writing a gated doc → write compliant first try → no rework. Codified 2026-05-26.

**Why.** `compliance.py` is ~8000 lines + ~60 `check_*` keepers + several `_HARNESS_*_AGENTS` name-bound contracts. An agent that doesn't *know* the contract authors a drift-prone doc → gets gated → reworks (with the agent dispatch tax compounding the cost). The cache is the cheap lookup.

**Mirror contract (user mandate — "the memory should always be the keeper mirror").** Modifying `compliance.py` MUST cause a refresh. Enforced by three legs:
1. **Eager pre-commit refresh** (`scripts/hooks/pre-commit`): if `compliance.py` is staged → `cli.py --refresh-keeper-cache` runs before the commit lands.
2. **Lazy query-time refresh** (`keeper_pattern_cache.lookup()`): compares `cache_meta.source_sha` vs live `sha256(compliance.py)`; on mismatch, rebuilds + answers — the cache self-heals on use.
3. **Loud freshness gate** (`check_keeper_cache_freshness`, severity `high`): if the cache is missing / unreadable / stale, the keeper fails in `validate` so the drift is visible, not papered over.

## File location + git status
`.claude/cache/keeper-patterns.sqlite` — **gitignored** (derived; mole tradition for fs-derived artifacts). Deleting it is safe — `refresh()` rebuilds on next query. Sibling: anonymous Docker volumes (regenerable, never tracked).

## Schema
```sql
CREATE TABLE keeper_patterns (
  keeper_name      TEXT NOT NULL,    -- 'check_agent_format' | 'check_agent_archetype_contract::_HARNESS_EXECUTOR_AGENTS' | …
  pattern_kind     TEXT NOT NULL,    -- 'contract-clause' | 'set-membership' | 'fixture-example' | 'session-data'
  pattern_value    TEXT NOT NULL,    -- the literal contract (docstring 1st line / set members / fixture string)
  severity         TEXT,             -- 'high' | 'warning' | NULL (inferred when present in source)
  remediation      TEXT,             -- human-readable fix (when available)
  source_file      TEXT NOT NULL,    -- 'mcp/noctusai/tools/noctus/dev/compliance.py' | 'mcp/noctusai/tests/test_*.py'
  source_line      INTEGER,
  fixture_example  TEXT,             -- full literal for fixture-example rows
  scope            TEXT NOT NULL DEFAULT 'permanent',  -- 'permanent' | 'session-<uuid>'
  cached_at        TEXT NOT NULL     -- ISO-8601 UTC
);
CREATE INDEX idx_keeper_name ON keeper_patterns(keeper_name);
CREATE INDEX idx_scope ON keeper_patterns(scope);

CREATE TABLE cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL                -- 'source_sha' (sha256 of compliance.py), 'populated_at'
);
```

## Population (AST-first per the rule)
- `_extract_keepers_from_compliance()` — regex-locates `def check_*(...)`, takes its docstring 1st-line as a contract-clause row.
- `_extract_set_membership()` — regex-locates `_HARNESS_*_AGENTS = frozenset({...})` constants; emits set-membership rows with severity=high + remediation note.
- `_extract_fixtures_from_tests()` — **`ast.walk`** the test files (a naive `"..."` regex catches code text BETWEEN string literals — proven by build-time test failure on 2026-05-26; AST is the fix). Filters string constants `≥10` chars containing `---`/`name:`/`tools:`/`description:` → fixture-example rows.

## API
- `noctus.dev.keeper_pattern_lookup(keeper_name?, file_path?)` — query by keeper-name substring OR file-path heuristic (`.claude/agents/<x>.md` → `agent_format` + `agent_archetype`; `CLAUDE.md` → `claude_md_router`; etc.). Both filters optional; combined = AND.
- `noctus.dev.keeper_pattern_refresh(force=False)` — re-populate; idempotent; `force=True` bypasses the in-sync short-circuit. Auto-run by pre-commit.
- `noctus.dev.keeper_pattern_list()` — distinct keeper names in cache.
- CLI: `python mcp/noctusai/cli.py --refresh-keeper-cache [--force]` · `--keeper-pattern-lookup <name_or_path>` · `--check-keeper-cache-freshness`.

## Session lane (temporary cache, dev/research use)
Same DB, `scope='session-<uuid>'` rows. `session_set(scope_id, key, value)` / `session_get(scope_id, key?)` / `sweep_session(ttl_hours=24)`. TTL via `cached_at`. Permanent rows are never touched by the sweep.

## How a doc-authoring agent uses it (the keeper-check-before-doc'ing discipline)
Before writing `.claude/agents/<new>.md`:
```bash
python mcp/noctusai/cli.py --keeper-pattern-lookup ".claude/agents/<new>.md"
```
Returns the applicable patterns (frontmatter shape from fixtures, set-membership constraints, severity hints). The agent writes a compliant doc on the first try.

Full discipline: [[keeper-check-before-docing]].

## Sibling rule
Persistent files in projects + `.claude/worktrees/*` must be absorbed to KB/memory BEFORE teardown — see [[persistent-files-absorption]]. Both are "context-preservation" disciplines: cache preserves keeper context for authoring; absorption preserves project context for the durable record.

## Risks + carve-outs
- **Schema migrations** — adding a column to `keeper_patterns` requires the cache to be rebuilt (drop + refresh). The freshness keeper catches via the source_sha (compliance.py change ⇒ refresh ⇒ new schema picked up).
- **Performance** — lookup is O(log n) on the indexes; the whole cache is ~80 rows currently, well under any concern.
- **Test-only patterns** — some keepers have patterns defined inline in `compliance.py` without a colocated test fixture; those land as `contract-clause` rows (docstring 1st-line) which may be less complete than fixture-example. The agent's discipline: read the docstring + open the keeper if the cache row alone is insufficient — *the cache is a shortcut, not the entire contract*.

## Composes with
[[methodology-codification-pipeline]] (this cache is a Stage-4-adjacent infrastructure — it makes the existing keepers more usable, not new keepers) · [[claude-md-router-discipline]] (the router/format-keeper sibling pattern) · [[storage-hygiene]] (the gitignored-derived-artifact precedent) · [[testing]] (regression-test-the-detector for the new keeper) · [[ast]] (AST-first extractor was the fix when regex extraction broke).
