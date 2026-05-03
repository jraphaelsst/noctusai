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

### Phase 2 — CLAUDE.md compaction
- [ ] Rewrite §1 — each bullet becomes: terse rule + 1-clause why-it-matters + KB pointer. Drop paragraph bodies, mantras, parenthetical examples.
- [ ] Rewrite §2 (The Map) — keep, already terse.
- [ ] Rewrite §3 (When to read what) — keep / lightly trim.
- [ ] Rewrite §4 (Sync rule) — keep, already concise.
- [ ] Run `bash scripts/verify-kb-sync.sh` — must pass.
- [ ] Target: ~60-80 lines.

### Phase 3 — MEMORY.md index compaction + retire
- [ ] Rewrite each MEMORY.md entry to one line ~150 chars: `- [Title](file.md) — one-line hook`.
- [ ] Identify retire candidates (duplicates, superseded, stale).
- [ ] Delete retired files; remove their MEMORY.md entries.
- [ ] Target: ~80 lines.

### Phase 4 — Topical CLAUDE.md split
- [ ] Bucket §1 rules into universal vs. backend / frontend / projects / platform.
- [ ] Move topical rules into `CLAUDE-<topic>.md` (top-level repo files) with rule + pointer format.
- [ ] CLAUDE.md gains a routing block: "When doing backend code, also read CLAUDE-backend.md" etc.
- [ ] Document the loading discipline as a new behavioral rule in CLAUDE.md.
- [ ] Run `bash scripts/verify-kb-sync.sh` — must still pass (will need updating to recognize CLAUDE-*.md if applicable; likely just whitelist).

### Phase 5 — MCP allowlist trim
- [ ] Verify `.mcp.json` only contains noctusai. (Already true.)
- [ ] Verify `.claude/settings.local.json` `enabledMcpjsonServers` only contains `noctusai`. (Already true.)
- [ ] Document keep-list policy: noctusai + supabase only. claude-in-chrome rare, intentionally not in the keep-list.
- [ ] Document the user-side disable path for claude-in-chrome (Chrome extension → toggle, or Claude.ai connector settings) since CLI can't disable a Chrome-extension MCP.
- [ ] Land the policy in CLAUDE.md (or CLAUDE-platform.md if topical split is by then live).

### Phase 6 — Skills keep-list policy
- [ ] Identify which Claude Code bundled skills are actually used (`update-config`, `schedule`, `loop` likely yes; `init`, `review`, `security-review`, `keybindings-help`, `simplify`, `fewer-permission-prompts`, `claude-api` likely no in this repo).
- [ ] Document keep-list policy in CLAUDE.md.

### Phase 7 — Three-way sync (new methodology rule)
- [ ] Land new rule: "Context budget discipline — CLAUDE.md is a router; KB is depth; MCP/skills follow keep-list; new rules KB-first." Three-way sync: KB anchor + CLAUDE.md pointer + memory file + MEMORY.md index entry.
- [ ] Run `bash scripts/verify-kb-sync.sh`.
- [ ] Run `python scripts/update-kb-counts.py --check`.

### Phase 8 — Project close
- [ ] Bundled improvement proposal: read all phase Improvements blocks, synthesize ONE proposal at `projects/context-budget-overhaul/proposals/...`. Apply inline (per apply-inline-then-delete methodology). Delete the proposal file.
- [ ] Cross-product builds (mind: this project doesn't touch product code, but standard project-close ritual): `cd products/<one>/frontend && npx vite build` for spot-check.
- [ ] Backend tests: `pytest tests/` for any product where CLAUDE.md changes might be cited (none expected — meta only).
- [ ] MCP keeper review: `python mcp/noctusai/cli.py --review`.
- [ ] Final `bash scripts/verify-kb-sync.sh`.
- [ ] Run `python mcp/noctusai/cli.py --improvements <this-project>.md`.
- [ ] Delete the project folder per apply-inline-then-delete.
- [ ] Final `git add` (explicit paths, never `-A`) + `git commit` + `git push`. Push is the literal last step.

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
