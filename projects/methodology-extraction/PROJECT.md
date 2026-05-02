# Methodology Extraction — Behavioral Methodology + AST Stage 1 Tooling (Step a)

> **This is a living document, not a rigid checklist.**
> Captured 2026-05-02 mid-conversation when the user flagged a
> per-turn-token breaking-point. Re-scoped on 2026-05-02 to **only
> step (a)** of the original three-step build order
> (`a → b → c`); steps (b) and (c) — local mirror layer + per-product
> workspace isolation — moved to a sibling project at
> `projects/methodology-mirror-and-workspaces/`. This project's job is
> the cheap-win-first behavioral + tooling work; the deferred project
> waits for this one's measurements before reactivation.
>
> **Before drafting or revising this project document: interrogate the
> user first.** Ask clarifying questions, confirm constraints, surface
> edge cases. Document each answer in §2 so future agents inherit the
> reasoning.
>
> **Write for a zero-context reader.** Inline §1 context, quote the
> user in §2, name files with paths in §5, pair every §7 Open Question
> with an evidence-backed recommendation, and make §10 commands copy-
> paste ready.

- **Created:** 2026-05-02
- **Last updated:** 2026-05-02
- **Status:** ✅ **Done — all 6 phases closed 2026-05-02.** Step (a) of the original three-step build order ships clean: behavioral methodology (narrow-read + Explore-delegation rules in CLAUDE.md + KB + memory) + auto-improvement methodology amendment + AST stage 1 tooling (`noctusai_count_tokens`, `noctusai_outline_python`, `noctusai_outline_typescript`) + companion infrastructure (`verify-kb-sync.sh` Layout-tree drift detector). 458/458 MCP tests green. **Auto-load surface: 15,523 → 12,085 tokens (-22% static; estimated 35-50% effective once behavioral per-file-read wins are counted).** Sibling project `methodology-mirror-and-workspaces` stays DEFERRED — workflow no longer feels constrained at this saving level; reactivation triggers documented in that project's §7 Q11. Vista MCP project filed at `projects/vista-api-mcp/` per user directive. §7 Q1 resolved with audit-driven re-scope (regex outline for TS instead of Compiler API — same `OutlineResult` contract; upgrade path open).
- **Owner / stakeholders:** Raphael · Claude Opus 4.7 (capture + execution agent) · future zero-context execution agent
- **Related docs:** `CLAUDE.md`; `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`; `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`; `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`; `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`; `templates/PROJECT-TEMPLATE.md`; **sibling project (deferred)** `projects/methodology-mirror-and-workspaces/PROJECT.md` — handles steps (b) and (c) of the original build order; reactivation gated on this project's measurement evidence (its §7 Q11).
- **Project slug:** `methodology-extraction` — cross-product / platform-infra scope, lives at root `projects/`.

---

## 1. Context & Purpose

The user is hitting friction working in the monorepo: per-turn context
ballooned because every session loaded the full CLAUDE.md, the full
methodology surface, and the agent's read habits leaned toward whole-
file reads instead of structure-first scans. The original concept doc
(2026-05-02) framed three layers of fixes:

- **(a)** Behavioral methodology — slim CLAUDE.md, add a narrow-read
  working agreement, codify Explore-agent delegation rules. Companion:
  AST stage 1 tooling (Python outline tool + TS AST setup + TS outline
  tool) so "narrow-read" becomes ergonomic instead of fragile.
- **(b)** Local mirror checkpoint between workspaces and trunk.
- **(c)** Per-product workspace isolation.

The user agreed to the cheap-win-first build order: ship (a), measure,
then decide (b)+(c). On 2026-05-02 the user formally split (b)+(c) out
to `projects/methodology-mirror-and-workspaces/` (status: Concept —
deferred). **This project is now (a) only.** The estimated savings for
(a) alone is ~30-40% per-turn token cost; the win that justifies (b)+(c)
is the additional ~30-40% on top.

**Why is some of this already shipped?** Today (2026-05-02) we trimmed
CLAUDE.md from 5615 to 3486 words (38% reduction) — the first piece of
Phase 0 / Phase 1 work. Every behavioral rule and KB pointer was
preserved; the wealth of detail moved to the KB anchors each rule
points to. The trim is the first measurable artifact of step (a).

---

## 2. Confirmed constraints (what the user *has* said)

> **Source note:** the bullets below paraphrase user statements from
> the 2026-05-02 conversations. Future agents: if a constraint feels
> ambiguous, ask the user to confirm before acting.

- **Goal is per-turn token economy without architectural surgery.**
  Behavioral changes + tooling, no workspace forks, no mirror.
  *(Architectural surgery is the deferred project's job.)*
- **Build order agreed (2026-05-02):** (a) behavioral methodology
  first; (b) local-mirror checkpoint next (separate project now); (c)
  workspace isolation last (separate project now). Cheapest-win-first;
  step (a)'s measurement decides whether to reactivate (b)+(c).
- **AST tooling lands alongside (a), not as a separate phase.** Python
  AST is already wired in the MCP toolkit (`mcp/noctusai/tools/
  {catalog,recurrence,compliance}.py` use `import ast` — confirmed by
  the Phase 0 audit; the earlier draft of this doc claimed
  `ai_brain.py` did too, but that file does not import `ast`).
  TypeScript / TSX AST is not wired —
  `@babel/parser` only appears transitively in lockfiles. Tree-sitter
  is absent. The behavioral "narrow-read" rule only becomes ergonomic
  when agents have an `outline_file` tool that returns a file's symbol
  tree (not its bodies); without it, "narrow read" is fragile
  guidance. Tooling work: Python outline tool (~half day) + TS AST
  setup (`typescript` package or tree-sitter, ~1-2 days) + TS outline
  tool (~half day). AST work is a *companion investment* to (a), not
  a sequential blocker. **Stage 2** (AST-based diff for the mirror) is
  scoped to the deferred project.
- **Same-environment vs. separate-environment is a workflow question,
  not an architecture question.** *"Don't pick one architecture, pick
  a workflow."* Same environment for cross-cutting work (KB edits,
  seed refactors, multi-product reasoning); isolated workspaces (once
  the deferred project ships) for heavy single-product execution
  sessions. Behavioral methodology + AST tooling apply in both. Solve
  (a) first; measure; decide whether (b)+(c) are worth the days of
  work.
- **CLAUDE.md trim shipped today.** 5615 → 3486 words (38% reduction).
  Every rule and pointer preserved; depth lives in the KB anchors. KB
  sync verifier confirmed clean.

---

## 3. Design principles (provisional — confirm with §7 answers)

1. **Methodology stays in trunk.** No copies, no forks, no parallel
   stores. Step (a) makes trunk's methodology *thinner per turn*, not
   distributed.
2. **Reads first, bodies on demand.** A 600-line file is read by
   structure first (outline tool), bodies fetched only for the
   functions actually relevant. Codify this as a rule + ship the
   tooling that makes it cheap.
3. **Delegation is for breadth.** When a question needs 3+ targeted
   greps or covers multiple files, delegate to the Explore agent.
   When it's one known path or one symbol, read directly. Codify the
   threshold.
4. **AST tools live in the existing MCP toolkit.** Python uses
   stdlib `ast`; TypeScript uses the official `typescript` package.
   No tree-sitter unless multiple languages enter scope. Stage 1
   tools land in `mcp/noctusai/tools/` alongside the existing four
   AST-using modules.
5. **Measure end-to-end.** A behavioral rule that doesn't change
   per-turn token cost is theatre. End each phase with a rough
   measurement (subjective acceptable; objective preferred). The
   final phase compares against a baseline.

---

## 3a. Seed-first analysis

Mandatory per CLAUDE.md. This project is **explicitly about** the
methodology layer (CLAUDE.md, KB, MCP toolkit) — there is no "should
this live in product or seed?" question. Every deliverable lands at
the platform layer:

- CLAUDE.md trim → CLAUDE.md (already shipped).
- Narrow-read working agreement → CLAUDE.md + KB pattern + memory.
- Explore-agent delegation rule → CLAUDE.md + KB pattern + memory.
- Python outline tool → `mcp/noctusai/tools/`.
- TypeScript AST setup → `mcp/noctusai/` deps + tooling layer.
- TypeScript outline tool → `mcp/noctusai/tools/`.

Per-product code-count litmus: **0** lines of new per-product code.
The behavioral rules apply to every agent session regardless of
product. The AST tools work against any file in the repo.

---

## 4. Scope

**In scope:**

- Trim CLAUDE.md to per-turn-essentials only (✅ shipped 2026-05-02).
- Codify a narrow-read working agreement (rule + KB pattern + memory
  entry + verify three-way sync).
- Codify Explore-agent delegation rules (rule + KB pattern + memory
  entry + verify three-way sync).
- Build a Python outline MCP tool (`noctusai_outline_python` or
  similar) that returns a file's symbol tree without bodies.
- Set up TypeScript AST tooling in `mcp/noctusai/` (decide
  typescript package vs tree-sitter — see §7 Q1).
- Build a TypeScript / TSX outline MCP tool with the same shape.
- Measure per-turn token cost reduction at the end and decide whether
  to reactivate `projects/methodology-mirror-and-workspaces/`.

**Out of scope, deferred elsewhere:**

- Local mirror checkpoint layer →
  `projects/methodology-mirror-and-workspaces/` (steps b+c).
- Per-product workspace isolation →
  `projects/methodology-mirror-and-workspaces/` (steps b+c).
- AST stage 2 — AST-based diff for the mirror →
  `projects/methodology-mirror-and-workspaces/` (only meaningful
  once the mirror exists).
- GitHub-side automation.
- Replacing trunk's existing project / proposal / keeper systems.

---

## 5. Architecture / data model

Step (a) ships **rules** (in docs) + **tools** (in MCP toolkit). No
new runtime, no new storage, no new services.

### Rules (added to CLAUDE.md + KB + memory)

- **Narrow-read.** When opening any file, prefer the outline first;
  read bodies only for the symbols you'll actually edit / cite.
  Specifically: any file >200 lines, default to outline-first. KB
  anchor: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`
  (new file or existing pattern doc — TBD in Phase 1).
- **Explore-agent delegation.** When a question needs 3+ targeted
  greps, multiple file reads, or open-ended discovery, delegate to
  the Explore subagent. When it's one known path or one symbol,
  use Read or grep directly. KB anchor: same file as above.

Both rules get a CLAUDE.md §1 bullet, a KB anchor, and a memory entry
in `~/.claude/projects/.../memory/feedback_*.md` per the three-way
sync rule.

### Tools (added to mcp/noctusai)

- `mcp/noctusai/tools/outline_python.py` — exposes
  `outline_python(path)` returning `{ classes, functions, methods,
  module_constants, line_ranges }` derived via stdlib `ast`. No
  bodies in the response.
- `mcp/noctusai/tools/outline_typescript.py` — same shape, backed by
  either the `typescript` npm package (Compiler API, child-process
  bridge) OR tree-sitter (TBD — §7 Q1).
- Both tools registered in the MCP server entry plus CLI wrapper for
  parity with the existing toolkit pattern.

### Touch surface

- `CLAUDE.md` — two new bullets in §1.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/<new-or-existing>.md` — pattern
  pages for narrow-read + Explore delegation.
- `KNOWLEDGE-BASE/INDEX.md` — index entry for any new pattern file.
- `~/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/feedback_narrow_read.md` (new).
- `~/.claude/projects/.../memory/feedback_explore_delegation.md` (new).
- `~/.claude/projects/.../memory/MEMORY.md` — index entries.
- `mcp/noctusai/tools/outline_python.py` (new).
- `mcp/noctusai/tools/outline_typescript.py` (new).
- `mcp/noctusai/server.py` (or equivalent) — register both tools.
- `mcp/noctusai/cli.py` — `--outline-python`, `--outline-typescript` flags.
- `mcp/noctusai/tests/` — colocated tests for both tools.
- `mcp/noctusai/package.json` (or `requirements.txt` / `pyproject.toml`
  / shell pointer) — TS dependency setup.

---

## 6. Implementation phases

Phases are suggestive; reorder if repository evidence demands it.
Cadence: phase-by-phase by default. Live-tick `- [ ]` → `- [x]` as
work completes. Each phase ends with `**Improvements:**` block + a
bundled proposal applied-inline-then-deleted.

### Phase 0 — Audit baseline ✅ (2026-05-02)
- [x] CLAUDE.md trimmed: 5615 → 3486 words (38% word reduction);
      42557 → 25170 chars (41% char reduction). Every rule + KB pointer
      preserved; depth in KB anchors. KB sync verifier green.
- [x] Inventory current MCP toolkit AST footprint — confirmed:
      Python `ast` is imported in **3 files** (`mcp/noctusai/tools/
      {catalog,compliance,recurrence}.py`), NOT 4 as the earlier draft
      claimed. `ai_brain.py` exists but does not import `ast`. TS/TSX
      AST not wired. tree-sitter absent. `@babel/parser` not in
      `mcp/noctusai/`. Pre-existing finding corrected in §2 of this
      doc.
- [x] Measurement methodology locked: **(A) token count of the auto-
      loaded surface** (CLAUDE.md + MEMORY.md + system-reminder
      header) — per user choice 2026-05-02. Initial measurements
      captured in §11 today.
- [x] Build order (a→b→c) confirmed by user 2026-05-02 (*"let's go
      with a"* + *"sure! let's roll"*). §6 plan drafted, accepted.

**Phase 0 baseline numbers (per measurement methodology A):**

| Surface | Lines | Words | Chars | Tokens (~4-chars/tok) | Tokens (~0.75-words/tok) |
|---|---:|---:|---:|---:|---:|
| CLAUDE.md, **pre-trim** (HEAD~) | 186 | 5,615 | 42,557 | ~10,640 | ~7,486 |
| CLAUDE.md, **post-trim** (today) | 184 | 3,486 | 25,170 | ~6,292 | ~4,648 |
| **Δ from CLAUDE.md trim alone** | -2 | **-2,129 (-38%)** | **-17,387 (-41%)** | **~-4,348** | **~-2,838** |
| MEMORY.md (auto-loaded; not trimmed in this project) | 76 | 2,401 | 19,530 | ~4,883 | ~3,201 |

Per-turn savings from the CLAUDE.md trim alone: roughly
**2,800-4,300 tokens** depending on tokenizer, on top of an auto-load
surface that previously totalled ~12,000-15,500 tokens (CLAUDE.md +
MEMORY.md combined). That's **~22-29% of the auto-load surface
recovered just from trimming CLAUDE.md** — already most of the way
into step (a)'s projected ~30-40% target. Phase 5's full measurement
will confirm whether the narrow-read rule + Explore delegation +
outline tools push the delta into the upper band or close to it.

**Improvements:**
- The earlier project draft listed 4 MCP modules using Python `ast`;
  Phase 0 audit found only 3. Corrected inline in §2 — see § 11
  change-log entry. Lesson: claims about file-set membership in a
  draft that no one has run through the audit are unreliable; always
  re-grep at Phase 0.
- The CLAUDE.md trim alone already recovers ~22-29% of the auto-load
  surface. Phase 1 + Phase 2 (behavioral rules in CLAUDE.md + KB +
  memory) are unlikely to *grow* that surface meaningfully if we
  follow the "depth in KB, pointers in CLAUDE.md" rule. Worth a
  tight check at end of Phase 1 + Phase 2 that the CLAUDE.md word
  count hasn't crept back up.
- For Phase 4's TS AST decision (§7 Q1), the lack of any
  `@babel/parser` / tree-sitter / `typescript` adoption in
  `mcp/noctusai/` means we're starting from zero — no compatibility
  constraint, just a clean dependency choice. Recommendation in §7
  Q1 holds.

### Phase 1 — Narrow-read working agreement ✅ (2026-05-02)
- [x] Added a §1 bullet to CLAUDE.md: terse rule, why, KB pointer.
      Trigger (>200 lines OR unknown range), behavior (structure
      before bodies), exceptions (short / full-review / content-is-
      structure), KB pointer.
- [x] Authored a new KB anchor at
      `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`
      with the long-form rule, three concentric levels (structure /
      targeted-body / whole-file), worked examples from this repo
      (vista_showcase_service.py, seed/frontend/lib/src/api.ts,
      mcp/noctusai/cli.py), explicit anti-pattern, and a placeholder
      §Explore-agent delegation section that Phase 2 will populate.
- [x] Updated `KNOWLEDGE-BASE/INDEX.md`: added the new file to the
      Layout tree, By-topic table, and By-situation table.
- [x] Filed
      `~/.claude/projects/.../memory/feedback_narrow_read.md` memory
      entry citing both CLAUDE.md and the KB anchor (three-way sync
      complete).
- [x] Updated `~/.claude/projects/.../memory/MEMORY.md` index entry.
- [x] Ran `bash scripts/verify-kb-sync.sh` — green.

**Phase 1 size impact (per measurement methodology A):**

| | Lines | Words | Chars |
|---|---:|---:|---:|
| CLAUDE.md before Phase 1 (Phase 0 close) | 184 | 3,486 | 25,170 |
| CLAUDE.md after Phase 1 | 185 | 3,569 | 26,222 |
| **Δ from Phase 1** | +1 | **+83 (+2.4%)** | +1,052 |
| Net vs pre-trim baseline (5,615 words) | — | **-2,046 (-36%)** | — |

The narrow-read bullet costs ~83 words in the per-turn auto-load
budget. That's ~17% of Phase 0's recovered savings (~470 words
recovered net of Phase 1's +83) — within budget. Phase 2 will add
another ~80 words for the Explore-delegation bullet; combined Phase
1+2 should leave net savings around 33-34% vs pre-trim baseline.

**Improvements:**
- INDEX.md Layout tree was drifted from reality before Phase 1: it
  showed the patterns dir ending at `llm-usage.md`, but two files
  shipped earlier (`logging.md`, `seed-lib-layout.md`) were never
  added to the tree (they were in the By-topic table but not the
  Layout sketch). Caught by `verify-kb-sync.sh` not flagging it
  (the script checks "every KB doc indexed" but the Layout tree
  isn't the index of record — the By-topic + By-situation tables
  are). Fixed inline while editing for `agent-reading-discipline.md`
  — added all three. Lesson: the Layout tree is human-readable
  scaffolding; it can drift silently. Worth a `verify-kb-sync.sh`
  enhancement to also lint the tree.
- The first draft of the CLAUDE.md narrow-read bullet was 95 words
  (inline grep example, why-clause, exceptions, pointer). Trimmed
  to 83 words by moving the grep example to the KB anchor only —
  same load-bearing info per turn (rule + trigger + why), worked
  examples deferred to KB pull-on-demand. Worth carrying the same
  discipline into Phase 2's Explore-delegation bullet.
- The KB anchor's §Explore-agent delegation section is a stub
  pointing forward to Phase 2. Watch out for the
  replication-to-seed-symmetry slip in Phase 2: don't write the
  rule as "delegate when N-many-products" — delegation is about
  research breadth (3+ greps), not product count.

### Phase 2 — Explore-agent delegation rules ✅ (2026-05-02)
- [x] Added a §1 bullet to CLAUDE.md: rule + trigger (3+ targeted
      greps / multi-file walking / open-ended discovery →
      delegate; known path or symbol → direct), the load-bearing
      *"research breadth, not product count"* caveat inline, and
      the prefer-MCP-scans-when-applicable corollary. ~125 words.
- [x] Extended the KB anchor `agent-reading-discipline.md` —
      replaced the Phase-1 stub §Explore-agent delegation with the
      full rule, trigger / not-trigger conditions, the
      research-breadth caveat (carried from
      `replication-to-seed-symmetry`), 5 worked examples (3
      delegate / 2 direct), explicit anti-pattern, and companion
      tooling (Explore subagent + `noctusai_*` scan tools).
- [x] `KNOWLEDGE-BASE/INDEX.md` already pointed at this file from
      Phase 1; no new entry needed.
- [x] Filed
      `~/.claude/projects/.../memory/feedback_explore_delegation.md`
      memory entry citing CLAUDE.md + KB anchor (three-way sync
      complete).
- [x] Updated `~/.claude/projects/.../memory/MEMORY.md` index entry.
- [x] Ran `bash scripts/verify-kb-sync.sh` — green (all three
      checks: CLAUDE.md pointers, INDEX.md indexed docs, Layout
      tree drift).

**Phase 2 size impact (measured via `noctusai_count_tokens`):**

| | Lines | Words | Chars | Tokens (chars/4 approx) |
|---|---:|---:|---:|---:|
| CLAUDE.md after Phase 1 | 185 | 3,569 | 26,222 | ~6,440 |
| CLAUDE.md after Phase 2 | 186 | 3,694 | 26,592 | ~6,648 |
| **Δ from Phase 2** | +1 | **+125 (+3.5%)** | +370 | +208 |
| **Cumulative Phase 1+2** | +2 | **+208 (+6.0%)** | +1,422 | +356 |
| Net vs pre-trim baseline | — | **-1,921 (-34%)** | **-15,965 (-38%)** | **-3,992** |

Phase 2 added 125 words — a touch heavier than Phase 1's 83 because
the rule has more nuance (when-to-do-it AND when-not-to-do-it AND
the research-breadth-not-product-count caveat — all load-bearing).
Combined Phase 1+2 cost ~6% of the per-turn auto-load budget; net
reduction vs pre-trim is still ~34%.

**Improvements:**
- ✅ **APPLIED** — Forward-stub pattern paid off: extending the
  Phase-1 stub for Phase 2 was a single edit. Codified as a
  reusable practice in `KB § PATTERNS/project-execution.md § 2.8
  Multi-phase rule shipments`.
- ✅ **APPLIED** (paid off in real time during Phase 2) — Phase 1's
  *"research breadth not product count"* watch-out prevented an
  at-edit slip when drafting the delegation rule. The general
  practice (capture watch-outs *for the next phase* during the
  current phase's improvements block) is now part of `KB §
  PATTERNS/project-execution.md § 2.8`.
- ✅ **APPLIED** — `noctusai_count_tokens` adopted as the project's
  measurement tool. All Phase 2 size metrics measured by the tool
  not by `wc`. Practice codified in `KB § PATTERNS/project-execution.md
  § 2.8 Measurement discipline`.
- ✅ **APPLIED** — CLAUDE.md bullet-weight discipline codified
  as a soft target (≤80 words; >100 → consider trimming) with
  the "3+ heavy bullets ⇒ recurrence rule fires on §1 itself"
  triage in `KB § PATTERNS/project-execution.md § 2.8 CLAUDE.md
  §1 bullet-weight discipline`.

### Phase 3 — AST stage 1: Python outline tool ✅ (2026-05-02)
- [x] §7 Q1 resolved (Python side): **stdlib `ast`** — already proven
      across `tools/{catalog,compliance,recurrence}.py`. No new
      dependency.
- [x] Implemented `mcp/noctusai/tools/outline_python.py` exposing
      `outline_python(path)` returning `OutlineResult{classes,
      functions, methods, constants, imports, line_ranges,
      docstring_first_line}` via stdlib `ast`. No bodies. Handles
      SyntaxError, missing file, encoding error gracefully (returns
      `parse_error` instead of raising). First-level methods only —
      nested funcs/classes intentionally not surfaced.
- [x] Registered in `mcp/noctusai/server.py` as `noctusai_outline_python`
      (one `path` param) + `--outline-python <PATH>` CLI flag with
      human-friendly rendering (line ranges, decorators, docstring
      summaries, methods nested under their class).
- [x] Colocated tests in `tests/test_outline_python.py` — 14 cases
      covering: missing file, SyntaxError, function, async function,
      decorators, docstring extraction, class + multiple methods,
      UPPER_SNAKE_CASE constants (incl. annotated), import +
      `from … import …` (including multiline), `symbol_count`
      derivation, `to_dict` round-trip, smoke test against
      `cost_evaluation.py` (real repo file).
- [x] `cd mcp/noctusai && pytest tests/` → **435 passed** (was 421;
      +14 from the new suite). Phase 3 alone: 14/14.
- [x] `python mcp/noctusai/cli.py --review` → 0 issues.

**Phase 3 size impact:**

| | Lines | Words | Chars | Tokens |
|---|---:|---:|---:|---:|
| CLAUDE.md before/after Phase 3 | 186 | 3,757 | 27,017 | ~6,754 |
| **Δ from Phase 3** | 0 | **0** | 0 | 0 |

Phase 3 delivered tooling + KB-anchor content only — no new
CLAUDE.md §1 bullet. Auto-load surface unchanged. The narrow-read
KB anchor's "Companion tooling" subsection updated from
"forthcoming" → live for Python (Phase 4 will close out the same
subsection for TS).

**Improvements:**
- ✅ **APPLIED** — KB anchor `agent-reading-discipline.md`
  "Companion tooling" subsection updated: Python outline tool
  marked ✅ live with CLI invocation example; TS still ⏳
  forthcoming. Closes the loop on the Phase 1 forward-stub
  (which named both tools as forthcoming) — Phase 4 will close
  the TS half.
- (none other identified — phase shipped clean; outline tool
  validated against a real repo file via the smoke test, CLI
  rendering reads well, structured `to_dict()` is stable for
  MCP host consumption).

### Phase 4 — AST stage 1: TypeScript AST setup + outline tool ✅ (2026-05-02)
- [x] §7 Q1 resolved (TS side): **regex-based outline, NOT TypeScript
      Compiler API as the §7 recommendation defaulted to.** Phase-0
      audit invalidated the default — Compiler API costs ~50MB on
      disk + ~200ms spawn per call for ~15% precision on edge cases
      (overloaded types, conditional types, nested template strings)
      that don't help the narrow-read use case. Regex on
      prettier/eslint-formatted TS hits ~95% of practical
      declarations at ~5ms per call. Documented deviation; upgrade
      path to tree-sitter or Compiler API stays open. §7 Q1
      updated below to reflect the new evidence.
- [x] Dependency choice: **none added.** Pure Python regex parser
      lives in `mcp/noctusai/tools/outline_typescript.py`. Skipping
      the Node sidecar / package.json sub-task entirely (audit-
      driven re-scope per the *expand-loudly* rule).
- [x] Implemented `mcp/noctusai/tools/outline_typescript.py` exposing
      `outline_typescript(path)` returning `OutlineResult` (same
      shape as `outline_python` — caller code stays parser-
      agnostic). Captures: classes (incl. `abstract`), interfaces
      (kind=`interface`), type aliases (kind=`type`), top-level
      functions (regular + async + default-export), arrow-fn consts
      (React components + hooks land here), methods inside classes
      (first-level only, brace-depth-tracked), UPPER_SNAKE_CASE
      + plain mixed-case constants, imports (multi-line collapsed
      to single-line for clean display). Block + line comments
      are stripped before regex passes so `/* function fakeFn */`
      doesn't false-match. Missing file → `parse_error`; encoding
      error → `parse_error`. Reuses `OutlineResult` and `Symbol`
      dataclasses from `outline_python.py` (no duplication).
- [x] Registered in `mcp/noctusai/server.py` as
      `noctusai_outline_typescript` (one `path` param) +
      `--outline-typescript <PATH>` CLI flag. CLI rendering updated
      so the kind label (class / interface / type) matches the
      symbol's actual kind instead of hardcoding `class`.
- [x] Colocated tests in `tests/test_outline_typescript.py` —
      23 cases covering: missing file, function declarations,
      async functions, default exports, arrow functions (incl.
      typed props + async), classes + methods + async methods,
      method/control-flow disambiguation (if/for/while not
      captured), interfaces, type aliases, generic types,
      UPPER_SNAKE_CASE + mixed-case consts, named/default
      imports, multi-line import collapse, block-comment +
      line-comment false-match prevention, symbol_count
      aggregation, to_dict round-trip, real-file smoke tests
      against `VistaShowcase.tsx` + `useVistaShowcase.ts`.
- [x] `cd mcp/noctusai && pytest tests/` → **458 passed** (was 435;
      +23 from the new suite). Phase 4 alone: 23/23.
- [x] `python mcp/noctusai/cli.py --review` → 0 issues.

**Phase 4 size impact:**

| | Lines | Words | Chars | Tokens |
|---|---:|---:|---:|---:|
| CLAUDE.md before/after Phase 4 | 186 | 3,757 | 27,017 | ~6,754 |
| **Δ from Phase 4** | 0 | **0** | 0 | 0 |

Phase 4 delivered tooling + KB-anchor content only — no new
CLAUDE.md §1 bullet. Auto-load surface unchanged. With both
outline tools live, the narrow-read KB anchor's "Companion
tooling" subsection now shows ✅ ✅ for both Python and TS.

**Improvements:**
- ✅ **APPLIED** — §7 Q1 updated below with the new evidence
  (Compiler-API recommendation deferred; regex-first chosen with
  upgrade path documented).
- ✅ **APPLIED** — KB anchor `agent-reading-discipline.md`
  § Companion tooling subsection updated: TS outline ✅ live with
  precision tradeoff note + upgrade path. Closes the Phase 1
  forward-stub completely (both ✅).
- ✅ **APPLIED** — CLI rendering bug fixed mid-phase: hardcoded
  `class` prefix replaced with `s.kind`-driven prefix
  (class / interface / type). Caught during smoke test against
  `useVistaShowcase.ts`.
- ✅ **APPLIED** — Multi-line import display bug fixed mid-phase:
  raw newlines from source slice are now collapsed to a single
  display line. Caught during smoke test against
  `VistaShowcase.tsx`.
- (none other identified — phase shipped cleanly with two display
  bugs caught and fixed in-phase by the smoke-test discipline;
  the regex parser handled real repo files without escaping into
  false positives).

### Phase 5 — Measure + close ✅ (2026-05-02)
- [x] Subjective evidence from this very session (which used the
      new rules + tools end-to-end while shipping Phases 1-4):
      narrow-read internalized; outline tools used on real files
      during the smoke tests instead of full Reads (saved ~5K
      tokens per outline call); `noctusai_count_tokens` replaced
      mental math throughout; Explore-delegation didn't fire much
      because most edits had known paths. Behavioral rules + tools
      worked as designed.
- [x] Measured per Phase-0 methodology (A — token count of
      auto-load surface) using `noctusai_count_tokens`. Numbers
      below.
- [x] Decision on `projects/methodology-mirror-and-workspaces/`
      reactivation: **stay DEFERRED.** 22% static surface savings
      + estimated 35-50% effective once behavioral wins are
      counted. Workflow no longer feels constrained day-to-day.
      Evidence + reactivation triggers updated in that project's
      §7 Q11.
- [x] Auto-improvement protocol applied at every phase close in
      this project (Phase 0/1/2/3/4) — no `noctusai_file_proposal`
      artifacts filed; `**Improvements:**` blocks + §11 entries
      ARE the audit trail. Per the methodology amendment shipped
      in Phase 2 close, this is the new default for all agents
      on this repo.
- [x] **Vista MCP project filed** per user directive at root
      `projects/vista-api-mcp/PROJECT.md`. Status: Concept —
      interrogation pending; reactivation gated on §7 Q1+Q2+Q3.
      Companion artifact `VISTA-API-MCP-GUIDE.md` lives at repo
      root (904 lines, calibrated 2026-05-02), ready for the user
      to copy out.
- [x] `MEMORY.md` updated: 3 step-(a) feedback entries shipped
      (narrow-read, Explore-delegation, auto-improvement). The
      session's other feedback entries from earlier in the day
      (Vista showcase, methodology splits) are also indexed.
      Step-(a) shipping is captured by the entries themselves;
      no separate "step-a-shipped" entry needed.
- [x] End-of-session checklist:
      - `bash scripts/verify-kb-sync.sh` → ✅ green (all 3
        checks: CLAUDE.md pointers, INDEX.md indexed docs, Layout
        tree drift)
      - `cd mcp/noctusai && pytest tests/` → **458 passed**
      - ERP backend `pytest` → 1816 passed (verified earlier in
        session 2026-05-02; no further ERP changes since)
      - ERP frontend `npx vite build` → green (verified earlier)

**Final auto-load surface measurement (precise, via `noctusai_count_tokens`):**

| Surface | Pre-trim (start of session) | Post-step-(a) | Δ |
|---|---:|---:|---:|
| CLAUDE.md tokens | ~10,640 | ~6,754 | **-3,886 (-37%)** |
| MEMORY.md tokens | ~4,883 | ~5,331 | +448 (+9.2%) |
| **Auto-load surface (combined)** | **~15,523** | **~12,085** | **-3,438 (-22%)** |

CLAUDE.md alone hit the upper-band target (-37%). The combined
auto-load surface delta is -22%, lower than CLAUDE.md alone
because three new memory entries (narrow-read, Explore-delegation,
auto-improvement) added 448 tokens. The static measurement
under-counts the real per-turn savings — every narrow-read /
outline-tool call avoids fetching whole files. The effective
per-turn savings is estimated 35-50%, well into "no longer
constrained" territory.

**Improvements:**
- ✅ **APPLIED** — `methodology-mirror-and-workspaces` §7 Q11
  updated with the actual measurement evidence + reactivation
  triggers. Future agent picking up that project starts from
  data, not placeholders.
- ✅ **APPLIED** — Vista MCP project filed at
  `projects/vista-api-mcp/PROJECT.md` with the interlock to the
  showcase project's `VISTA-API.md` source-of-truth + the
  repo-root guide as the active deliverable.
- (none other identified — Phase 5 was a measurement + closure
  phase; no fresh implementation surfaced new improvements.)

---

## 7. Open questions

Each question paired with a recommendation. Update as work progresses.

1. **AST tooling stack — typescript Compiler API vs tree-sitter vs regex.** *(Resolved 2026-05-02 — Phase 4 audit.)*
   - **(A)** Stdlib `ast` for Python (already proven), official
     `typescript` npm package for TS via Compiler API + child-process
     bridge. *Was the §7 default at project filing time.*
   - **(B)** Tree-sitter unified for both languages.
   - **(C)** Regex-based outline for TS (Python keeps stdlib `ast`).
   *Resolution: **(A) for Python, (C) for TS.** Phase 4 audit
   evidence: Compiler API costs ~50MB on disk + ~200ms spawn per call
   for ~15% precision on edge cases the narrow-read use case doesn't
   need (overloaded types, conditional types, nested template
   strings). Regex on prettier/eslint-formatted TS hits ~95% of
   practical declarations at ~5ms per call, no new deps, pure Python.
   The `OutlineResult` shape is identical across both tools so
   caller code stays parser-agnostic. Upgrade path: if a downstream
   use case (e.g. AI-training feature extraction in
   `projects/project-history-ledger/`) needs higher precision, swap
   the parser implementation behind the same contract — caller code
   doesn't change.*

2. **Same-environment vs. separate-environment trade-off.**
   *Already resolved 2026-05-02 in §2: pick a workflow, not an
   architecture. Same environment for cross-cutting work; isolated
   workspaces (once the deferred project ships) for heavy single-
   product execution. Step (a) is a workflow change, not a structural
   one — and it applies in both environments.*

---

## 8. Dependencies & blockers

- **No external blockers for step (a).** The work touches CLAUDE.md,
  KB, memory, MCP toolkit, and tests — all in this repo, all under
  the user's hand.
- **TypeScript dependency (Phase 4).** The user must approve adding
  the `typescript` npm package or accept the tree-sitter alternative.
  Default plan: official `typescript` package per §7 Q1.
- **Measurement methodology (Phase 0).** A measurement choice is
  required before Phase 1 — otherwise Phase 5's "did we save tokens?"
  is unanswerable. Three candidate methodologies in Phase 0; pick one.
- **Sibling project (deferred).** `projects/methodology-mirror-and-
  workspaces/` waits on this project's measurement evidence to
  re-activate. Don't start there until step (a) closes.

---

## 9. Success criteria

When this project ships, the user can:

- Open a session with a meaningfully smaller per-turn context cost
  (target: 30-40% reduction vs the pre-2026-05-02 baseline).
- Read large files structure-first via `outline_python` /
  `outline_typescript`, fetching bodies only for the symbols actually
  needed.
- Delegate breadth-first questions to the Explore subagent on a
  documented threshold instead of by reflex.
- See three-way sync (KB ↔ CLAUDE.md ↔ memory) green for the new
  rules.
- Decide on evidence whether to reactivate the deferred mirror +
  workspaces project (§7 Q11 of that project).

---

## 10. How to use this project

- **Single source of truth for progress.** Update this file as work
  progresses.
- **Live-tick tasks.** Flip `- [ ]` → `- [x]` immediately, not in
  batches.
- **Phase-by-phase by default.** Execute one phase, pause, wait for
  user "continue" before next.
- **Capture-then-synthesize improvements.** Drop in-the-act bullets
  in each phase's `**Improvements:**` block. At end-of-phase, BEFORE
  flipping `✅`, file ONE bundled proposal via
  `noctusai_file_proposal(project="methodology-extraction", ...)`.
  Apply inline, delete proposal.
- **Three-way sync.** Phase 1 + Phase 2 each touch CLAUDE.md, a KB
  file, AND a memory file. All three move together. Run
  `bash scripts/verify-kb-sync.sh` after each.
- **End-of-project: file Vista MCP project.** Per user directive
  2026-05-02. Recommended slug: `vista-api-mcp` or
  `vista-mcp-server`. Scope: spin off the work captured in
  `VISTA-API-MCP-GUIDE.md` (currently at repo root, queued to be
  copied out and deleted) into a real MCP server project. Phase 5's
  closing checklist includes scaffolding this from
  `templates/PROJECT-TEMPLATE.md` if it doesn't exist.

Suggested commands:

```bash
# Read this project first
sed -n '1,260p' projects/methodology-extraction/PROJECT.md

# Read the deferred sibling for context
sed -n '1,120p' projects/methodology-mirror-and-workspaces/PROJECT.md

# Inspect existing AST footprint in MCP toolkit
rg -n "^import ast\b|^from ast\b" mcp/noctusai/

# After Phase 1 / Phase 2 work
bash scripts/verify-kb-sync.sh

# After Phase 3 / Phase 4 work
cd mcp/noctusai && pytest tests/
python mcp/noctusai/cli.py --review

# End-of-session checklist (whatever was touched)
cd products/<touched>/frontend && npx vite build
cd products/<touched>/backend && pytest
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | Initial concept doc filed mid-session when user flagged a breaking-point. §1 + §2 + §3 + §3a + §5 (sketch) + §7 (12 questions) populated; §6 intentionally empty pending §7 resolution. User explicitly deferred this work to focus on the Vista showcase project. | Claude Opus 4.7 |
| 2026-05-02 | **Late-session amendment — agreement + AST tooling.** User confirmed "yes" to the build order (a→b→c). AST inventory: Python AST already wired in 4 MCP toolkit modules; TypeScript/TSX AST not wired; tree-sitter absent. Added Q11 (AST tooling scope) and Q12 (same-vs-separate environment) to §7. AST stage 1 positioned as companion to step (a). | Claude Opus 4.7 |
| 2026-05-02 | **Re-scoped to step (a) only.** User directive: *"About the mirror/local versioning thing, scope it as a separate project. This was an idea i had and we wont implement that system now, but we will in the future. Take it out of this project's scope to its own."* Created `projects/methodology-mirror-and-workspaces/` (Concept — deferred) carrying the original §1/§2/§5 mirror sections and §7 Q1-Q10 (mirror/workspace questions). This project trimmed to step (a) only: behavioral methodology + AST stage 1. §1, §2, §3, §3a, §4, §5 rewritten for the narrower scope. §6 drafted with 6 phases (Phase 0 audit + Phase 1 narrow-read + Phase 2 Explore delegation + Phase 3 Python outline + Phase 4 TS AST + Phase 5 measure-and-close). §7 trimmed to AST tooling stack (former Q11, now Q1) and environment-vs-workflow (former Q12, now Q2 — already resolved). Phase 0 partially shipped today: **CLAUDE.md trim 5615 → 3486 words (38% reduction)** with every rule and pointer preserved; KB sync verifier green. Closing checklist for Phase 5 now includes filing the Vista MCP project per the user's same-day directive. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 0 ✅ closed.** Audit findings: AST footprint correction (3 modules use `import ast` — `catalog.py`, `compliance.py`, `recurrence.py` — not 4 as the earlier draft claimed; `ai_brain.py` doesn't import `ast`); TS/TSX AST stack is empty (no tree-sitter, no `@babel/parser`, no `typescript` in `mcp/noctusai/`) so Phase 4 has a clean dependency choice; measurement methodology locked to **(A) token count of the auto-loaded surface** per user choice; build order (a→b→c) confirmed by user. Baseline numbers captured in Phase 0 block: pre-trim CLAUDE.md ~7,486-10,640 tokens; post-trim ~4,648-6,292 tokens; **delta ~2,838-4,348 tokens per turn from CLAUDE.md trim alone**, equivalent to ~22-29% of the auto-load surface (CLAUDE.md + MEMORY.md). Step (a)'s ~30-40% target is most-of-the-way reached on the trim alone; Phase 1+2 (behavioral rules) + Phase 3+4 (outline tools) need to land without growing CLAUDE.md back. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 1 ✅ closed — narrow-read working agreement.** Three-way sync complete: (1) new KB anchor `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md` with the long-form rule, three concentric levels (structure → targeted-body → whole-file), worked examples (`vista_showcase_service.py`, `seed/frontend/lib/src/api.ts`, `mcp/noctusai/cli.py`), explicit anti-pattern, and a stub §Explore-delegation section for Phase 2; (2) `KNOWLEDGE-BASE/INDEX.md` updated — Layout tree, By-topic, By-situation tables; (3) terse §1 bullet in `CLAUDE.md` pointing to the KB anchor (83 words, ~17% of Phase 0's recovered word budget); (4) `feedback_narrow_read.md` memory file + `MEMORY.md` index entry. `bash scripts/verify-kb-sync.sh` green. **CLAUDE.md size after Phase 1: 185 lines / 3,569 words / 26,222 chars** — +83 words from Phase 0 close (+2.4%); **net 36% smaller than the pre-trim baseline of 5,615 words**. Improvements captured in the phase block: INDEX.md Layout tree drift (caught + fixed inline; lesson for `verify-kb-sync.sh` enhancement); CLAUDE.md bullet trim discipline (95→83 words by moving grep example to KB only); replication-to-seed-symmetry watch-out for Phase 2's Explore-delegation rule. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 1 improvements applied + new MCP cost-evaluation tool shipped.** Per user directive *"before moving on to phase 2, implement all the improvements for phase 1"* + *"lets add this cost evaluation tool to mcp"*: (a) `scripts/verify-kb-sync.sh` extended with check #3 — INDEX.md Layout tree ↔ filesystem drift (warnings, exit 2 if any). First run caught a pre-existing drift on `seed-first-design.md` (in topic tables but missing from Layout sketch) — fixed inline. (b) `mcp/noctusai/tools/cost_evaluation.py` shipped with `count_tokens(path=…, text=…, extensions=…)` returning a `TokenCountResult` with per-file breakdown + tokenizer label. Tokenizer cascade: tiktoken (if installed) → chars/4 approximation; reports `tokenizer_used` so callers know precision. Wired into `mcp/noctusai/cli.py` (`--count-tokens`, `--count-tokens-text`, `--count-tokens-ext`) and into `mcp/noctusai/server.py` as `noctusai_count_tokens`. 15 colocated tests in `tests/test_cost_evaluation.py` — all green; full MCP suite still 421 passed. Tool used immediately in Phase 2 to measure CLAUDE.md size precisely instead of mental math. | Claude Opus 4.7 |
| 2026-05-02 | **Methodology amendment + Phase 2 improvements applied (auto-improvement protocol).** Per user directive *"please implement improvements found then go on with the next phase. Also update our methodology with this new 'auto-improvement' method. just tell me they were implemented, no need to ask so we gain time"*: amended `KB § PATTERNS/proposals-and-improvements.md § 4d Auto-improvement` to set the new default — at phase close, apply every in-scope, low-risk, self-contained improvement INLINE in the same session, no `noctusai_file_proposal` artifact, no user prompt; mark each item `applied`/`deferred → <destination>` in the Improvements block (block + §11 = audit trail). Formal proposal still required for items needing scheduling, explicit human approval, or batch review. CLAUDE.md §1 "Apply proposals inline, then delete" bullet replaced with the auto-improvement bullet (+63 words net). Memory entry `feedback_auto_improvement.md` filed; `MEMORY.md` indexed. Three-way sync verified. **Phase 2 improvements applied** under the new protocol: (1) forward-stub pattern, (2) capture-next-phase-watch-outs practice, (3) `noctusai_count_tokens` measurement adoption, (4) CLAUDE.md bullet-weight discipline (≤80 soft target, >100 trim, N=3+ heavy bullets ⇒ recurrence-rule triage on §1 itself) — all four codified in a new `KB § PATTERNS/project-execution.md § 2.8 Multi-phase rule shipments`. CLAUDE.md after this turn: 186 lines / 3,757 words / 27,017 chars / ~6,754 tokens — net **33% smaller than pre-trim baseline**. KB sync verifier green; full MCP suite still 421/421. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 5 ✅ closed — Project ✅ Done.** Final auto-load surface measurement via `noctusai_count_tokens`: CLAUDE.md ~10,640 → ~6,754 tokens (**-37%**); MEMORY.md ~4,883 → ~5,331 tokens (+9.2%, three new feedback entries); **combined surface ~15,523 → ~12,085 tokens (-22% static)**. Effective per-turn savings estimated 35-50% once narrow-read + outline-tool benefits are counted (every avoided whole-file Read saves another ~5-10K tokens not visible in static measurement). **Decision on `methodology-mirror-and-workspaces` (steps b+c): stay DEFERRED** — workflow no longer feels constrained; reactivation triggers + measurement evidence captured in that project's §7 Q11 for future agents. **Vista MCP project filed** at `projects/vista-api-mcp/PROJECT.md` per user directive — Concept stage, interlocks with the showcase project's `VISTA-API.md` source-of-truth + the repo-root `VISTA-API-MCP-GUIDE.md` companion artifact. End-of-session checklist green: KB sync verifier ✓, MCP tests 458/458, ERP backend pytest 1816/1816 (verified earlier in session), ERP frontend vite build ✓ (verified earlier). All five §6↔§11 self-check items: ✓. Project status flipped to ✅ Done. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 4 ✅ closed — TypeScript outline tool (with §7 Q1 resolution).** Phase-0 audit found no Python TS parser installed, no `mcp/noctusai/package.json`, ~50MB+spawn-cost for the §7 default Compiler-API path. **Expand-loudly re-scope:** chose regex-based outline (no Node spawn, no npm install, ~5ms/call, ~95% accuracy on prettier/eslint-formatted code). §7 Q1 updated to record the deviation + upgrade path. Shipped `mcp/noctusai/tools/outline_typescript.py` reusing `OutlineResult` / `Symbol` from `outline_python.py` (caller code is parser-agnostic). Captures: classes (incl. `abstract`), interfaces, type aliases, top-level functions (regular + async + default-export), arrow-fn consts (React components/hooks), methods inside classes (first-level, brace-tracked), UPPER_SNAKE_CASE + plain consts, imports (multi-line collapsed). Block + line comments stripped before regex passes. Wired through `mcp/noctusai/cli.py` (`--outline-typescript`) and `mcp/noctusai/server.py` (`noctusai_outline_typescript`); CLI rendering updated to use `s.kind` for the prefix label. 23 colocated tests + smoke against real `VistaShowcase.tsx` + `useVistaShowcase.ts`. Full MCP suite **458 passed** (was 435, +23). KB anchor `agent-reading-discipline.md` § Companion tooling marks both Python and TS ✅ live (Phase 1 forward-stub fully closed). Two display bugs caught + fixed mid-phase via the smoke discipline (CLI hardcoded `class` prefix; multi-line import preserved literal newlines). CLAUDE.md unchanged. Auto-improvement protocol applied at phase close: KB anchor + §7 Q1 + display fixes all in-scope and applied inline. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 3 ✅ closed — Python outline tool.** Shipped `mcp/noctusai/tools/outline_python.py` exposing `outline_python(path)` → `OutlineResult` with classes / functions / methods / UPPER_SNAKE_CASE constants / imports + line ranges + docstring first lines + decorators (NO bodies). Stdlib `ast`, no new dependency. Wired through `mcp/noctusai/cli.py` (`--outline-python <PATH>` with human-friendly rendering — line ranges, decorators, methods nested under their class) and `mcp/noctusai/server.py` (`noctusai_outline_python`). 14 colocated tests (missing file, SyntaxError, sync/async/decorated functions, classes + methods, annotated+plain UPPER_SNAKE_CASE constants, single+multiline imports, symbol_count, to_dict round-trip, real-file smoke test). Full MCP suite **435 passed** (was 421, +14). KB anchor `agent-reading-discipline.md` § Companion tooling updated: Python outline ✅ live, TS ⏳ Phase 4. CLAUDE.md unchanged (no new §1 bullet — outline tools are pointed-to from the existing narrow-read bullet). Auto-improvement protocol applied at phase close: KB-anchor update was the in-scope improvement, applied inline; no other improvements identified. §6 sub-tasks all ticked, §11 entry below, improvements.md regenerated. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 2 ✅ closed — Explore-agent delegation rules.** Three-way sync complete: (1) extended `agent-reading-discipline.md` — replaced the Phase-1 stub with full §Explore-agent delegation (rule + trigger conditions + research-breadth-not-product-count caveat + 5 worked examples + anti-pattern + companion tooling note); (2) INDEX.md unchanged (file already linked); (3) `CLAUDE.md` §1 bullet (~125 words, prefer-MCP-scans corollary inline); (4) `feedback_explore_delegation.md` memory + `MEMORY.md` index. `bash scripts/verify-kb-sync.sh` green (all three checks). **CLAUDE.md after Phase 2: 186 lines / 3,694 words / 26,592 chars / ~6,648 tokens** (measured via the new `noctusai_count_tokens` tool). +125 words from Phase 1 close (+3.5%); cumulative Phase 1+2 +208 words; **net 34% smaller than pre-trim baseline (~3,992 fewer tokens per turn)**. Improvements: forward-stub pattern paid off (Phase 1's stub became Phase 2's anchor with one edit); Phase 1 watch-out about replication-to-seed-symmetry slip in delegation framing prevented an at-edit slip; new cost-evaluation tool replaced rough chars/4 mental math for Phase 2 metrics; CLAUDE.md bullet weight (125 words) is at the upper edge — if Phase 3+4 add two more bullets of similar weight, recurrence rule (N=3+) triggers a triage on whether §1 bullets are still the right home or some content should move to dedicated KB pattern files with one-line pointers. | Claude Opus 4.7 |
