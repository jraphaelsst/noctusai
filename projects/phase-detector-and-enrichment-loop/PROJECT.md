# phase-detector-and-enrichment-loop — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update §11.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Filed → Phase 1 ready
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § PATTERNS/project-execution.md` (where the new methodology rule lands in §2), `KB § PATTERNS/master-tree-parallel-batches.md` (where the cross-reference Improvements convention lands), `KB § PATTERNS/mcp-tool-conventions.md` (governs new MCP tool naming), `mcp/noctusai/tools/noctus/dev/compliance.py` (detector code being fixed in Phase 1), `projects/repo-state-consolidation-wave-2/PROJECT.md` (v2 — gets enriched in Phase 6 with learnings logged via the new SQLite tracker).
- **Project slug:** `phase-detector-and-enrichment-loop` — cross-cutting tooling + methodology project per `KB § PATTERNS/project-execution.md §1`. Lives at root `projects/<slug>/` (no product owns it).

---

## 1. Context & Purpose

While filing `repo-state-consolidation-wave-2`, the pre-commit phase-state detector (`mcp/noctusai/tools/noctus/dev/compliance.py:1102-1135`) flagged two false positives that revealed deeper methodology gaps, not bugs:

1. **The parallel-agent's `erp-imobiliario-wiring` Phase 0 had no `**Improvements:**` block.** Investigation showed Phase 0 had surfaced **plenty** of improvements — they were captured in the master-tree scratchpad (`projects/products-wiring-rollout/live-patterns-log.md` + `cross-product-absorption-catalog.md`) per `KB § PATTERNS/master-tree-parallel-batches.md`, NOT in the child PROJECT.md. The detector was designed for single-project workflows and didn't recognize the cross-reference shape, AND the master-tree KB doc didn't tell child agents to write a cross-reference Improvements block.

2. **My v2 §11 entry triggered a "Phase 0 ✅" detector hit** when describing *another file's* state. The regex `r'Phase\s+(\d+)\s*✅'` matched my reference to the parallel agent's file as if it were a self-claim. I worked around it by rephrasing to "header marked `[checkmark]`" — that's a workaround, not a fix. The **no-workaround rule** says go upstream.

The user also surfaced a third concern: there's no durable mechanism for capturing learnings between phases. Today, learnings live in the agent's context window (evaporates), in §11 prose (semi-durable but unstructured), or in scattered patterns logs (durable but per-project). The user wants a **local SQLite tracker** so phases can produce learnings durably and the next phase can consume them — the foundation for a future cross-project learning system the user has plans for.

The win: detector precision (no false positives), the master-tree workflow has explicit guidance for child Improvements blocks, every phase produces durable learnings the next phase consumes, and the methodology has an explicit "phase enrichment loop" rule. This project also dogfoods itself — Phase 6 logs Phases 1-5's own learnings to the new SQLite tracker, then enriches v2 with those learnings.

---

## 2. Confirmed constraints

Decisions the user made in the 2026-05-03 session.

- **No workaround on the detector regex.** *"please remember our no-workaround rule. find a consistent solid solution."* The regex precision fix must be a structural change, not a sentinel/escape hack. *(Drives Phase 1 design — strip inline code spans before regex match, making backticks the canonical "this is a reference, not a self-claim" marker. No new syntax for users; backticks are already markdown-idiomatic.)*
- **Plan + implement, single commit-and-push at close.** *"please plan this project then implement it... after implementing that project, commit and push."* Per `feedback_no_auto_commit.md`: per-phase local commits, push at project close. The user's "commit and push" maps to the project-close gate. *(Drives commit cadence in §6.)*
- **File or enrich v2 with learnings from v1.** *"file a project for v2 (if not phased already. If so, enrich it with learnings from v1)."* v2 = `repo-state-consolidation-wave-2` (already phased with 7 phases). So Phase 6 here ENRICHES v2's existing PROJECT.md with the learnings from this project's Phases 1-5, rather than filing a new project. *(Drives Phase 6.)*
- **Enrichment between phases is a real methodology rule.** *"every shipped phase must be enriched with new learnings from the past phase."* The rule lands in `KB § PATTERNS/project-execution.md` (auto-loaded surface for execution rules), with a CLAUDE/projects.md pointer + memory entry. Three-way sync. *(Drives Phase 5.)*
- **Local SQLite for learning durability.** *"please, create a local instance of sqlite for storing this data and making it persist locally. I've got future plans for it."* The "future plans" framing means: keep the schema minimal-but-extensible, gitignore the .db file, and expose CRUD via MCP tools so future agents (and the user) can build on it. *(Drives Phase 3 + 4.)*

---

## 3. Design principles

How we're approaching *this specific* tooling + methodology project.

1. **Strip code spans, don't add escape syntax.** The detector's regex precision fix doesn't introduce new conventions — it adopts the existing markdown one. Backtick a phrase = "this is a reference, not prose." A markdown reader sees a code span; the detector treats it the same way (i.e., ignored for self-claim matching). Single source of truth. No new docs except a one-liner added to the detector docstring + the `**Improvements:**`-block guidance in the master-tree KB doc.
2. **SQLite stays local, schema stays minimal.** The .db file is gitignored. Schema is one table (`phase_learnings`) with extensible columns. No ORMs, no migration framework — just `sqlite3.connect()` + raw `CREATE TABLE IF NOT EXISTS`. When the user's "future plans" surface, additional tables / columns get added then; over-engineering now would obscure intent.
3. **MCP tools follow the existing 3-segment convention** (`noctus.dev.<action>`). No new service introduced — these are dev-toolkit tools, same namespace as the rest. Per `KB § PATTERNS/mcp-tool-conventions.md`.
4. **Dogfood in Phase 6.** First real use of the tracker is logging Phases 1-5's own learnings, then having Phase 6 read them to enrich v2. If the workflow is awkward, we discover it on our own work, not on a real project.
5. **Methodology rule is short + actionable.** The "phase enrichment loop" rule in KB is ≤200 words with a clear when/how/why. CLAUDE.md gets a single bullet + KB pointer per the auto-loaded budget rule (`feedback_context_budget_discipline.md`).
6. **Master-tree KB doc enrichment is a single new subsection**, not a rewrite. Add §2.5 "Cross-reference Improvements blocks in child phases" between existing §2.4 and §3. Document the convention + give the canonical example (the working-tree fix already applied to `erp-imobiliario-wiring` Phase 0).

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** N/A — this is platform-level tooling + methodology, not a product feature. The detector + tracker are repo-wide.
2. **Is the data source product-specific?** N/A. The SQLite db spans projects, not products.
3. **Is the placement product-specific?** N/A.
4. **Is the visibility / permission rule the same?** N/A (local dev tool; no RLS).
5. **Does the seam already exist in seed?** No — this is dev-toolkit territory (`mcp/noctusai/`), not a product seed concern.
6. **Default-on or opt-in?** **Default-on once landed.** The methodology rule applies platform-wide; the detector is in the pre-commit hook. Opt-out doesn't make sense — the cost of a missed-learning is exactly the slip the rule is preventing.

**Litmus — per-product code count this design requires:** [x] **0 lines** in any `products/<x>/` tree. All code lands in `mcp/noctusai/`, `KNOWLEDGE-BASE/`, `CLAUDE/`, and `~/.claude/projects/.../memory/`.

**Phase plan implications:** §6 phases work in the dev-toolkit + KB + CLAUDE auto-loaded surfaces. **No phase walks through products.** Correct shape.

---

## 4. Scope

**In scope:**

- Phase 1 — Detector regex precision: strip inline code spans in `_shipped_phases_in_changelog`. Add unit tests for self-claim vs. backtick-wrapped-reference. Update detector docstring.
- Phase 2 — `KB § PATTERNS/master-tree-parallel-batches.md`: new §2.5 "Cross-reference Improvements blocks in child phases" with worked example.
- Phase 3 — SQLite tracker: `mcp/noctusai/data/phase_learnings.db` schema + `mcp/noctusai/tools/noctus/dev/phase_learnings.py` helper module (init / log / query / consume). Gitignore the .db file.
- Phase 4 — MCP tool exposure: `noctus.dev.phase_learning_log`, `noctus.dev.phase_learning_query`, `noctus.dev.phase_learning_consume`. Pydantic schemas. Tests.
- Phase 5 — Methodology rule: new section in `KB § PATTERNS/project-execution.md` (e.g., §2.11 "Phase enrichment loop"), pointer in `CLAUDE/projects.md`, memory entry `feedback_phase_enrichment_loop.md` + `MEMORY.md` index line. Three-way sync.
- Phase 6 — Dogfood + enrich v2: log Phases 1-5 learnings to the new tracker; enrich `projects/repo-state-consolidation-wave-2/PROJECT.md` §6 with relevant learnings; add v2 §11 entry pointing to v1.
- Phase 7 — Project close: verify all green; folder delete; final commit + `git push origin main`.

**Out of scope (for now — with reason):**

- **Other detector improvements** (e.g. multi-row §11 phase-attribution, phase numbering gaps, header-icon validation) — separate project; this one is precision-focused.
- **Other methodology rules** — one rule per project to avoid scope creep.
- **Backfill SQLite with historical learnings** — the tracker starts empty. First entries are Phases 1-5's own learnings (Phase 6).
- **v2 phase-by-phase execution** — v2's own §6 is for v2's pickup agent. Phase 6 here only ENRICHES v2's plan with learnings, doesn't execute v2's work.
- **Cross-machine SQLite sync** — local-only per user directive. Future plans (per §2) may add a sync layer; not now.
- **MCP tool exposure for SQLite querying outside the dev toolkit** — the user's future plans may add a UI; not in this project.
- **Updating the parallel agent's erp-imobiliario-wiring file in git** — their file stays untracked. The working-tree cross-reference body I added stays in working tree only; they own the next commit on it.

---

## 5. Architecture / Data Model

### 5.1 Detector regex precision (Phase 1)

Current `_shipped_phases_in_changelog` regex (compliance.py:1102-1135) runs against the full `§11 Change log` text. Two patterns:

```python
# Pattern A — Phase N immediately followed by ✅
r'Phase\s+(\d+)\s*✅'

# Pattern B — Phase N then within 80 chars (no period) "shipped/closed/complete"
r'Phase\s+(\d+)\b[^.]{0,80}?(?:shipped|closed|complete)'
```

False positive: any §11 prose mentioning "Phase 0 ✅" or "Phase 1 closed" of *another file* matches as if it were a self-claim.

**Fix shape (no workaround):** preprocess the changelog text to strip inline code spans before regex matching. Markdown convention: backticks delimit "this is code/identifier/reference, not prose." A `\`Phase 0 ✅\`` reference becomes invisible to the detector; an unbacked "Phase 0 ✅" remains visible. No new syntax for the user.

```python
# Helper
_INLINE_CODE_SPAN_RE = re.compile(r'`[^`\n]*`')

def _strip_code_spans(text: str) -> str:
    """Strip inline code spans (backtick-delimited) from markdown text.

    Used to normalize before phase-shipped detection so cross-file
    references don't trigger self-claim heuristics.
    """
    return _INLINE_CODE_SPAN_RE.sub(" ", text)
```

`_shipped_phases_in_changelog` calls `_strip_code_spans` before each regex pass.

**Tests** (extend `mcp/noctusai/tests/test_compliance.py`):

| Case | Input fragment | Expected behavior |
|---|---|---|
| Self-claim | `Phase 1 ✅ shipped 2026-05-03` | Phase 1 in shipped set |
| Backticked reference | `flagged \`Phase 0 ✅\` in another file` | Phase 0 NOT in shipped set |
| Mixed | `Phase 2 ✅ this; \`Phase 0 ✅\` other` | Phase 2 in set; Phase 0 not |
| Multi-line backtick | (across newlines — code span doesn't span lines per markdown) | Multi-line `\`...\`` doesn't suppress |

### 5.2 Master-tree KB doc — new §2.5 (Phase 2)

Insert between existing §2.4 (Post-batch consolidation) and §3 (Live shared artifacts). Title: **"Cross-reference Improvements blocks in child phases."** Body covers:

- The convention: child phases write `**Improvements:** see <master-scratchpad-path> (...specific items...). Cross-references rather than duplicates so the master root remains canonical.`
- Why: avoids duplication; aligns with §2.3 ("inline-applied improvements file in child §11" + master scratchpad as canonical).
- Worked example: ERP-imobiliario-wiring Phase 0 (the in-working-tree fix already applied — quote it exactly).
- The detector accepts this shape — see Phase 1 of this project.

### 5.3 SQLite phase-learnings schema (Phase 3)

```sql
-- mcp/noctusai/data/phase_learnings.db
CREATE TABLE IF NOT EXISTS phase_learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_slug TEXT NOT NULL,
    phase_number INTEGER NOT NULL,
    phase_title TEXT,
    learning_kind TEXT,         -- 'methodology' | 'technical' | 'process' | 'tool' | 'other'
    learning_text TEXT NOT NULL,
    shipped_at TEXT NOT NULL,   -- ISO 8601 timestamp
    consumed_by_phase_number INTEGER,
    consumed_at TEXT,
    created_by TEXT             -- agent identity, e.g. 'claude-opus-4-7'
);

CREATE INDEX IF NOT EXISTS idx_phase_learnings_project_slug ON phase_learnings(project_slug);
CREATE INDEX IF NOT EXISTS idx_phase_learnings_unconsumed ON phase_learnings(project_slug, consumed_by_phase_number);
```

Helper module `mcp/noctusai/tools/noctus/dev/phase_learnings.py`:

| Function | Signature | Purpose |
|---|---|---|
| `get_db_path` | `() -> Path` | Returns path; respects `NOCTUS_PHASE_LEARNINGS_DB` env override for tests |
| `_init_db` | `(conn: sqlite3.Connection) -> None` | Idempotent schema apply |
| `log_learning` | `(project_slug, phase_number, phase_title, learning_kind, learning_text, created_by) -> int` | Insert row, return id |
| `query_learnings` | `(project_slug, phase_number=None, unconsumed_only=False) -> list[dict]` | List rows |
| `consume_learning` | `(learning_id, by_phase_number) -> bool` | Mark consumed |

`.gitignore` entry: `mcp/noctusai/data/`. Add to root .gitignore alongside the existing patterns.

### 5.4 MCP tools (Phase 4)

Per `KB § PATTERNS/mcp-tool-conventions.md` — Pydantic schemas, dotted naming, lazy context.

| Tool name | Args | Returns |
|---|---|---|
| `noctus.dev.phase_learning_log` | `project_slug: str, phase_number: int, phase_title: str \| None, learning_kind: str, learning_text: str` | `{ "id": int }` |
| `noctus.dev.phase_learning_query` | `project_slug: str, phase_number: int \| None = None, unconsumed_only: bool = False` | `{ "learnings": [ { ...row... } ] }` |
| `noctus.dev.phase_learning_consume` | `learning_id: int, by_phase_number: int` | `{ "consumed": bool }` |

`created_by` is auto-populated from a context default ("claude-opus-4-7" or env override).

### 5.5 Methodology rule (Phase 5)

`KB § PATTERNS/project-execution.md` gets a new section §2.11 "Phase enrichment loop":

> **The rule.** When a phase ships, capture **at least one** learning discovered during the phase via `noctus.dev.phase_learning_log`. Before opening the next phase, query unconsumed learnings via `noctus.dev.phase_learning_query` — fold the relevant ones into the next phase's plan, then call `noctus.dev.phase_learning_consume`. Learnings that would benefit other projects (cross-cutting) get promoted to the absorption catalog or filed as follow-up projects.
>
> **Why.** The recurrence rule (DRY) only fires when learnings are durable. A learning that lives in the agent's context window evaporates with that context. A learning that lives in §11 prose is durable but unstructured — hard to query, hard to consume mechanically. The SQLite tracker makes "what did the previous phase teach us?" a one-liner, which makes the consumption habit cheap.
>
> **What counts as a learning.** Any non-obvious insight: a methodology gap discovered (Phase 1's detector quirk), a tool that didn't behave as expected (Phase 3's SQLite path), a pattern that recurred (when Phase N+1 trips on the same shape Phase N flagged). Trivial restatements of "we did X" don't count — those go in §11 prose.

`CLAUDE/projects.md` gets one bullet:
> **Phase enrichment loop** — every shipped phase logs ≥1 learning via `noctus.dev.phase_learning_log`; the next phase consumes via `noctus.dev.phase_learning_query`. Durability without prose-archeology. → `KB § PATTERNS/project-execution.md § 2.11`.

Memory: `feedback_phase_enrichment_loop.md` with body "rule + Why + How to apply" per the feedback memory shape. `MEMORY.md` index line.

### 5.6 v2 enrichment (Phase 6)

For each of v2's 7 phases (`repo-state-consolidation-wave-2`), check the unconsumed learnings DB for relevant entries and add a brief cross-reference to v2's §6. Add a §11 entry to v2 logging "enriched 2026-05-03 with learnings from `phase-detector-and-enrichment-loop` (commit `<hash>`)."

---

## 6. Implementation phases

### Phase 0 — File this project

- [x] Write `projects/phase-detector-and-enrichment-loop/PROJECT.md`.
- [x] Create proposals/.gitkeep.
- [ ] Stage + commit: `docs(projects): file phase-detector-and-enrichment-loop [phase-detector-and-enrichment-loop file]`.

**Improvements:** captured in Phase 6 alongside Phase 1-5 learnings — the filing process surfaced one (the slug-naming question — chose `phase-detector-and-enrichment-loop` after considering `methodology-evolution-2026-05-03` and `phase-state-detector-precision-and-enrichment-loop`; trade-off is descriptiveness vs. length).

### Phase 1 — Detector regex precision

- [ ] Add `_INLINE_CODE_SPAN_RE` + `_strip_code_spans` helper to `compliance.py`.
- [ ] Refactor `_shipped_phases_in_changelog` to call `_strip_code_spans(changelog)` before each regex pass.
- [ ] Update detector docstring to mention the convention: "wrap cross-file references in backticks to prevent self-claim matching."
- [ ] Add 4 unit tests to `mcp/noctusai/tests/test_compliance.py` covering the §5.1 cases.
- [ ] Run `cd mcp/noctusai && python -m pytest tests/test_compliance.py -q` — must be green.
- [ ] Run `cd mcp/noctusai && python -m pytest tests/ -q` — full suite must stay green (baseline 564 passed).
- [ ] Commit: `fix(mcp): detector regex strips code spans before phase-shipped match — backticked references no longer trigger false positives [phase-detector-and-enrichment-loop Phase 1]`.

### Phase 2 — Master-tree KB doc enrichment

- [ ] Insert new §2.5 "Cross-reference Improvements blocks in child phases" in `KB § PATTERNS/master-tree-parallel-batches.md` between existing §2.4 and §3.
- [ ] Body covers: convention, rationale, worked example (quote the working-tree fix exactly).
- [ ] Run `bash scripts/verify-kb-sync.sh` — must stay green.
- [ ] Run `python scripts/update-kb-counts.py --check` — must stay green.
- [ ] Commit: `docs(kb): master-tree-parallel-batches §2.5 — cross-reference Improvements blocks in child phases [phase-detector-and-enrichment-loop Phase 2]`.

### Phase 3 — SQLite phase-learnings tracker

- [ ] Create `mcp/noctusai/tools/noctus/dev/phase_learnings.py` with the §5.3 schema + helper functions.
- [ ] Add `mcp/noctusai/data/` to root `.gitignore`.
- [ ] Add 5 unit tests to `mcp/noctusai/tests/test_phase_learnings.py` (init, log, query-all, query-unconsumed, consume).
- [ ] Run `cd mcp/noctusai && python -m pytest tests/test_phase_learnings.py -q` — green.
- [ ] Run full suite — green.
- [ ] Commit: `feat(mcp): SQLite phase-learnings tracker (init / log / query / consume) [phase-detector-and-enrichment-loop Phase 3]`.

### Phase 4 — MCP tool exposure

- [ ] Wrap the helper functions as MCP tools with Pydantic argument schemas, registered via the per-file `register(server)` pattern (per `KB § PATTERNS/mcp-tool-conventions.md`).
- [ ] Add 3 unit tests to verify tool registration + arg validation.
- [ ] Run full suite — green.
- [ ] Run `python mcp/noctusai/cli.py noctus.dev.phase_learning_log --project=test --phase=0 --kind=tool --text="smoke test"` (or equivalent) — verify CLI path works too.
- [ ] Commit: `feat(mcp): noctus.dev.phase_learning_{log,query,consume} MCP tools [phase-detector-and-enrichment-loop Phase 4]`.

### Phase 5 — Methodology rule (3-way sync)

- [ ] KB: add §2.11 "Phase enrichment loop" to `KB § PATTERNS/project-execution.md` per §5.5 spec.
- [ ] CLAUDE.md / topical: add the one-bullet pointer in `CLAUDE/projects.md` (most relevant topical for execution rules).
- [ ] Memory: write `feedback_phase_enrichment_loop.md` with frontmatter + body (rule, Why, How to apply). Add MEMORY.md index line under "Project execution" cluster.
- [ ] Run `bash scripts/verify-kb-sync.sh` — must stay green.
- [ ] Commit: `docs(kb+claude+memory): phase enrichment loop rule (3-way sync) [phase-detector-and-enrichment-loop Phase 5]`.

### Phase 6 — Dogfood: log v1 learnings + enrich v2

- [ ] For each of Phases 1-5 here, call `noctus.dev.phase_learning_log` with project=`phase-detector-and-enrichment-loop`, the phase number, kind, and a 1-2-sentence learning. (At minimum: Phase 1 learning about "no-workaround applies to detector regex precision"; Phase 2 about "master-tree children write cross-reference Improvements blocks"; Phase 3 about "local SQLite is sufficient for in-session phase-learnings durability"; Phase 4 about "MCP tool exposure follows existing `noctus.dev.<action>` shape, no new service needed for dev tooling"; Phase 5 about "three-way sync requires 3 separate edits in same session — easy to skip the memory line.")
- [ ] Query: `noctus.dev.phase_learning_query --project=phase-detector-and-enrichment-loop` returns 5 entries.
- [ ] Edit `projects/repo-state-consolidation-wave-2/PROJECT.md`:
  - §6 Phase 0: add a sub-task pointing to relevant new-detector behavior + new tracker (e.g. "If §11 references another file's `Phase N ✅`, wrap in backticks per Phase 1 of `phase-detector-and-enrichment-loop`. Log Phase 0 learnings via `noctus.dev.phase_learning_log` per `KB § PATTERNS/project-execution.md § 2.11`.").
  - §6 final phase: add the close-out sub-task for the phase-enrichment-loop discipline.
  - §11: new entry — "enriched 2026-05-03 with learnings from `phase-detector-and-enrichment-loop` Phases 1-5 (commit `<hash>`)."
- [ ] Mark v2's relevant SQLite learnings as consumed via `noctus.dev.phase_learning_consume`.
- [ ] Commit: `docs(projects): enrich repo-state-consolidation-wave-2 with v1 learnings + new phase-enrichment-loop discipline [phase-detector-and-enrichment-loop Phase 6]`.

### Phase 7 — Project close

- [ ] Run final verification:
  - `cd mcp/noctusai && python -m pytest tests/ -q | tail -3` (must be green; expect ~570+ passed)
  - `bash scripts/verify-kb-sync.sh` (green)
  - `python scripts/update-kb-counts.py --check` (green)
  - `git status --short` — confirm no surprise un-staged work outside this project's scope
- [ ] `git rm -r projects/phase-detector-and-enrichment-loop/`
- [ ] Final commit: `chore(projects): phase-detector-and-enrichment-loop close — folder delete (project close) [phase-detector-and-enrichment-loop close]`
- [ ] Verify `git log origin/main..HEAD --oneline` — only this project's commits + v2-enrichment commit (8 commits total expected: file + 6 phase commits + close).
- [ ] `git push origin main` — final step.

---

## 7. Open questions

None remaining — every fix has a confirmed §6 sub-task + §5 spec. If the executing pass surfaces an ambiguity (e.g. SQLite schema needs a column we didn't anticipate), surface BEFORE the corresponding phase commits per `feedback_no_silent_errors.md`.

---

## 8. Dependencies & blockers

- **None blocking.** Detector code is in tree (commit `7e7e28d` HEAD), tests fixture exists at `mcp/noctusai/tests/test_compliance.py`, KB doc structure is in tree, methodology auto-loaded surfaces are in tree.
- **One coordination check** — `repo-state-consolidation-wave-2/PROJECT.md` (v2) is tracked at HEAD. Phase 6 edits it — verify no parallel agent has staged edits to it before Phase 6 commit. (Working-tree status check.)

---

## 9. Success criteria

- [ ] `_strip_code_spans` lands; 4+ regression tests cover the §5.1 cases; `cd mcp/noctusai && pytest tests/test_compliance.py -q` green.
- [ ] `KB § PATTERNS/master-tree-parallel-batches.md` §2.5 exists and renders cleanly.
- [ ] `mcp/noctusai/data/phase_learnings.db` initializes on first call; CRUD tests green; .gitignored.
- [ ] 3 MCP tools registered + accessible via the `noctus.dev.phase_learning_*` namespace; tests green.
- [ ] `KB § PATTERNS/project-execution.md` §2.11 lands; `CLAUDE/projects.md` pointer; memory entry + `MEMORY.md` index line. `verify-kb-sync.sh` green.
- [ ] v2 PROJECT.md enriched with v1 learnings (Phase 0 sub-task + final-phase sub-task + §11 entry).
- [ ] Project folder deleted; final commit + `git push origin main` lands.
- [ ] `git log origin/main..HEAD --oneline` returns 0 lines after push (everything pushed).

---

## 10. How to use this plan

```bash
# Pre-flight
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
git status --short
cd mcp/noctusai && python -m pytest tests/ -q | tail -3 && cd ../..   # baseline

# Phase 1 — detector regex precision
# Edit mcp/noctusai/tools/noctus/dev/compliance.py per §5.1
# Edit mcp/noctusai/tests/test_compliance.py per §5.1 cases
cd mcp/noctusai && python -m pytest tests/test_compliance.py -q && cd ../..
git add mcp/noctusai/tools/noctus/dev/compliance.py mcp/noctusai/tests/test_compliance.py
git commit -m "fix(mcp): detector regex strips code spans before phase-shipped match — backticked references no longer trigger false positives [phase-detector-and-enrichment-loop Phase 1]"

# Phase 2 — KB doc
# Edit KNOWLEDGE-BASE/CONTEXT/PATTERNS/master-tree-parallel-batches.md per §5.2
bash scripts/verify-kb-sync.sh
python scripts/update-kb-counts.py --check
git add KNOWLEDGE-BASE/CONTEXT/PATTERNS/master-tree-parallel-batches.md
git commit -m "docs(kb): master-tree-parallel-batches §2.5 — cross-reference Improvements blocks in child phases [phase-detector-and-enrichment-loop Phase 2]"

# Phase 3 — SQLite tracker
# Create mcp/noctusai/tools/noctus/dev/phase_learnings.py per §5.3
# Edit .gitignore
# Create mcp/noctusai/tests/test_phase_learnings.py
cd mcp/noctusai && python -m pytest tests/test_phase_learnings.py -q && cd ../..
git add mcp/noctusai/tools/noctus/dev/phase_learnings.py mcp/noctusai/tests/test_phase_learnings.py .gitignore
git commit -m "feat(mcp): SQLite phase-learnings tracker (init / log / query / consume) [phase-detector-and-enrichment-loop Phase 3]"

# Phase 4 — MCP tools
# Edit phase_learnings.py to add register(server) per §5.4
# Edit tests
cd mcp/noctusai && python -m pytest tests/ -q && cd ../..
git add mcp/noctusai/tools/noctus/dev/phase_learnings.py mcp/noctusai/tests/
git commit -m "feat(mcp): noctus.dev.phase_learning_{log,query,consume} MCP tools [phase-detector-and-enrichment-loop Phase 4]"

# Phase 5 — methodology rule (3-way sync)
# Edit KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md
# Edit CLAUDE/projects.md
# Create ~/.claude/projects/.../memory/feedback_phase_enrichment_loop.md
# Edit ~/.claude/projects/.../memory/MEMORY.md
bash scripts/verify-kb-sync.sh
git add KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md CLAUDE/projects.md
git commit -m "docs(kb+claude+memory): phase enrichment loop rule (3-way sync) [phase-detector-and-enrichment-loop Phase 5]"

# Phase 6 — dogfood + enrich v2
python mcp/noctusai/cli.py noctus.dev.phase_learning_log --project=phase-detector-and-enrichment-loop --phase=1 --kind=technical --text="..."
# (repeat for phases 2-5)
python mcp/noctusai/cli.py noctus.dev.phase_learning_query --project=phase-detector-and-enrichment-loop
# Edit projects/repo-state-consolidation-wave-2/PROJECT.md per §5.6
git add projects/repo-state-consolidation-wave-2/PROJECT.md
git commit -m "docs(projects): enrich repo-state-consolidation-wave-2 with v1 learnings + new phase-enrichment-loop discipline [phase-detector-and-enrichment-loop Phase 6]"

# Phase 7 — close
cd mcp/noctusai && python -m pytest tests/ -q | tail -3 && cd ../..
bash scripts/verify-kb-sync.sh
python scripts/update-kb-counts.py --check
git rm -r projects/phase-detector-and-enrichment-loop/
git commit -m "chore(projects): phase-detector-and-enrichment-loop close — folder delete (project close) [phase-detector-and-enrichment-loop close]"
git log origin/main..HEAD --oneline
git push origin main
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Project filed by claude-opus-4-7 after surfacing two methodology gaps while filing v2 (`repo-state-consolidation-wave-2`): detector regex precision (false-positive on cross-file `Phase N ✅` references) + master-tree workflow gap (children should write cross-reference Improvements blocks; doc didn't say so). User added: durable phase-learnings tracking via local SQLite + new methodology rule "every shipped phase enriches the next phase with learnings." Single-session implementation; commit-and-push at project close per user explicit-delegation. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

This project's success requires:

- **Folder `projects/phase-detector-and-enrichment-loop/` deleted on close** per `CLAUDE/projects.md § Commit per phase, push at project close` apply-inline-then-delete methodology.
- **Final commit + push** must include only this project's commits (`[phase-detector-and-enrichment-loop ...]` bracketed). Verify with `git log origin/main..HEAD --oneline` before push. No other agent's work touched.
- **No new untracked files** introduced by this project, except the gitignored `mcp/noctusai/data/phase_learnings.db` (intentional; gitignored).
- **Memory entry persists across sessions** — `feedback_phase_enrichment_loop.md` lives in `~/.claude/projects/.../memory/`, not gitignored; the methodology rule survives any folder delete here.
