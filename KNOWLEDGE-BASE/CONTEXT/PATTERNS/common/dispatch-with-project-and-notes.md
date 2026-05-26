# Dispatch with PROJECT — return with notes

> **The structural execution pattern for noctusai engineer dispatches and inline-empersonation slices.** Tech-lead writes a `PROJECT.md` that doubles as the dispatch brief; engineer (or inline-lens) reads it, executes their slice, and returns a **delivery note**. When the engineer sees a better route mid-flight, they STOP and file a **surface note** — execution blocks until the tech-lead approves / rejects / adapts with rationale. The whole loop reuses the existing project + proposal infrastructure; **notes** are the concept layer mapped onto the `templates/PROPOSAL-TEMPLATE.md` format via the `kind` parameter.

## Why this exists

Before this pattern was codified, dispatched engineers (and inline-empersonated lenses) routinely:

- Skipped codification stages (s1→s2→s3→s4) because the brief didn't name them.
- Scope-expanded silently when they saw a "better way" mid-execution — sometimes useful, often a brittle commit that the tech-lead inherited without rationale.
- Returned with thin status footers that the tech-lead had to reverse-engineer to know what shipped.
- Surfaced findings that the tech-lead had already considered and ruled out (wasted turns).
- Forgot which lens to apply when inline (architect drifted out of specialist discipline).

The pattern formalizes a **two-way structured channel**: tech-lead → PROJECT.md (the brief, in the project file's §4a Dispatch routing) → engineer; engineer → notes (surface mid-flight, delivery at end) → tech-lead. Both sides write durable artifacts that survive `/clear` and re-read.

## The shape

```
projects/<slug>/                              ← directory shape (already convention)
├── PROJECT.md                                ← tech-lead writes; dispatch brief
│   §1-3   Context / Constraints / Design principles  (existing)
│   §3a    Seed-first analysis  (existing, REQUIRED)
│   §4     Scope (in / out)  (existing)
│   §4a    Dispatch routing  (NEW — REQUIRED)
│       §4a.1 Slice → Lens table  (which lens owns which slice + file scope + time-box)
│       §4a.2 Codification expectations per slice  (s1/s2/s3/s4 marked yes/no)
│       §4a.3 Routes-not-taken  (tech-lead's pre-rejected alternatives + why)
│       §4a.4 Notes — surface + delivery  (the workflow gates)
│   §5-11   (existing: architecture / phases / open Qs / dependencies / success / change log)
├── proposals/                                ← existing per-project folder
│   ├── <agent>-<ts>-surface-<slug>.md        ← NEW: kind="surface" (in-flight alt route)
│   ├── <agent>-<ts>-delivery-<slug>.md       ← NEW: kind="delivery" (post-execution return)
│   └── <agent>-<ts>-<slug>.md                ← LEGACY: kind="phase" (end-of-phase bundle)
└── findings.md  (optional)
```

**No new directory.** The existing `projects/<slug>/proposals/` folder hosts all three kinds. The `kind` parameter on `noctus.dev.file_proposal` shapes the filename + the body's `**Note kind:**` header. Legacy `phase` proposals are untouched (back-compat).

## The protocol

### 1. Tech-lead writes PROJECT.md §4a before any dispatch

For a single-slice quick project, §4a.1 has one row. For a multi-slice wave, one row per slice. Each row names the **lens** (which `.claude/agents/<name>` brings the specialist `owns_kb`), the **files** the slice touches, the **time-box**, and whether the slice is **dispatched** to an Agent or **inline-empersonated** by the tech-lead.

§4a.2 marks codification expectations per slice (which of s1/s2/s3/s4 should land). §4a.3 lists pre-rejected alternatives — so the engineer doesn't waste a turn surfacing them. §4a.4 reminds the engineer of the surface + delivery gates.

### 2. Engineer reads PROJECT.md (the WHOLE thing, not just their slice row)

The engineer dispatch brief points at `projects/<slug>/PROJECT.md`. The engineer reads:

- §1-3 for context (why this exists, what constraints, design principles)
- §3a to know which seam they're consuming or extending
- §4a.1 to find THEIR slice row → confirm scope + lens + files
- §4a.2 to know which codification events to emit
- §4a.3 to know which routes the tech-lead already considered and ruled out
- §5-6 for architecture + phase context

The brief itself is now lean — references PROJECT.md instead of inlining all this. See `KB § PATTERNS/architect/dispatch-engineer-tuning.md` for brief shape.

### 3. Engineer plans → executes, OR surfaces alt route → BLOCKS

**If the brief is clear and the engineer agrees with the routing:** execute the slice (file-disjoint, stay-in-worktree, AST-first per `engineer-default.md`).

**If the engineer sees a better route** (alternative architecture, alternative seam, alternative tool, alternative slice boundary, alternative codification stage):

1. STOP execution — do NOT proceed with the proposed alt.
2. File a **surface note** via `noctus.dev.file_proposal(kind="surface", project=<slug>, ...)`. Contents:
   - Proposed alternative (what + why)
   - Linkage to §4a.1 slice scope (which boundaries it expands / contracts)
   - Risk assessment (additive / breaking / cross-slice)
   - Linkage to §4a.3 — confirm this isn't already pre-rejected
3. Return to tech-lead with the surface-note filename.
4. WAIT for tech-lead to call `noctus.dev.set_proposal_status` →
   - `accepted` (proceed with original brief's slice scope — the alt was acknowledged but the original route stands)
   - `rejected` (rationale recorded as durable trailer; engineer proceeds with original brief)
   - `adapted` (rationale recorded; re-dispatch follows with the adapted brief)
5. Resume execution only after the surface note's status is set.

**Why block-on-surface (not proceed-then-review):** an engineer's worktree doesn't see the broad picture (peer activity, cross-product impact, batched resolution); silent fix-and-continue muddies file-disjoint commit hygiene by mixing route changes into a feature commit. Block-on-surface mirrors `engineer-default.md §7` (`drift-found:` rule — "you CONTINUE your own slice — tech-lead resolves at integration") applied to route alternatives.

### 4. Engineer writes delivery note at end

At the end of execution — before returning to tech-lead — the engineer files a **delivery note** via `noctus.dev.file_proposal(kind="delivery", project=<slug>, ...)`. Contents (minimum, mirrors engineer-default short-form footer):

- §1 Context: "the slice was dispatched per PROJECT.md §4a.1 row <X>"
- §2 Situation: "as-shipped state — which files changed, which tests added/passed, which acceptance criteria met"
- §3 Solution → 3.2 Application instructions: how the changes were actually made (path, line, AST tool)
- §4 Effects: behavior / risk / ergonomics / coverage (per template §4)
- §5 Acceptance: tick the dispatch-acceptance items
- **Codification events emitted (this slice):** explicit list of s1/s2/s3/s4 events the engineer logged (or "none + why")
- **drift-found:** + **scoped-improvement:** — durable form of the engineer-default two-leg footer
- Routes-not-taken the engineer encountered + chose-not-to-surface (rationale)

The delivery note IS the durable form of the engineer's return message. The tech-lead absorbs it at integration — lessons → KB/memory, drift-found → batched resolution, scoped-improvement → codification radar.

### 5. Tech-lead absorbs at integration, then archives

After all slices in §4a.1 are delivered + integrated:

1. Read every delivery note in `projects/<slug>/proposals/`.
2. Lessons → KB/memory (per `persistent-files-absorption.md`).
3. Routes-not-taken from delivery notes → update §4a.3 of the PROJECT.md as durable history.
4. Codification events → confirm s2/s3/s4 ndjson entries landed.
5. Archive the project (per `KB § PATTERNS/architect/project-execution.md § Closeout`).

## Composes-with

- **`engineer-default.md`** — the standing protocol. §1a on-disk verification, §3 short-form return, §7 two-leg footer (drift-found / scoped-improvement). Delivery notes are the DURABLE form of §3's return shape — the same content, but persisted.
- **`KB § PATTERNS/architect/dispatch-engineer-tuning.md`** — brief shape (~15 lines, references PROJECT.md instead of inlining).
- **`KB § PATTERNS/architect/parallelization-first-orchestration.md`** — inline-empersonation rules (the tech-lead applies a lens when no subagent dispatch). Same §4a metadata applies — tech-lead reads their own §4a.1 row, switches discipline, applies + commits, then switches.
- **`KB § PATTERNS/common/scoped-auto-improvement.md`** — the two-leg footer's ledger destination. Delivery notes also write to `project-history/auto-improvement.ndjson` (so codification radar + cache stay fed).
- **`KB § PATTERNS/common/methodology-codification-pipeline.md`** — the s1→s2→s3→s4 contract. §4a.2 names which stages a slice is expected to touch.
- **`KB § PATTERNS/architect/proposals-and-improvements.md`** — legacy phase-proposal protocol (kind="phase", end-of-phase bundle). Untouched by this pattern.

## Tooling

- **MCP**: `noctus.dev.file_proposal(kind="phase|surface|delivery", project=<slug>, ...)` — same tool, three kinds.
- **MCP**: `noctus.dev.set_proposal_status(status="accepted|rejected|adapted", project=<slug>, reason=<rationale>, ...)` — `adapted` is new; `reason` now recorded for all non-default statuses (audit).
- **MCP**: `noctus.dev.proposal_template` — returns the canonical template (which now carries `**Note kind:**` field + per-kind guidance).
- **MCP**: `noctus.dev.codify_log(stage, target, description, force?)` — append a codification event with s-stage progression enforcement (s4 requires preceding s3 same-target · s3 requires preceding s1|s2 same-target · `force=True` with rationale for backfill / same-commit s2→s3→s4 compression). Solves the bypass-the-stages slip that needed 5× manual backfill on 2026-05-26 evening. Sibling of §4a.2 — the dispatched engineer / inline-lens EMITS what §4a.2 anticipates. → `KB § PATTERNS/common/methodology-codification-pipeline.md`.
- **Keeper**: `check_project_has_dispatch_routing` (Stage-4, severity warning, 2026-05-26 evening) — every PROJECT.md with §6 phases must carry §4a; projects whose PROJECT.md first-commit predates the rule's birthday are grandfathered via git first-commit date.
- **CLI**: `python mcp/noctusai/cli.py --list-proposals --product <slug>` — existing listing (project-scoped listing TBD as follow-up).
- **CLI**: `python mcp/noctusai/cli.py --codify-log <STAGE> <TARGET> <DESCRIPTION> [--force --codify-source-ref <ref>]` — codify_log from the command line.
- **CLI**: `python mcp/noctusai/cli.py --check-project-has-dispatch-routing` — run the dispatch-routing keeper standalone.

## Recurrence trigger

This pattern emerged when the user surfaced (2026-05-26 session): *"agents (and even inline deving) skip steps and get lost — give them roadmaps to follow upon dispatch, structured instructions and structured communications."* The s4-keeper-without-s3-codification gap shipped earlier the same day (`check_codification_pipeline_health` smoke-fired on s3-codified-NEVER) was the proximate signal — agents skip s2→s4 because nothing structurally requires them to mark s3. §4a.2 makes the expectation explicit; the delivery note records what landed.

**Promoted to s4 same-day (2026-05-26 evening).** User override of the N=1 deferral — keeper `check_project_has_dispatch_routing` shipped + `noctus.dev.codify_log` shipped + pre-commit hook drift fixed in one slice (project `dispatch-pattern-hardening`). Both keeper + helper enforce the pattern structurally instead of advisory-only. Grandfather rule (pre-birthday projects skipped) keeps the warning surface tractable.

## What this does NOT do

- It does NOT replace the legacy phase-proposal flow (`kind="phase"`) — phase proposals continue working unchanged for end-of-phase bundled improvements.
- It does NOT change the proposal file format — `templates/PROPOSAL-TEMPLATE.md` got one new field (`**Note kind:**`) + per-kind guidance; the §1-6 structure is identical.
- It does NOT introduce a parallel `notes/` subdirectory — the existing `projects/<slug>/proposals/` folder hosts all three kinds.
- It does NOT impose a keeper today — the protocol is advisory (s3). A keeper lands only when recurrence proves it's needed.
