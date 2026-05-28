# Eight-way sync — the methodology surface contract

**What it is.** A formal sync contract across the eight **first-class methodology surfaces** in this codebase. Changing one without aligning the others is structural drift — the codebase becomes inconsistent with what an agent or developer reads in CLAUDE.md / KB / agent files / etc. Born 2026-05-26 as the seven-way sync (promotion from the legacy "three-way sync" rule); promoted to **eight-way** on 2026-05-28 when `.claude/cache/` was codified as the live agent read path (per the `cache-as-agent-tool` rule).

## The eight surfaces

| # | Surface | What it carries | Load timing |
|---|---|---|---|
| 1 | **`CLAUDE.md`** | Always-on router (§1 principles + §2 map) | Every session, every reply |
| 2 | **`MEMORY.md`** (auto-memory) | Per-user behavioral rules + project state | Every reply (system reminder) |
| 3 | **`.claude/agents/<name>.md`** | Specialist L1 INDEX + `owns_kb:` declarations | Dispatch time (per agent) |
| 4 | **`KNOWLEDGE-BASE/`** (tree) | Methodology depth — patterns, integrations, guides, per-product detail | On-demand (consulted via grep / kb_search / agent_context cache) |
| 5 | **`CONTEXTUALIZE.md`** | Fresh-agent read map (pointer-only) | Session start when `/contextualize` skill triggers |
| 6 | **`.claude/skills/<name>/SKILL.md`** | Procedural skill bodies — auto-trigger on phrases | Session start (auto-load) + at trigger phrase |
| 7 | **`.claude/commands/<name>.md`** | Slash-invoked commands (`/codify`, `/vector-status`, ...) | Session start (auto-load) + at slash invocation |
| 8 | **`.claude/cache/`** | Eight keeper-mirror caches mirroring the 7 doc sources + code + memory + landscape graph | **Agent read path** (queries via `noctus.{graph,kb,code,memory}.*`) |

These eight are **first-class methodology surfaces**: an agent reading any one of them should arrive at a consistent picture. A rule added to CLAUDE.md §1 that isn't reflected in the relevant skill OR isn't backed by a KB doc OR isn't carried in the right agent's `owns_kb` OR not reachable via the relevant cache IS drift.

**Promotion #7 → #8 (2026-05-28 evening)**: surface count moved from 7 to 8 after `cache-as-agent-tool` was codified (CLAUDE.md §1) — caches are the LIVE read path agents reach BEFORE grep/Read. A stale or wrong cache silently mis-answers at the consumption layer. Structural mirror is guaranteed by the 4 git hooks (pre-commit + post-merge + post-checkout + pre-push) running `refresh_all_caches`; logic-correctness of the extractors is a SEPARATE concern (see [extractor-correctness-vs-mirror](extractor-correctness-vs-mirror.md)). The 8-way sync closes the structural gap; the residual logic gap has its own test surface (the `mcp/noctusai/tests/test_graph_*.py` suite + per-extractor pytest).

## What's NOT in the 8-way

These are **referenced** by the methodology surfaces but aren't themselves first-class methodology carriers:

- `scripts/hooks/pre-commit` — executable gate. Implements but doesn't define methodology.
- `mcp/noctusai/tools/noctus/dev/compliance.py` — keeper code. The EXECUTABLE form of the rules. The pre-commit hook calls into it; the rules' canonical statement is in CLAUDE.md §1 + KB.
- `mcp/noctusai/cli.py` — CLI flags. Surface for the keeper executions, not the rules themselves.

These are gated by their own contracts (pre-commit hook itself runs each cli flag → any mismatch fails LOUD). They don't need to be members of the 8-way sync because they don't carry methodology PROSE that can independently drift.

## The sync contract

Adding or modifying a methodology rule MUST touch all surfaces where it applies, in the SAME commit:

| Type of change | Surfaces that MUST update together |
|---|---|
| New §1 rule in CLAUDE.md | + KB pattern doc + at least one referenced skill/agent/INDEX if it points to those |
| New KB pattern doc | + KB INDEX.md + CLAUDE.md §1 pointer (if always-on relevant) + agent `owns_kb:` (if a specialist owns the territory) + KB embeddings cache refresh (lazy) |
| New `.claude/skills/<name>/SKILL.md` | + CLAUDE.md §2 map listing + procedure-references current |
| Agent body change | + agent's `owns_kb:` declarations match body content + agent-context cache refresh (lazy) |
| Auto-load doc (CLAUDE.md / CONTEXTUALIZE.md) change | + counts + canonical-cores still cross-resolvable |
| New keeper (compliance.py) | + CLI flag in cli.py + pre-commit hook leg + CLAUDE.md §1 rule (if always-on) + KB doc + test |
| New cache (under `.claude/cache/`) | + a per-cache `check_<name>_cache_freshness` keeper + wire into `check_all_cache_freshness` + 4-hook contract (pre-commit + post-merge + post-checkout + pre-push) + KB doc |

## Keeper enforcement

`check_eight_way_sync` (severity `high` — methodology drift IS a correctness issue at the agent-context layer).

**What it checks** (per the canonical surface predicates):

1. **`CLAUDE.md`**: every `KB §` pointer resolves to a real file under `KNOWLEDGE-BASE/`.
2. **`CONTEXTUALIZE.md`**: every canonical-core entry in compliance.py's `_CONTEXTUALIZE_CANONICAL_CORES` is referenced.
3. **`KNOWLEDGE-BASE/INDEX.md`**: every KB doc on disk is indexed (via the existing `kb_sync` gate).
4. **`.claude/agents/<name>.md`**: every `owns_kb:` entry resolves; not in `_AGENT_KB_UNOWNED_ALLOWLIST` unless commons.
5. **`.claude/skills/<name>/SKILL.md`**: every skill listed in CLAUDE.md §2 maps to a directory containing `SKILL.md`.
6. **`.claude/commands/<name>.md`**: every command listed in CLAUDE.md §2 maps to a file on disk; every on-disk command is mentioned in CLAUDE.md.
7. **`MEMORY.md`**: index lines ≤ ~200 chars (existing `check_memory_md_index` discipline).
8. **`.claude/cache/`**: every keeper-mirror cache's `source_sha` matches the live aggregate (composed via `check_all_cache_freshness`).

The keeper is a **composition** of existing checks + the new surface-presence checks for skills + commands + the cache-freshness composition. Reuses the established sub-keepers:
- `check_kb_sync` (#1, #3)
- `check_contextualize_alignment` (#2)
- `check_agent_kb_alignment` (#4)
- `check_memory_md_index` (#7)
- `check_skills_listed_in_router` (#5)
- `check_commands_listed_in_router` (#6) — sister of skills check, applied to `.claude/commands/`.
- NEW: `check_all_cache_freshness` (#8) — composition of the per-cache freshness keepers (`check_keeper_cache_freshness`, `check_agent_context_cache_freshness`, `check_auto_improvement_cache_freshness`, `check_code_embeddings_cache_freshness`, `check_noc_graph_cache_freshness`, `check_kb_embeddings_cache_freshness`, `check_corpus_embeddings_cache_freshness`, `check_memory_embeddings_cache_freshness`).

## Composition-keeper base (`_run_composed_keeper`)

`check_seven_way_sync` (now `check_eight_way_sync`) was the first composition keeper that ran multiple sub-keepers and decorated each result with a `<composition>-<sub>::<orig-symbol>` prefix so root-cause is traceable. The pattern was extracted to a reusable helper `_run_composed_keeper(name, sub_keepers)` in compliance.py — future composition gates reuse it without copy-pasting the loop + exception-tolerant wrapper. `check_all_cache_freshness` is the second composition gate built on the same primitive.

## Adding a new methodology surface (the promotion ritual)

If a new auto-loaded surface appears (say, `.claude/<X>/` directories that the harness consumes), follow the promotion ritual to keep the codebase honest:

1. **Demonstrate recurrence**: N≥3 items already exist OR a forcing function that guarantees N≥3 (e.g. a new harness feature loads 5 docs).
2. **Rename the file**: `eight-way-sync.md` → `nine-way-sync.md`. Mechanical churn but the count IS the point.
3. **Add the surface to the table** in this doc, with load timing.
4. **Add a sub-keeper** for it (mirror `check_skills_listed_in_router` / `check_commands_listed_in_router` / `check_all_cache_freshness`).
5. **Wire into the composition** via `_run_composed_keeper`.
6. **Update CLAUDE.md §1** rule + (if §2 contains the listing) update §2.
7. **Update tests**.
8. **Update CONTEXTUALIZE.md** + the cache-as-agent-tool / agent-context-architecture sibling docs as warranted.

Don't silently promote. The count IS a versioning signal.

## Composes with

- [`claude-md-router-discipline`](claude-md-router-discipline.md) — the §1 pointer-only rule that gates CLAUDE.md re-bloat. This sync's surface #1.
- [`agent-context-architecture`](agent-context-architecture.md) — the L1-INDEX + `owns_kb:` model. This sync's surface #3.
- [`keeper-pattern-cache`](keeper-pattern-cache.md) — the mirror-cache contract that backs the compliance gate. This sync's surface #8 (#1 of the 8 caches).
- [`cache-as-agent-tool`](cache-as-agent-tool.md) — the principle (caches ARE the agent read path) that promoted `.claude/cache/` from referenced sibling to first-class surface.
- [`extractor-correctness-vs-mirror`](extractor-correctness-vs-mirror.md) — sibling pattern naming the residual gap the 8-way doesn't close: structural-mirror correctness (this sync's job) vs. logic correctness of the extractors (separate test surface).
- [`cache-auto-freshness`](cache-auto-freshness.md) — the 4-hook contract guaranteeing the structural mirror; the executable form of the 8-way's surface #8 guarantee.
- [`drift-fix-on-contact`](drift-fix-on-contact.md) — when a surface mismatch is surfaced, FIX in-flight, don't defer.

## Anti-patterns

- **DON'T** add a §1 rule without a depth pointer + ensuring the agent / skill / KB tree the pointer leads to actually contains the depth. Pointer-only discipline ⊥ broken pointers.
- **DON'T** add a KB doc without an INDEX entry + (if always-on relevant) a CLAUDE.md line.
- **DON'T** add a new skill without listing it in CLAUDE.md §2 map.
- **DON'T** add a new cache without a per-cache `check_<name>_cache_freshness` keeper + wiring into `check_all_cache_freshness` (silent cache = consumption-layer drift).
- **DON'T** silently expand the surface count to 9+. Promote `eight-way-sync` to `nine-way-sync` LOUDLY with a new keeper rev.
- **DON'T** conflate structural freshness with extractor correctness. A green `check_all_cache_freshness` means "cache is in-sync with source"; it does NOT mean "the extractor's logic is right". See [extractor-correctness-vs-mirror](extractor-correctness-vs-mirror.md).

## History

This pattern formalizes what was previously called "three-way sync" (CLAUDE.md / KB / agent context). The surface count grew over time:
- 2026-04: three-way (CLAUDE.md + KB + agent context)
- 2026-05: four-way (added MEMORY.md after the auto-memory layer landed)
- 2026-05 (Phase B): five-way (added CONTEXTUALIZE.md as a sibling of CLAUDE.md for fresh-agent ramp)
- 2026-05-26 (morning): six-way (added `.claude/skills/` as a first-class auto-load methodology surface)
- 2026-05-26 (same-day evening): seven-way (added `.claude/commands/` after the v4.0-beta doc sprint grew it from N=1 to N=6 — the harness auto-loads commands indistinguishably from skills; recurrence rule promoted them to first-class)
- 2026-05-28 (evening): **eight-way** (added `.claude/cache/` after `cache-as-agent-tool` was codified — caches are the live read path; structural mirror guaranteed via 4 git hooks; logic correctness stays a separate test-surface concern per [extractor-correctness-vs-mirror](extractor-correctness-vs-mirror.md))

Each promotion has been a methodology evolution, captured here so future surface additions follow the same path: add the surface + add it to this list + bump the keeper.
