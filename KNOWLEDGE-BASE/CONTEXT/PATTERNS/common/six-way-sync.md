# Six-way sync — the methodology surface contract

**What it is.** A formal sync contract across the six **first-class methodology surfaces** in this codebase. Changing one without aligning the others is structural drift — the codebase becomes inconsistent with what an agent or developer reads in CLAUDE.md / KB / agent files / etc. Born 2026-05-26 (promotion from the legacy "three-way sync" rule after the methodology surface count grew to six).

## The six surfaces

| # | Surface | What it carries | Load timing |
|---|---|---|---|
| 1 | **`CLAUDE.md`** | Always-on router (§1 principles + §2 map) | Every session, every reply |
| 2 | **`MEMORY.md`** (auto-memory) | Per-user behavioral rules + project state | Every reply (system reminder) |
| 3 | **`.claude/agents/<name>.md`** | Specialist L1 INDEX + `owns_kb:` declarations | Dispatch time (per agent) |
| 4 | **`KNOWLEDGE-BASE/`** (tree) | Methodology depth — patterns, integrations, guides, per-product detail | On-demand (consulted via grep / kb_search / agent_context cache) |
| 5 | **`CONTEXTUALIZE.md`** | Fresh-agent read map (pointer-only) | Session start when `/contextualize` skill triggers |
| 6 | **`.claude/skills/<name>/SKILL.md`** | Procedural skill bodies — auto-trigger on phrases | Session start (auto-load) + at trigger phrase |

These six are **first-class methodology surfaces**: an agent reading any one of them should arrive at a consistent picture. A rule added to CLAUDE.md §1 that isn't reflected in the relevant skill OR isn't backed by a KB doc OR isn't carried in the right agent's `owns_kb` IS drift.

## What's NOT in the 6-way

These are **referenced** by the methodology surfaces but aren't themselves first-class methodology carriers:

- `.claude/commands/<name>.md` — slash commands. User-invoked, not auto-loaded. Mentioned in CLAUDE.md but methodology details live elsewhere.
- `scripts/hooks/pre-commit` — executable gate. Implements but doesn't define methodology.
- `mcp/noctusai/tools/noctus/dev/compliance.py` — keeper code. The EXECUTABLE form of the rules. The pre-commit hook calls into it; the rules' canonical statement is in CLAUDE.md §1 + KB.
- `mcp/noctusai/cli.py` — CLI flags. Surface for the keeper executions, not the rules themselves.

These are gated by their own contracts (pre-commit hook itself runs each cli flag → any mismatch fails LOUD). They don't need to be members of the 6-way sync because they don't carry methodology PROSE that can independently drift.

## The sync contract

Adding or modifying a methodology rule MUST touch all surfaces where it applies, in the SAME commit:

| Type of change | Surfaces that MUST update together |
|---|---|
| New §1 rule in CLAUDE.md | + KB pattern doc + at least one referenced skill/agent/INDEX if it points to those |
| New KB pattern doc | + KB INDEX.md + CLAUDE.md §1 pointer (if always-on relevant) + agent `owns_kb:` (if a specialist owns the territory) |
| New `.claude/skills/<name>/SKILL.md` | + CLAUDE.md §2 map listing + procedure-references current |
| Agent body change | + agent's `owns_kb:` declarations match body content |
| Auto-load doc (CLAUDE.md / CONTEXTUALIZE.md) change | + counts + canonical-cores still cross-resolvable |
| New keeper (compliance.py) | + CLI flag in cli.py + pre-commit hook leg + CLAUDE.md §1 rule (if always-on) + KB doc + test |

## Keeper enforcement

`check_six_way_sync` (severity `high` — methodology drift IS a correctness issue at the agent-context layer).

**What it checks** (per the canonical surface predicates):

1. **`CLAUDE.md`**: every `KB §` pointer resolves to a real file under `KNOWLEDGE-BASE/`.
2. **`CONTEXTUALIZE.md`**: every canonical-core entry in compliance.py's `_CONTEXTUALIZE_CANONICAL_CORES` is referenced.
3. **`KNOWLEDGE-BASE/INDEX.md`**: every KB doc on disk is indexed (via the existing `kb_sync` gate).
4. **`.claude/agents/<name>.md`**: every `owns_kb:` entry resolves; not in `_AGENT_KB_UNOWNED_ALLOWLIST` unless commons.
5. **`.claude/skills/<name>/SKILL.md`**: every skill listed in CLAUDE.md §2 maps to a directory containing `SKILL.md`.
6. **`MEMORY.md`**: index lines ≤ ~200 chars (existing `check_memory_md_index` discipline).

The keeper is a **composition** of existing checks + the new surface-presence check for skills. Reuses the established sub-keepers:
- `check_kb_sync` (#1, #3)
- `check_contextualize_alignment` (#2)
- `check_agent_kb_alignment` (#4)
- `check_memory_md_index` (#6)
- NEW: `check_skills_listed_in_router` (#5) — surfaces skill-set drift between CLAUDE.md §2 listings and the actual `.claude/skills/<name>/SKILL.md` files on disk.

## Composes with

- [`claude-md-router-discipline`](claude-md-router-discipline.md) — the §1 pointer-only rule that gates CLAUDE.md re-bloat. This sync's surface #1.
- [`agent-context-architecture`](agent-context-architecture.md) — the L1-INDEX + `owns_kb:` model. This sync's surface #3.
- [`keeper-pattern-cache`](keeper-pattern-cache.md) — the mirror-cache contract that backs the compliance gate.
- [`drift-fix-on-contact`](drift-fix-on-contact.md) — when a surface mismatch is surfaced, FIX in-flight, don't defer.

## Anti-patterns

- **DON'T** add a §1 rule without a depth pointer + ensuring the agent / skill / KB tree the pointer leads to actually contains the depth. Pointer-only discipline ⊥ broken pointers.
- **DON'T** add a KB doc without an INDEX entry + (if always-on relevant) a CLAUDE.md line.
- **DON'T** add a new skill without listing it in CLAUDE.md §2 map.
- **DON'T** silently expand the surface count to 7+. Promote `six-way-sync` to `seven-way-sync` LOUDLY with a new keeper rev.

## History

This pattern formalizes what was previously called "three-way sync" (CLAUDE.md / KB / agent context). The surface count grew over time:
- 2026-04: three-way (CLAUDE.md + KB + agent context)
- 2026-05: four-way (added MEMORY.md after the auto-memory layer landed)
- 2026-05 (Phase B): five-way (added CONTEXTUALIZE.md as a sibling of CLAUDE.md for fresh-agent ramp)
- 2026-05-26: six-way (added `.claude/skills/` as a first-class auto-load methodology surface, after the keeper-pattern cache surfaced its load-bearing role)

Each promotion has been a methodology evolution, captured here so future surface additions follow the same path: add the surface + add it to this list + bump the keeper.
