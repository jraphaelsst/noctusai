# Changelog

All notable changes to noc are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
as codified in `KB § CONTEXT/PATTERNS/common/versioning.md`.

---

## [4.0.0-beta] — 2026-05-26

The methodology + structural-refactor release. v3 → v4 is a MAJOR bump
because the methodology surface contract changed shape (3-way → 7-way sync),
the dev-team specialist agent roster landed as first-class, and the PATTERNS/
tree was reorganized by ownership.

### Breaking changes (vs. v3)

- **Methodology surface contract**: 3-way sync (CLAUDE.md / KB / agent context)
  promoted to **7-way sync** (added MEMORY.md, CONTEXTUALIZE.md, `.claude/skills/`,
  `.claude/commands/`). See `KB § PATTERNS/common/seven-way-sync.md`.
- **PATTERNS/ reorg**: from flat layout to ownership-organized subfolders
  (`common/`, `architect/`, `backend/`, `frontend/`, `devops/`, `security/`,
  `compliance/`). Old paths broken; INDEX.md updated.
- **Agent contract**: agents now declare `owns_kb:` in frontmatter; bodies
  become L1 INDEX (rule + `→` pointer) over KB depth.

### New methodology rules (CLAUDE.md §1)

- Parallelization-first orchestration (the DEFAULT mindset for dispatch).
- Dispatch via `task_branch`, NEVER Agent `isolation: "worktree"` (stale-base hazard).
- Inline = empersonate the specialist (lens-switching at task boundaries).
- Drift-fix-on-contact (PAUSE → resolve → surface → DOC → continue).
- Roadmap tracking — multi-session project plans in `project-history/roadmaps/`.
- Persistent-files absorption (lessons into KB/memory BEFORE archive/teardown).
- Don't block on background tasks — keep working in parallel + `ScheduleWakeup` fallback.
- 7-way sync — methodology surfaces stay aligned.
- Cache-locking discipline — WAL mode on every keeper-mirror SQLite cache.

### New infra

- **5 keeper-mirror caches** with the 3-leg mirror contract: keeper-patterns +
  agent-context + auto-improvement + kb-embeddings + code-embeddings.
- **WAL mode** on all 5 caches (cache-locking-discipline).
- **Vector platform**: kb-vector-search, code-embeddings, vector-costs (with opt-in
  namespace attribution), vector-calibration (reasoning-driven, NOT auto-tuning),
  kb-baseline + code-baseline (ratification layer), kb-recurrence-radar (semantic
  consult-before-editing), code-recurrence-promote (cross-product recurrence loop).
- **Codification pipeline closed end-to-end**: code-embeddings → recurrence-promote
  → auto-improvement.ndjson → codification_radar → s2/s3/s4 promotion candidates.

### New keepers

- `check_six_way_sync` (now `check_seven_way_sync`) — composition gate over 6
  sub-keepers (kb_sync, contextualize, agent_kb, skills_listed, commands_listed,
  memory_md_index).
- `check_skills_listed_in_router` — skills ↔ CLAUDE.md §2 sync.
- `check_commands_listed_in_router` — commands ↔ CLAUDE.md §2 sync.
- `check_kb_semantic_drift` — kb_baseline diff vs. ratified.
- `check_code_recurrence_drift` — code_baseline diff vs. ratified.
- `check_kb_vector_canonical` — markdown stays canonical, vector DB is enrichment.
- `check_code_embeddings_cache_freshness` — 5th keeper-mirror.
- `check_kb_embeddings_cache_freshness` — 4th keeper-mirror.
- `check_keeper_cache_freshness`, `check_agent_context_cache_freshness`,
  `check_auto_improvement_cache_freshness` — 1st, 2nd, 3rd keeper-mirrors.

### New slash commands (`.claude/commands/`)

- `/vector-status` — 5-cache health overview + cost ledger snapshot.
- `/baselines` — kb + code ratification status + diff.
- `/codification-radar` — surface s1/s2 → s3 promotion candidates.
- `/cost-report` — vector-costs.ndjson aggregation with empirical calibration.
- `/verify-pass` — Pass-A + Pass-B verify scaffolding.

(`/codify` was already in v3.x.)

### New procedure skills (`.claude/skills/`)

The full noc-* skill set + `skill-creator` was bedded down in v3.5; in v4.0 they
became first-class methodology surface members (6-way sync promotion).

### New MCP tools

Tool count went from ~142 (v3 tail) → **162** (v4.0-beta) — net +20 across the
session.

### Pre-commit hook (legs added in v4.0)

- Leg 4a — skills↔router sync (blocking).
- Leg 9b — kb-embeddings cache auto-refresh on KB doc change.
- Leg 9c — code-embeddings cache auto-refresh on code source change.
- Leg 10 — auto-improvement cache auto-refresh.
- Leg 11 — vector-costs ledger JSON sanity (advisory).
- Leg 12 — seven-way-sync gate (blocking when any methodology surface staged).
- Leg 13 — kb-baselines staleness hint on large KB changes (advisory).

### Verify pass

9/9 slices verified against live state. Total OpenAI spend: **$0.101** for the
full kb-embeddings + code-embeddings cold population (1,964 + 2,779 chunks).

### Known issues

- 4 pre-existing pytest failures in `test_symbology_and_vite_supabase_detectors.py
  ::TestCheckDocSymbologyDrift::*` — keeper behavior changed; tests didn't follow.
  Pre-v4.0, unresolved.

### Migration from v3

Agents and tooling that referenced old PATTERNS/ paths must update to the new
ownership-organized layout. `kb_sync` will surface every broken pointer.

---

## [3.x] and earlier — pre-2026-05-26

Pre-formal-versioning era. Methodology lived in CLAUDE.md without a stamp.
See `git log` for the chronological trail.
