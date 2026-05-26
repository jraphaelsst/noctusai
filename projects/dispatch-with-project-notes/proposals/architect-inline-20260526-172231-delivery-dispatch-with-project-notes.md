# Proposal: Dispatch-with-PROJECT-and-notes — Phase 1 delivery

**Agent:** architect-inline (claude-opus-4-7)
**Note kind:** delivery
**Origin:** project:dispatch-with-project-notes:phase-1
**Generated:** 2026-05-26 17:22
**Severity:** medium
**Effort:** medium
**Affected products:** none (methodology — touches templates / KB / CLAUDE.md / agents / MCP tool)
**Status:** pending  <!-- tech-lead (rapha) absorbs lessons + closes -->

---

## 1. Context

Phase 1 of the `dispatch-with-project-notes` project shipped: codified the structural dispatch pattern (tech-lead → PROJECT.md §4a → engineer/lens → delivery note; alt route → surface note + BLOCK). The slice was triggered by the user's 2026-05-26 evening surface — *"agents skip steps and get lost; provide roadmaps for them to follow upon dispatch, structured instructions + structured communications. Adapt proposals, keep project structure."* — alongside `check_codification_pipeline_health` smoke-firing s3-codified-NEVER (4 s4-keepers had shipped same session without s3 events logged).

Executed entirely inline-empersonation by the architect (no parallel dispatch — cross-surface shared-state required coherent voice across 7 first-class methodology surfaces in one commit).

---

## 2. Situation (as-shipped state)

The methodology now carries a structural execution pattern, codified across 7 surfaces:

- **`templates/PROJECT-TEMPLATE.md`** — new §4a Dispatch routing (slice→lens table · codification expectations s1/s2/s3/s4 · routes-not-taken · notes contract).
- **`templates/PROPOSAL-TEMPLATE.md`** — new `**Note kind:**` field + per-kind guidance HTML comment block (phase / surface / delivery).
- **`mcp/noctusai/tools/noctus/dev/proposals.py`** — new `VALID_NOTE_KINDS = ("phase", "surface", "delivery")` · new `kind` parameter on `file_proposal` (validates + shapes filename `<agent>-<ts>-<kind>-<slug>.md` for surface/delivery, back-compat shape for phase) · new `VALID_NOTE_STATUSES` including `"adapted"` · new `project=` scoping on `update_proposal_status` · rationale-trailer recorded for ALL non-default statuses (not just `rejected`).
- **`KB § PATTERNS/common/dispatch-with-project-and-notes.md`** — NEW canonical reference (~80 lines: why exists, the shape, the protocol §1-5, composes-with, tooling, recurrence trigger, anti-patterns).
- **`KB § INDEX.md`** — tree entry (alphabetical, after `dispatch-warmup.md`) + catalog row (after methodology-codification-pipeline).
- **`CLAUDE.md` §1** — new rule one-liner after `Scoped auto-improvement`.
- **`.claude/agents/engineer-default.md`** — new §1b (Read PROJECT.md first) · new §1c (Surface notes — STOP + file + BLOCK) · §3 short-form return extended with `codification-events:` + `delivery-note:` lines.
- **`.claude/agents/backend-engineer.md` · `frontend-engineer.md` · `devops-engineer.md`** — composes-with pointers added to `dispatch-with-project-and-notes.md`.

Sibling work:

- `pgvector==0.4.2` installed in venv (drift surfaced in earlier session by W1-A backend-engineer; closed).
- 4× s3-codified backfill in `project-history/auto-improvement.ndjson` for the methodology-only ships done earlier this session (lenses-applied-trailer, prod-cache-container, ci-embedding-cache-gate, prod-deploy-safety-gates).
- `projects/dispatch-with-project-notes/PROJECT.md` — the dogfood project file (this file's parent), structured per the new §4a.

---

## 3. Proposed Solution

This is a delivery note — the solution shipped. Sections 3.1–3.5 are repurposed to record HOW it was applied.

### 3.1 Linkage — why this solution fits this situation

The user's surface (`agents skip steps + get lost`) is a downstream consequence of dispatch briefs being implicit + ephemeral (chat-only). Making PROJECT.md §4a the structural canonical-brief — with explicit codification expectations + routes-not-taken — closes the "agents skip silently" gap and the "agents re-surface pre-rejected routes" gap simultaneously. Reusing the existing `proposals/` infrastructure (vs inventing `notes/`) matches the user's explicit constraint and keeps the methodology surface count constant.

### 3.2 Application instructions (HOW the change was made)

1. Added §4a section to `templates/PROJECT-TEMPLATE.md` between §4 Scope and §5 Architecture (4 sub-sections + intro guidance).
2. Added `**Note kind:**` field + per-kind guidance HTML comment to `templates/PROPOSAL-TEMPLATE.md` (after `**Agent:**`).
3. Extended `proposals.py` (~50 LoC across 4 edit points): module docstring, `VALID_NOTE_KINDS` constant, `kind` param + filename shaping in `file_proposal`, `VALID_NOTE_STATUSES` with `adapted`, `project=` scoping + universal rationale-trailer in `update_proposal_status`, MCP tool description updates for both `file_proposal` and `set_proposal_status`.
4. Authored `KB § PATTERNS/common/dispatch-with-project-and-notes.md` from scratch (~140 lines, structured: rationale → shape → protocol → composes-with → tooling → recurrence → anti-patterns).
5. Added INDEX.md tree entry + catalog row.
6. Added CLAUDE.md §1 one-liner.
7. Updated `engineer-default.md` (§1b + §1c new sections; §3 footer extended).
8. Updated `backend-engineer / frontend-engineer / devops-engineer.md` composes-with pointers.
9. Created `projects/dispatch-with-project-notes/PROJECT.md` dogfooding the new §4a.
10. Filed this delivery note (you're reading it).

### 3.3 Seed APIs / shared lib involved

- `noctus.dev.file_proposal` — extended with `kind` parameter (this is THE seam).
- `noctus.dev.set_proposal_status` — extended with `project=` scope + `adapted` status + universal `reason` trailer.
- `noctus.dev.proposal_template` — unchanged (template content carries the new guidance).

### 3.4 Risks before applying

Low risk — additive. `kind` defaults to `"phase"` (back-compat); existing phase-proposal callers see zero behavior change. The 3 engineer-agent updates are pure pointer additions in composes-with. The CLAUDE.md addition is one §1 line. The two template changes are content-only (no structural breaking). The proposals.py edits add validation that only fires when invalid `kind` is passed (defensive).

---

## 4. Effects

- **Behavior:** `noctus.dev.file_proposal` now accepts `kind ∈ {phase, surface, delivery}`. Default unchanged. `set_proposal_status` now accepts `adapted` + `project=` scope.
- **Risk profile:** SAFER — engineer alt-route divergence is now block-on-surface (was: silent fix-and-continue). Codification pipeline visibility increases (each slice marks expected s-stages).
- **Ergonomics:** Dispatched engineers / inline-lenses now have a structural canonical brief (PROJECT.md §4a) instead of an implicit chat-only brief. Lookup of routes-not-taken stops duplicate surfacing.
- **Coverage:** New methodology surface (KB doc + CLAUDE.md rule + 5 agent files + 2 templates). No test regression — proposals.py changes are validation-only on invalid inputs.

---

## 5. Acceptance Criteria

- [x] §4a section added to PROJECT-TEMPLATE.md
- [x] `Note kind:` field added to PROPOSAL-TEMPLATE.md
- [x] `kind` parameter on `noctus.dev.file_proposal` (validates + shapes filename)
- [x] `adapted` + `project=` on `noctus.dev.set_proposal_status`
- [x] KB doc authored + INDEX.md updated
- [x] CLAUDE.md §1 rule added
- [x] engineer-default §1b + §1c + §3 updated
- [x] 3 engineer-agent composes-with updated
- [x] Dogfood PROJECT.md created
- [x] This delivery note filed
- [ ] Keeper gates green (kb_sync · check_claude_md_router · check_seven_way_sync · check_agent_kb_alignment)  ← W3 in flight
- [ ] Impacted pytest green  ← W3 in flight
- [ ] feat/dispatch-with-project-notes pushed to `dev`  ← W3 in flight

---

## 6. Related files

- `templates/PROJECT-TEMPLATE.md` — §4a (the new section)
- `templates/PROPOSAL-TEMPLATE.md` — `Note kind:` field
- `mcp/noctusai/tools/noctus/dev/proposals.py` — `kind` param + new statuses
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/dispatch-with-project-and-notes.md` — canonical reference
- `CLAUDE.md` §1 — one-liner
- `.claude/agents/engineer-default.md` — §1b + §1c + §3
- `projects/dispatch-with-project-notes/PROJECT.md` — the dogfood

---

**Codification events emitted (this slice):**
- s1-emergent: dispatch-with-project-and-notes pattern (recurrence trigger — user surface + s4-without-s3 smoke)
- s2-memory: none (skipped — straight to s3 same commit, intentional for the codification-pass; if recurrence shows this skip is itself a slip, add MEMORY.md entry retroactively)
- s3-codified: `KB § PATTERNS/common/dispatch-with-project-and-notes.md` + CLAUDE.md §1 + INDEX.md catalog row + templates carry the rule + engineer-default discipline mirror — all in this commit
- s4-keeper: deferred (N=1 today; promote to s4 keeper `check_project_has_dispatch_routing` when recurrence proves the pattern earns it)

**drift-found:** (none observed — pgvector pip + 4× s3 backfill were drift-fix-on-contact done in same session as the methodology slice; both already absorbed)

**scoped-improvement:** Codification pipeline DID smoke-fire (s3-silent-NEVER) — the meta-keeper is working as designed. Pattern: when a session ships an s4-keeper without explicit s3-codified, the s3-silence threshold (60 days) ticks. Backfill mechanism is durable but reactive — consider a `noctus.dev.codify_log` helper that wraps the ndjson append + enforces the contract (s4 ship MUST be preceded by s3-codified entry in same session). Defer per recurrence rule.

**Routes-not-taken encountered + chose-not-to-surface:**
- Could have built `noctus.dev.list_notes(project, kind)` — covered by existing `list_proposals` for now; defer until friction.
- Could have built `check_project_has_dispatch_routing` keeper — N=1; methodology-in-pilot per codification-pipeline rule; promote on recurrence.
- Could have migrated existing `projects/<slug>/PROJECT.md` files to add §4a — opt-in (fix-on-contact rule); old projects gain it on next touch.

---

**Tech-lead action requested:** absorb lessons into KB/memory if any are durable (most are already codified at s3); close this note via `noctus.dev.set_proposal_status` once the integration commit + push lands.
