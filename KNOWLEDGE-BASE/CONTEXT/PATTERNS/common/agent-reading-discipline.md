# Agent Reading & Research Discipline

> **What this file is.** The long-form anchor for the behavioral
> rules that govern *how* the agent reads files and conducts research
> across the repo. Both rules exist to keep per-turn token cost
> proportional to the work being done — large files do not need to
> arrive whole when an edit only touches one function.
>
> **Where this applies.** Every session, every file read, every
> research question. The rules are tool-agnostic — they apply to
> direct `Read` / `grep` / `find` and to delegated subagent calls.
>
> **Sync rule.** This file's rules also surface as terse §1 bullets
> in `CLAUDE.md` and as memory entries under `~/.claude/projects/`.
> Update all three layers together; never just one (CLAUDE.md +
> memory + this file = three-way sync). See
> `CONTEXT/01-PHILOSOPHY.md § Docs stay in sync`.

---

## Narrow-read first

**The rule.** When opening a file you don't fully know, read its
**structure** first; fetch **bodies** only for the symbols you'll
actually edit, cite, or reason about.

### Trigger

Apply by default when **any** of these is true:

- The file is > 200 lines.
- You don't know the exact line range you need.
- The file is named generically (e.g. `service.py`, `utils.ts`,
  `helpers.py`) and likely contains many unrelated symbols.
- You're orienting (first read of a session) rather than editing
  specifically.

Skip the rule (read whole file) when **all** are true:

- The file is small (< 200 lines).
- You'll act on most of it (a full review, a complete rewrite, a
  migration body).
- The structure IS the content (a JSON config, a SQL migration with
  no nested logic, a `.env.example`).

### Behavior

Three concentric levels of detail, take the smallest that answers
the question:

1. **Structure pass** — outline only. Until the AST outline tools
   land in Phase 3+4, use one of:
   - `Read` with `limit=80` to see imports + first declarations,
     then a second read at a deeper offset if needed.
   - `grep -n "^def \|^class \|^export \|^const \|^function "
     <path>` (or `rg --type py --type ts -n '^(def |class |export
     |const |function )' <path>`) to dump symbol names + line
     numbers.
   - `wc -l <path>` to size the file before deciding.
2. **Targeted body pass** — read 30-100 lines around the specific
   symbol you'll touch (`Read offset=<line> limit=80`).
3. **Whole-file pass** — only when the cost is justified by the
   work.

### Why

Most edits need 1-2 functions. Reading a 600-line file whole pulls
in ~5,000-10,000 tokens of context that won't be referenced again
this turn — paid for in a smaller available window for the actual
reasoning. Phase 0 measurement of `methodology-extraction` (2026-05-02)
confirmed CLAUDE.md's auto-load surface alone is ~5-7K tokens
post-trim; whole-file reads of large modules can rival that on each
turn. The narrow-read rule recovers that headroom for thinking.

### Worked examples (from this repo)

- `products/erp-imobiliario/backend/app/services/vista_showcase_service.py`
  is 383 lines. Editing `IMOVEL_LIST_FIELDS` requires lines 47-76
  (~30 lines) — a `Read offset=40 limit=40` is enough; reading the
  whole file is wasteful.
- `seed/lib/frontend/src/api.ts` is hundreds of lines but the
  question "does `api.get` return `{data: T}` or `T`?" is answered
  by `grep -n "handleResponse\|return response.json" <path>` then a
  20-line targeted read of `handleResponse`.
- `mcp/noctusai/cli.py` has ~30 CLI flags. To answer "does it support
  `--review`?" a `grep -n -- "--review" cli.py` is one `grep` cheaper
  than a Read.

### Anti-pattern

Reading `Read <path>` with no offset/limit on every file the agent
encounters during exploration, regardless of size or relevance. The
default `Read` reads up to 2000 lines — that's cheap insurance feels
like, but the cost compounds across a multi-file investigation.

### Companion tooling

- ✅ **`noctus.dev.outline_python(path)`** (Phase 3 ship 2026-05-02) —
  returns a Python file's symbol tree (classes, functions, methods,
  module-level UPPER_SNAKE_CASE constants, imports) with line
  ranges. No bodies. Stdlib `ast`, no extra deps. CLI:
  `python mcp/noctusai/cli.py --outline-python <path>`.
  The structure pass on a Python file is now a single tool call —
  prefer it over the `grep -n "^def \|^class …"` heuristic when
  working with `.py` files.
- ✅ **`noctus.dev.outline_typescript(path)`** (Phase 4 ship 2026-05-02) —
  same `OutlineResult` shape for `.ts` / `.tsx`. Captures classes,
  interfaces, type aliases, top-level functions, arrow-fn consts
  (React components and hooks land here), methods inside classes,
  UPPER_SNAKE_CASE + plain consts, imports (multi-line collapsed).
  Regex-based — no Node spawn, no npm install, ~5ms per call. CLI:
  `python mcp/noctusai/cli.py --outline-typescript <path>`. The
  precision tradeoff against the TypeScript Compiler API is
  documented in the tool's module docstring; ~95% accuracy on
  prettier/eslint-formatted code is sufficient for narrow-read.
  Upgrade path to tree-sitter or Compiler API stays open if a
  downstream use case (e.g. AI-training feature extraction in
  `projects/project-history-ledger/`) needs higher precision.

### Detector (Phase 3 ship 2026-05-03 — `session-review-baseline`)

- ✅ **`noctus.dev.review_session`** — walks one Claude Code JSONL
  transcript and emits a body-free issue when a whole-file `Read`
  (no `offset` / `limit`) on a >200-line repo file was not preceded
  by an `outline_python` / `outline_typescript`. Severity is INFO
  (calibration on 5 real local sessions confirmed legitimate
  whole-file reads exist; the WARNING bump is gated on a future
  manual-ground-truth calibration). The detector lives at
  `mcp/noctusai/tools/session_review.py` and is wired into the
  static-axis `noctus.dev.review` family as a session-axis sibling.
  See `KB § 06-AGENTS.md § Session-axis review`.

---

## Explore-agent delegation

**The rule.** Delegate research questions to the Explore subagent
when the answer needs **3+ targeted greps, multi-file walking, or
open-ended discovery**. Read / grep directly when the path *or*
symbol is already known.

### Trigger

Delegate when **any** is true:

- The question is *"where is X defined / which files reference Y"*
  and X / Y is the only thing known.
- Answering needs ≥3 grep / find / glob calls in a row.
- The repo location of the relevant code is genuinely unknown
  (cross-product feature search, hunting an unfamiliar pattern).
- Broad audit: *"what frontend hooks call `/api/foo/*`"*, *"every
  place that imports `noctusai_lib.X`"*, *"all PROJECT.md files
  that mention slug Y"*.

Use direct tools (`Read`, `grep`, `find`) when **all** are true:

- The exact file path is known.
- One symbol / one section / one file resolves the question.
- The lookup is fast (`grep -n <symbol> <path>` or
  `Read <path> offset=N limit=80`).

### Why

The Explore subagent runs in its own context window. It greps,
reads excerpts, and returns a synthesized digest — *the raw search
output never lands in the main conversation*. For breadth-3+ work
that's a cache-saving move (the digest is small; the equivalent raw
output would have flooded the main window). For a one-shot lookup
it's pure overhead — the subagent spin-up cost outweighs a single
`grep` you could run inline.

### The trigger is RESEARCH BREADTH, not product count

Phase 1 watch-out (carried over from the
`replication-to-seed-symmetry` rule): *the right framing is "3+
greps" or "open-ended discovery", NOT "this question touches N
products"*. A question that walks 3 directories of one product is a
delegate; a question that names one file in 5 products is direct.

### Worked examples

- *"where is `create_product_app` defined and who imports it?"* →
  delegate (multi-file walking, broad symbol-usage audit).
- *"does `vista_showcase_service.py` use `_audit` on every error
  path?"* → direct (one known path, one targeted scan).
- *"audit every project's §3a Seed-first analysis section"* →
  delegate (cross-folder discovery, ~15 files).
- *"check whether `/api/vista-showcase/imoveis` returns the correct
  envelope shape"* → direct (one known router file).
- *"what frontend hooks read `result.data` from `api.get`?"* →
  delegate (cross-hook scan, would have been ≥3 greps + reads).

### Anti-pattern

Delegating *"open `path/to/file.ts` and tell me what it does"* — a
direct `Read` is faster, cheaper, and the agent's understanding
isn't filtered through a digest.

### Companion tooling

- The Explore subagent (built-in `Agent` tool with
  `subagent_type=Explore`) is the canonical delegate.
- For `noctusai_*` MCP scans (`noctus.dev.scan_cross_product_helpers`,
  `noctus.dev.refs`, `noctus.dev.status`), the scan IS the digest —
  prefer the dedicated tool over delegating a generic Explore for
  the same question.
- After narrow-read (above) is fluent, "is this a delegate?" usually
  reduces to "does the structure pass say I need ≥3 more files?" —
  the two rules compound.

---

## See also

- `CLAUDE.md § Engineering Philosophy` — the terse bullets that point
  here.
- `CONTEXT/01-PHILOSOPHY.md § CLAUDE.md vs KNOWLEDGE-BASE` — the
  token-budget rule that motivates narrow-read at the
  philosophical level.
- `CONTEXT/PATTERNS/architect/project-execution.md § 2.5 Phase 0 audits` —
  Phase 0 audits are the canonical site where narrow-read pays for
  itself; the audit reads many files briefly, never fully.
- `projects/methodology-extraction/PROJECT.md` — the active project
  shipping these rules + tools.
