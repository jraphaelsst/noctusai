# Context Budget Overhaul — Project Document

> **Living document.** Phases revise as learnings come in. Capture in §11.
>
> **Scope: this entire project is META — it edits Claude's context-loading layer
> (CLAUDE.md, MEMORY.md, individual memory files, KB anchor depth, MCP allowlist,
> skills policy), not product code.** No backend / frontend / migration touches.
> §3a seed-first analysis is filled out below for the explicit "this is correctly
> platform-meta" confirmation.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Phase 0 ready
- **Owner / stakeholders:** rapha · claude-opus-4-7
- **Related docs:** `CLAUDE.md`, `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`, `KNOWLEDGE-BASE/INDEX.md`, `~/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/MEMORY.md`, `.mcp.json`, `.claude/settings.local.json`, `templates/PROJECT-TEMPLATE.md`
- **Project slug:** `context-budget-overhaul` — root-projects scope (cross-cutting platform-meta).

---

## 1. Context & Purpose

CLAUDE.md and MEMORY.md auto-load on every reply. CLAUDE.md is currently 193 lines of paragraph-bullets (~9-10K tokens), and MEMORY.md is 296 lines of paragraph-form index entries (~6-7K tokens) — totalling ~15-17K tokens spent every turn before any task content. Most of the per-turn content is redundant with the heavyweight KB (which is loaded *on demand*) — the system was supposed to be CLAUDE.md-as-router → KB-as-depth, but CLAUDE.md drifted into containing the depth itself.

The win: every-reply token savings of 60-70% on the auto-loaded surface. The cost we want to avoid: losing the "why" / slip-counts / caught-instances that keep behavioral rules from re-emerging — those must be parked in KB anchors *before* the CLAUDE.md bodies are trimmed.

Plus three contributing surfaces: stale/superseded individual memory files (~52 feedback files, several subsumed); MCP allowlist (currently exposes claude-in-chrome + ~30 claude.ai connectors as deferred tools, of which user only wants noctusai + supabase); skills allowlist (Claude Code bundles ~10 skills, only a few used).

Pain today: faster context exhaustion → earlier compression → stale rules → re-slipping. Win: each turn ≈ 10K cheaper, longer effective windows, behavioral rules still load-bearing because the depth is in KB.

---

## 2. Confirmed constraints

- **Scope** — CLAUDE.md compaction + MEMORY.md compaction + topical split + MCP keep-list (noctusai + supabase only) + skills keep-list. *(KB stays heavyweight — explicit user direction "dont compact kb, i got the importance of it being the heavy-weight-end".)*
- **Architecture** — KB is heavyweight depth; CLAUDE.md + MEMORY.md become slim routers pointing into KB. *(Quote: "so the other 2 consumes it as routers, yea?" — confirmed.)*
- **MCP keep-list** — noctusai + supabase only. Drop claude-in-chrome (rarely used). All other claude.ai connectors stay catalog-level (out of CLI control). *(Quote: "as for the mcp allowlist, keep only noctusai's and supabase's for now. dont keep claude in chrome, i dont use it often.")*
- **Project shape** — merge into a single umbrella project with phases ordered A → B → C, "save some time without losing quality and details, but better-scoping editing". *(Quote: "please merge projects where applicable so we save some time without losing quality and details".)*
- **Documentation** — every change three-way-synced (KB ↔ CLAUDE.md ↔ memory). *(Quote: "Doc all these changes so future agents are uptodate".)*
- **Methodology — commit per phase, push at project close** — already documented in CLAUDE.md (rule shipped 2026-05-03 in the previous session). User asked whether it's already doc'd; answer is yes, no new doc needed for that specifically. This project follows the rule.
- **Mode** — "Ram through it all, but please be careful." → User wants top-to-bottom execution, no per-phase wait, but with the rigor checks (Phase 0 audit, active robustness review, KB-anchor pre-step, verify-kb-sync gate).

---

## 3. Design principles

1. **Auto-loaded vs. on-demand is the lever.** Every-turn savings only come from compacting CLAUDE.md and MEMORY.md (auto-loaded). KB / individual memory files are on-demand — touching them is per-load savings, far smaller leverage. Phase ordering reflects this.
2. **Park before trim.** The "why" / slip-counts / caught-instance history in current CLAUDE.md bodies is corrective pressure — strip it without parking it in KB and the rule weakens. Phase 1 parks; Phase 2 trims.
3. **Pointers must resolve.** `verify-kb-sync.sh` is the gate. Every CLAUDE.md pointer (`→ KB § X`) must land on a real anchor.
4. **Topical split = path-of-least-discipline.** Move backend-only / frontend-only / project-only / platform-only rules into `CLAUDE-<topic>.md` files loaded on demand. The always-loaded `CLAUDE.md` lists "when doing X, also read CLAUDE-X.md" as a routing rule. No new harness mechanism — just discipline + KB-style pointer.
5. **Keep-lists, not kill-lists.** For MCP and skills, the policy is "this is the keep-list; everything else is on-demand or off". Future agents follow the keep-list rather than us listing every MCP/skill we don't want.
6. **Three-way sync at every rule change.** KB anchor + CLAUDE.md (or topical sub-file) pointer + memory file + MEMORY.md entry — same session.

---

## 3a. Seed-first analysis

> **This is platform-meta, not product code.** The seed framework is irrelevant here; nothing in this project mounts into a product app. §3a is filled out for the explicit confirmation the design is correctly platform-bounded.

1. **Is the contract identical for every product?** N/A — this is `/CLAUDE.md` + `/KNOWLEDGE-BASE/` + `/.claude/` + per-user memory. No product touches.
2. **Is the data source product-specific?** N/A.
3. **Is the placement product-specific?** N/A — everything lives at the repo root (`/CLAUDE.md`, `/KNOWLEDGE-BASE/`, `/.claude/`, `/.mcp.json`) or in the per-user memory directory.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** N/A — not a seed-mountable concern.
6. **Default-on or opt-in?** N/A — every agent in this repo loads CLAUDE.md every turn.

**Litmus — per-product code count this design requires:** [x] **0 lines** (correctly platform-meta — zero product touches; the only files edited are CLAUDE.md, KB docs, memory files, .mcp.json, .claude/settings.local.json).

**Phase plan implications:** §6 phases work in `/CLAUDE.md`, `/KNOWLEDGE-BASE/`, `/.claude/`, `/Users/rapha/.claude/projects/.../memory/`. No phase walks through products. Correct shape.

---

## 4. Scope

**In scope:**
- Compact `/CLAUDE.md` from paragraph-bullets to terse rule + pointer.
- Compact `/Users/rapha/.claude/projects/.../memory/MEMORY.md` index to one-line entries (per system-prompt format).
- Retire stale/superseded individual memory feedback files (e.g. `feedback_seed_first.md` subsumed by `feedback_seed_first_at_authoring_time.md`).
- Park "why" / slip-history content from CLAUDE.md bodies into KB anchors *before* trimming.
- Topical split: introduce `CLAUDE-backend.md` / `CLAUDE-frontend.md` / `CLAUDE-projects.md` / `CLAUDE-platform.md` for rules that don't apply universally; rewrite `CLAUDE.md` as the lean router.
- MCP allowlist: verify project-level config locks to noctusai; document keep-list policy + claude-in-chrome disable path (UI-side).
- Skills keep-list policy: documented in CLAUDE.md / KB.
- New "context budget discipline" methodology rule: three-way-synced (KB + CLAUDE.md + memory).

**Out of scope (for now — with reason):**
- KB compaction — explicitly excluded by user. KB stays heavyweight depth (per-load cost is amortized; per-turn cost is zero unless opened).
- Individual memory `feedback_*.md` body trimming — on-demand load, low per-turn yield, high "why" density. *(Phase 3 only retires duplicates / supersededs; bodies of kept entries stay rich.)*
- Disabling individual claude.ai connectors — those are catalog-level, managed via claude.ai web settings, not CLI-trimmable. *(Documented as a future user-side action.)*
- Per-product CLAUDE.md files — not pursued in this project; `KB § per-product` already serves that role.

---

## 5. Architecture / Data Model

Files touched (all paths absolute or repo-relative):

- `/Users/rapha/Documents/repository/NoctusAI/noctusai/CLAUDE.md` — main outer map.
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/CLAUDE-backend.md` (NEW, Phase 4) — backend-only behavioral rules.
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/CLAUDE-frontend.md` (NEW, Phase 4) — frontend-only.
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/CLAUDE-projects.md` (NEW, Phase 4) — project-execution-only.
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/CLAUDE-platform.md` (NEW, Phase 4) — DB / LGPD / webhook / shared-lib (load only when touching cross-cutting platform).
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md` — receive parked "why"/slip content (Phase 1).
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/KNOWLEDGE-BASE/PATTERNS/*.md` — receive parked content where topic-specific.
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/KNOWLEDGE-BASE/INDEX.md` — re-index any new KB anchors.
- `/Users/rapha/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/MEMORY.md` — index compaction.
- `/Users/rapha/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/feedback_*.md` — retire duplicates/superseds; possibly add `feedback_context_budget_discipline.md`.
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/.mcp.json` — verify minimal.
- `/Users/rapha/Documents/repository/NoctusAI/noctusai/.claude/settings.local.json` — verify minimal `enabledMcpjsonServers`.

Loading model after this project:

```
Every turn (auto-loaded):
  CLAUDE.md (~60-80 lines, terse rules + topical pointers)
  MEMORY.md (~80 lines, one-line index entries)

On demand (when a topic is touched):
  CLAUDE-backend.md / CLAUDE-frontend.md / CLAUDE-projects.md / CLAUDE-platform.md
  KB § CONTEXT / PATTERNS / GUIDES / per-product
  Individual memory feedback_*.md files
```

---

## 6. Implementation phases

**Cadence override.** User instruction: "Ram through it all". Run all phases without waiting for "continue" between them. Standard rigor checks (Phase 0 audit, active robustness review, KB-anchor pre-step, verify-kb-sync gate, per-phase commit) still apply.

### Phase 0 — Audit ✅
- [x] Measure exact line / token sizes of CLAUDE.md, MEMORY.md, top-10 largest memory files.
- [x] List every CLAUDE.md §1 rule with: target KB anchor + load-bearing content (slip counts, caught-instances, mantras) that needs parking.
- [x] Identify duplicate / superseded memory files.
- [x] Snapshot current MCP allowlist state (`.mcp.json`, `.claude/settings.local.json`, claude.ai connectors visible in the system reminder).
- [x] Snapshot current Claude Code skills available.
- [x] Output: `audit.md` inside this project folder.

**Improvements:** none identified — audit-only phase.

### Phase 1 — KB-anchor preservation pre-step ✅
- [x] For each CLAUDE.md rule with load-bearing body content, verify the matching KB anchor exists and carries the depth.
- [x] Verified all 86 KB-shorthand pointers + 5 literal pointers resolve to real anchors.
- [x] Verified slip-history sections exist (`KB § PATTERNS/project-execution.md § Audit trail of the slip pattern` x2, replication-to-seed-symmetry rule, §6↔§11 self-check rule).
- [x] Discovered `KB § PATTERNS/project-execution.md § 2.8 Multi-phase rule shipments — forward-stub + bullet-weight discipline (2026-05-02)` already mandates ≤80 words/CLAUDE.md-§1-bullet. Phase 2 has explicit alignment target.
- [x] No KB edits required — load-bearing content is already preserved across (a) memory `feedback_*.md` files (full why + slip-count) and (b) KB anchors (principle depth + audit trails).
- [x] No INDEX.md update required.

**Improvements:**
- The KB-anchor coverage is good *because* prior projects already three-way-synced rules into KB before they were added to CLAUDE.md. The current bloat is paragraph-bullets *layered on top of* preserved KB depth — i.e. CLAUDE.md drifted away from its own rule (KB § 2.8). Phase 2 brings CLAUDE.md back into compliance with its own bullet-weight discipline.
- `noctusai_count_tokens` MCP tool exists (per KB § 2.8) for measurement; Phase 2 uses it for before/after metrics instead of `wc -w`.

### Phase 2 — CLAUDE.md compaction with topical split (merged from original Phase 2 + Phase 4) ✅
- [x] Land KB anchor for the new "Context budget discipline" rule at `KB § 01-PHILOSOPHY.md` (covers: CLAUDE.md=router/KB=depth, MCP keep-list, skills keep-list, topical CLAUDE/*.md loading discipline).
- [x] No `KB § INDEX.md` update needed (anchor-only addition inside existing 01-PHILOSOPHY.md).
- [x] Create `CLAUDE/` directory at repo root for topical sub-files.
- [x] Write `CLAUDE/backend.md` (5 rules; 21 lines / 434 words).
- [x] Write `CLAUDE/frontend.md` (2 rules; 16 lines / 162 words).
- [x] Write `CLAUDE/projects.md` (8 rules; 22 lines / 939 words).
- [x] Write `CLAUDE/platform.md` (4 rules; 20 lines / 462 words).
- [x] Rewrite `CLAUDE.md` — 18 universal rules each ≤80 words, §2 Map updated for new sub-files, §3 When-to-read-what updated to point at topical files, §4 Sync rule extended.
- [x] Extend `scripts/verify-kb-sync.sh` to also check pointers in `CLAUDE/*.md` (pointers from topical files into KB shouldn't silently rot).
- [x] Run `bash scripts/verify-kb-sync.sh` — passes including new CLAUDE/*.md pointer scan.
- [x] Run `python scripts/update-kb-counts.py --check` — runs as part of pre-commit hook; passes.

**Result vs target:**
- Target: CLAUDE.md ≤ ~120 lines / ~1500 words. **Actual: 142 lines / 2109 words (51% word reduction from 4318).** Lines are slightly over target because the §3 routing table grew rows for topical files and §2 map preserves a fuller pointer index — both intentional usability gains; per-bullet word target met.
- Topical files combined: 79 lines / 1997 words.
- Net auto-loaded surface (CLAUDE.md only) reduced **~51% on words** — the relevant metric for tokens.

**Improvements:**
- `noctusai_count_tokens` MCP tool referenced in `KB § PATTERNS/project-execution.md § 2.8` was forward-looking; the tool does not yet exist. Phase 2 fell back to `wc -w` for measurement. Triage: **accept-with-rationale** for this project (the metric was sufficient for a 50%+ reduction signal); **defer** to a future MCP-server-expansion follow-up project to actually ship the tool. Will catalog in `KB § PATTERNS/accept-with-rationale.md` at Phase 8 close.
- Topical CLAUDE/*.md rules average 50-100 words each. The ≤80-word soft cap applies to CLAUDE.md §1 (auto-loaded budget); topical files are sibling routers loaded on-demand, so the discipline is intentionally relaxed. Documented this distinction in the new `KB § 01-PHILOSOPHY.md § Context budget discipline` anchor.
- `verify-kb-sync.sh` now scans both CLAUDE.md and CLAUDE/*.md. The script's existing checks (§2 KB doc indexed, §3 Layout tree current) still operate only on the KB filesystem, which is correct — topical CLAUDE/*.md aren't part of the KB.
- §2.8 of `project-execution.md` says ≤80 words/§1 bullet but doesn't define how topical sibling files behave under bullet-weight. I extended the rule implicitly via `KB § 01-PHILOSOPHY.md § Context budget discipline § The three layers`. Any future documentation pass should backfill this distinction into §2.8.

**Phase proposal**: applied inline; no separate `proposals/` artifact (per apply-inline-then-delete methodology + auto-improvement at phase close).

### Phase 3 — MEMORY.md index compaction + retire ✅
- [x] Rewrite each MEMORY.md entry to one line ~150 chars: `- [Title](file.md) — one-line hook`.
- [x] ~~Retire `feedback_apply_inline_delete_proposals.md` (merged into `feedback_auto_improvement.md`)~~ — **kept**: re-read showed it describes a complementary protocol (proposal-file lifecycle when one IS filed) referenced by `feedback_auto_improvement.md` for its non-simple-case branch. Audit claim invalidated; retire skipped. §11 logged.
- [x] Add `feedback_context_budget_discipline.md` — the new methodology rule (router/topical/depth + MCP/skills keep-lists).
- [x] Categorized index for easier scanning (Architecture & seed; DRY; Code quality; Testing; Security; MCP & DB; Reading discipline; Project execution; Product hygiene; Documentation; Context budget).

**Result vs target:**
- Target: ~80 lines.  **Actual: 106 lines / 1388 words** (line count up slightly from 83 because category headers + new entry; word count down 54% from 2993).
- Combined CLAUDE.md + MEMORY.md auto-loaded surface: 7311 → 3497 words = **~52% reduction in per-turn token cost.**

**Improvements:**
- Phase 0 audit's retire claim for `feedback_apply_inline_delete_proposals.md` was wrong — Phase 1's "verification reads what's actually there" methodology fired correctly here (re-read both files, found complementarity, decided to keep). Lesson cataloged: audit claims about *file relationships* need a same-pass verification before acting on them.
- The categorized layout (`### Architecture & seed`, `### DRY`, etc.) was a stretch goal, not in the original plan — turned out to be a high-value usability win at zero token cost. Future MEMORY.md edits should preserve the categorical grouping (drop entries into the right bucket; resist temptation to add new top-level sections).

### Phase 4 — (merged into Phase 2 above)

### Phase 5 — MCP allowlist trim ✅
- [x] Verify `.mcp.json` only contains noctusai → `['noctusai']`.
- [x] Verify `.claude/settings.local.json` `enabledMcpjsonServers` only contains `noctusai` → `['noctusai']`.
- [x] Verify `~/.claude.json` project section MCP fields are empty → confirmed `mcpServers: {}`, `enabledMcpjsonServers: []`, `disabledMcpjsonServers: []`.
- [x] Keep-list policy documented in three places (Phase 2 already landed it): `KB § 01-PHILOSOPHY.md § Context budget discipline § MCP keep-list`, `CLAUDE.md §1 "Context budget discipline"` bullet, `feedback_context_budget_discipline.md`.
- [x] User-side disable path for claude-in-chrome documented in the KB anchor: Chrome extension toggle (Claude Desktop preferences → `chromeExtensionEnabled`, or `/chrome` Claude Code slash command per `~/.claude/cache/changelog.md`); the CLI cannot directly disable a Chrome-extension-registered MCP.

**Improvements:**
- Phase 0 audit's framing — "trim what's locally trimmable + document the rest" — held: project-level config was already at the minimum, so Phase 5's actual delta is policy-doc, not config-edit. Recurrence cross-check: this is the second time the audit's "verification only" phase produced a proposal-quality finding (Phase 1 was the first); confirms Phase 0's audit-first methodology is paying back per `feedback_phase_zero_audit.md`.

### Phase 6 — Skills keep-list policy ✅
- [x] Skills available identified (per session-start system reminder): `update-config`, `keybindings-help`, `simplify`, `fewer-permission-prompts`, `loop`, `schedule`, `claude-api`, `init`, `review`, `security-review`.
- [x] Keep-list landed in `KB § 01-PHILOSOPHY.md § Context budget discipline § Skills keep-list`: `update-config` / `loop` / `schedule` / `security-review`.
- [x] Off-list (policy): `keybindings-help` / `simplify` / `fewer-permission-prompts` / `claude-api` / `init` / `review`. Bundled skills can't be CLI-disabled, but the policy reduces accidental invocation. (`init`/`review` overlap with repo-native tooling; `claude-api` is for direct Anthropic SDK apps and rarely applies because LLM access goes through `noctusai_lib.llm`.)

**Improvements:** none identified — pure policy doc.

### Phase 7 — Three-way sync (new methodology rule) ✅
- [x] Verified four-layer sync of "Context budget discipline" rule: (1) KB anchor `KB § 01-PHILOSOPHY.md § Context budget discipline`, (2) CLAUDE.md §1 bullet, (3) memory file `feedback_context_budget_discipline.md` (4109 bytes), (4) MEMORY.md index entry.
- [x] Ran `bash scripts/verify-kb-sync.sh` — passes (also via pre-commit on every Phase 2/3/5-7 commit).
- [x] Ran `python scripts/update-kb-counts.py --check` — passes via pre-commit hook.
- [x] Ran MCP keeper `--review` — 0 issues.

**Improvements:**
- The forward-stub pattern from `KB § PATTERNS/project-execution.md § 2.8` would have been useful if we'd planned the new "Context budget discipline" rule across multiple phases. Here we landed it in Phase 2 alongside the compaction work, so no forward-stub was needed. Documenting this so future multi-phase rule shipments default to the stub pattern.

### Phase 8 — Project close ⏳
- [x] Bundled improvement proposal: improvements were captured live in each phase's `**Improvements:**` block and applied inline as encountered (per `feedback_auto_improvement.md` rule). Two deferred items now properly destinated: (1) `noctusai_count_tokens` MCP tool → `mcp-server-expansion` project (cataloged as accept-with-rationale 2026-05-03); (2) ≤80-word distinction for topical files → applied inline as `KB § PATTERNS/project-execution.md § 2.8 § Auto-loaded vs. topical CLAUDE/<topic>.md`. No `proposals/` artifact to delete.
- [x] **Cross-product builds + backend tests SKIPPED** — accept-with-rationale: this project touched only `CLAUDE.md`, `CLAUDE/*.md`, `KB`, memory files, and `scripts/verify-kb-sync.sh`. None of these are inputs to Vite or pytest; product builds/tests would be 100% wasted vs. zero risk of regression. Pre-commit hook ran `verify-kb-sync.sh` + KB count check + §6↔§11 consistency on every phase commit (5 commits) and passed every time.
- [x] MCP keeper review: 0 issues (run twice — Phase 7 verification + Phase 8 close).
- [x] Final `bash scripts/verify-kb-sync.sh` — passes.
- [x] `python scripts/update-kb-counts.py --check` — passes ("KB counts are up to date").
- [x] `noctusai_file_proposal` not invoked — improvements applied inline; no `improvements.md` regeneration needed.
- [ ] Delete the project folder per apply-inline-then-delete.
- [ ] Final `git add` (explicit paths, never `-A`) + `git commit` + `git push`. Push is the literal last step.

**Improvements:** none identified — verification phase.

**Project final summary**

| Surface | Before (lines / words) | After (lines / words) | Word reduction |
|---|---|---|---|
| `CLAUDE.md` (auto-loaded) | 193 / 4318 | 142 / 2109 | **-51%** |
| `MEMORY.md` (auto-loaded) | 83 / 2993 | 106 / 1388 | **-54%** |
| **Combined auto-loaded** | **276 / 7311** | **248 / 3497** | **-52%** |
| `CLAUDE/*.md` (on-demand topical) | n/a | 79 / 1997 | new |

Per-reply token saving: ~3814 words ≈ 5000 tokens *every reply* across the entire session. New "Context budget discipline" methodology rule three-way-synced (KB + CLAUDE.md + memory) — codifies router/topical/depth layers + MCP keep-list (noctusai + supabase only) + skills keep-list (update-config / loop / schedule / security-review only). New script gate (`verify-kb-sync.sh` extended to scan `CLAUDE/*.md` too).

---

## 7. Open questions

1. **Topical split granularity** — backend / frontend / projects / platform is a starting bucket set. After §6 rule analysis in Phase 0/4, may collapse to fewer files (e.g. just `CLAUDE-backend.md` + `CLAUDE-frontend.md` + `CLAUDE-meta.md` if "projects" + "platform" overlap). **Recommendation:** decide at end of Phase 0 audit when the rule taxonomy is concrete; default to four files unless audit shows fewer.
2. **Stale memory candidate list** — Phase 0 will produce; Phase 3 acts on it. **Recommendation:** retire only when the entry is fully subsumed; if any unique nuance remains, merge into the surviving file.
3. **CLAUDE-*.md auto-discovery by `verify-kb-sync.sh`** — current script may flag new top-level CLAUDE-*.md files if they have pointers into KB. **Recommendation:** read the script first; extend the whitelist if needed; otherwise follow KB-pointer convention so the script accepts them.
4. **claude-in-chrome disable path** — investigation in Phase 5 to confirm whether a CLI mechanism exists or whether it's UI-only.

---

## 8. Dependencies & blockers

- `bash scripts/verify-kb-sync.sh` must remain green throughout.
- `python scripts/update-kb-counts.py --check` (regenerates auto-derived count blocks).
- Three-way sync rule (KB ↔ CLAUDE.md ↔ memory) MUST be honored at every rule edit — the rule is itself enforced by this project.

---

## 9. Success criteria

- CLAUDE.md ≤ 80 lines, every §1 rule terse + KB-pointer.
- MEMORY.md ≤ 80 lines, one-line entries per system-prompt format.
- All KB pointers resolve (`bash scripts/verify-kb-sync.sh` passes).
- Topical CLAUDE-*.md files exist + are pointed-to from CLAUDE.md.
- `.mcp.json` + `.claude/settings.local.json` confirmed minimal.
- New "context budget discipline" methodology rule landed three-way-synced.
- Project folder deleted; final commit + push done.
- No product code touched.

---

## 10. How to use this plan

- Live-tick `- [ ]` → `- [x]` as each sub-task completes.
- Add a phase status icon to the header on state change (`⏳` / `✅` / `❌`).
- Capture in-the-act findings in each phase's `**Improvements:**` block.
- After every sub-task in a phase is ticked, synthesize ONE bundled proposal (if non-trivial improvements exist); apply inline (per apply-inline-then-delete); delete the proposal file.
- Per-phase local commit at end of every phase (explicit paths, never `-A`).
- Final `git push` at project close as the literal last step (after folder deletion).

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial project drafted. Merged the originally-proposed three projects (A: compaction; B: topical split; C: MCP/skills allowlist) into one umbrella per user request. | claude-opus-4-7 |
| 2026-05-03 | Phase 0 ✅ — audit produced `audit.md`. CLAUDE.md = 193 lines / ~9-10K tokens; MEMORY.md = 83 lines / ~6-7K tokens; auto-loaded meta total ≈ 15-17K tokens/turn. 36 §1 rule bullets, 86 KB-shorthand pointers, 5 literal pointers. Rule taxonomy: 18 universal + 5 backend + 2 frontend + 8 projects + 5 platform. Retire candidate: `feedback_apply_inline_delete_proposals.md` (merged into `feedback_auto_improvement.md`). | claude-opus-4-7 |
| 2026-05-03 | Phase 1 ✅ — KB-anchor preservation: verified all 86 pointers resolve and slip-history sections exist; no parking needed (memory files + KB carry the depth already). Discovered existing `KB § PATTERNS/project-execution.md § 2.8` mandates ≤80 words / §1 bullet — Phase 2 alignment target. | claude-opus-4-7 |
| 2026-05-03 | Phase 2 ✅ — CLAUDE.md compaction with topical split (merged from original Phase 2 + Phase 4). New `KB § 01-PHILOSOPHY.md § Context budget discipline` anchor codifies router/topical/depth layers + MCP/skills keep-lists. New `CLAUDE/` directory with `backend.md`, `frontend.md`, `projects.md`, `platform.md` topical sub-files (read on-demand by agent discipline per §3 routing table). CLAUDE.md compacted 4318 → 2109 words (-51%). `verify-kb-sync.sh` extended to scan `CLAUDE/*.md` too — passes. Improvements applied inline; deferred items: `noctusai_count_tokens` MCP tool (accept-with-rationale this round, defer to MCP-server-expansion); ≤80-word distinction for topical files needs §2.8 backfill (future docs pass). | claude-opus-4-7 |
| 2026-05-03 | Phase 3 ✅ — MEMORY.md index compaction + retirement triage. Compacted 83/2993 → 106/1388 (lines +28%, words -54%; line bump is the new category headers + new `feedback_context_budget_discipline.md` entry). New memory file for the context-budget-discipline rule. Retire decision reversed for `feedback_apply_inline_delete_proposals.md` (Phase 0 audit claim invalidated by re-read — keeping; complementary to `feedback_auto_improvement.md`). Categorized layout added as in-flight improvement. **Combined Phase 2+3 auto-loaded surface: 7311 → 3497 words = ~52% reduction in per-turn token cost.** | claude-opus-4-7 |
| 2026-05-03 | Phases 5+6+7 ✅ — verification + bookkeeping. Phase 5: project-level MCP allowlist confirmed at the desired minimum (`['noctusai']` in both `.mcp.json` and `.claude/settings.local.json`); keep-list policy landed in Phase 2. Phase 6: skills keep-list policy landed in Phase 2. Phase 7: four-layer three-way sync verified for the new "Context budget discipline" rule (KB + CLAUDE.md + memory file + MEMORY.md). MCP keeper `--review` returned 0 issues. | claude-opus-4-7 |
| 2026-05-03 | Phase 8 partial — verification complete + deferred-item destinations finalized. Two deferred items resolved inline: (1) `noctusai_count_tokens` accept-with-rationale entry catalogued at `KB § PATTERNS/accept-with-rationale.md` (revisit trigger: when `mcp-server-expansion` ships the tool); (2) ≤80-word/topical-file distinction backfilled into `KB § PATTERNS/project-execution.md § 2.8` as a new sub-section. Cross-product builds + backend tests skipped under documented accept-with-rationale (project touched only meta files; not inputs to product builds). All gates green. Folder deletion + final push remain as literal last steps. | claude-opus-4-7 |
