# Improvements — Methodology Extraction — Behavioral Methodology + AST Stage 1 Tooling (Step a)

> **Auto-generated** from `PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `PROJECT.md`
**Plan status:** ✅ **Done — all 6 phases closed 2026-05-02.** Step (a) of the original three-step build order ships clean: behavioral methodology (narrow-read + Explore-delegation rules in CLAUDE.md + KB + memory) + auto-improvement methodology amendment + AST stage 1 tooling (`noctusai_count_tokens`, `noctusai_outline_python`, `noctusai_outline_typescript`) + companion infrastructure (`verify-kb-sync.sh` Layout-tree drift detector). 458/458 MCP tests green. **Auto-load surface: 15,523 → 12,085 tokens (-22% static; estimated 35-50% effective once behavioral per-file-read wins are counted).** Sibling project `methodology-mirror-and-workspaces` stays DEFERRED — workflow no longer feels constrained at this saving level; reactivation triggers documented in that project's §7 Q11. Vista MCP project filed at `projects/vista-api-mcp/` per user directive. §7 Q1 resolved with audit-driven re-scope (regex outline for TS instead of Compiler API — same `OutlineResult` contract; upgrade path open).
**Completed phases:** 6 of 6.
**Phases with recorded improvements:** 6 of 6 completed.

## Improvements by phase

### Phase 0 — Audit baseline

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

### Phase 1 — Narrow-read working agreement

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

### Phase 2 — Explore-agent delegation rules

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

### Phase 3 — AST stage 1: Python outline tool

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

### Phase 4 — AST stage 1: TypeScript AST setup + outline tool

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

### Phase 5 — Measure + close

` blocks + §11 entries
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

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- Local mirror checkpoint layer →
- Per-product workspace isolation →
- AST stage 2 — AST-based diff for the mirror →
- GitHub-side automation.
- Replacing trunk's existing project / proposal / keeper systems.

## Open questions still blocking

- **AST tooling stack — typescript Compiler API vs tree-sitter vs regex.** *(Resolved 2026-05-02 — Phase 4 audit.)*
- **Same-environment vs. separate-environment trade-off.**
