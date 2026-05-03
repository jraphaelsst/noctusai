# Phase 0 — Audit

## Sizes (current state)

| Surface | Lines | Bytes | Tokens (~est) | Loads |
|---|---|---|---|---|
| `CLAUDE.md` | 193 | 4318 words | ~9-10K | every turn |
| `MEMORY.md` (index) | 83 | 2993 words | ~6-7K | every turn |
| Total auto-loaded meta | 276 | 7311 words | **~15-17K** | every turn |
| Individual `feedback_*.md` files | 52 files | 348K dir | – | on demand |
| Individual `project_*.md` files | 14 files | included | – | on demand |
| KB CONTEXT files | 7 files | 165K (largest 45K) | – | on demand |
| KB PATTERNS files | ~18 files | – | – | on demand |

## CLAUDE.md anatomy

- 36 §1 behavioral-rule bullets (each 3-8 lines of paragraph body).
- 86 KB-shorthand pointers (`KB § X`) — *not* checked by `verify-kb-sync.sh` (script only validates literal backtick `KNOWLEDGE-BASE/…md` paths).
- 5 literal `KNOWLEDGE-BASE/…md` pointers — *are* script-checked.
- `verify-kb-sync.sh` checks: (a) literal pointers resolve, (b) every KB doc is referenced *by name* in `INDEX.md`, (c) Layout tree in `INDEX.md` reflects FS.

**Implication for compaction:** the verify script is permissive — we can shrink the body of every rule without breaking it, as long as we don't introduce a new literal `KNOWLEDGE-BASE/…md` pointer to a non-existent file or add a new top-level KB doc without updating INDEX.md.

## Rule taxonomy (for Phase 4 topical split)

Bucketed from current §1 bullets (36 rules):

### Universal (stays in always-loaded `CLAUDE.md`) — ~18 rules
- Vocabulary — methodology not doctrine
- Seed-is-the-skeleton (foundational, applies to every change)
- No incomplete commits
- No quick fixes
- No workarounds — no monkey-patching (production OR tests)
- Estimate off evidence, not structure
- DRY (the recurrence rule)
- Narrow-read first
- Explore-agent delegation
- Replication-to-seed symmetry
- AST-first — never regex code edits
- The recurrence rule (formalize at threshold)
- Absorption-search is a standing duty
- Triage at decision time
- No silent errors
- Three-way sync (KB ↔ CLAUDE.md ↔ memory)
- Finish the session — verify, don't assume
- Methodology vocabulary

### Backend (`CLAUDE-backend.md`) — ~5 rules
- Module-scope imports
- FastAPI dep factories defer config to request time
- MCP migrations mirror the file
- Supabase MCP — use proactively
- Webhook receivers verify before any side effect

### Frontend (`CLAUDE-frontend.md`) — ~2 rules
- Componentize everything (frontend lens; check shared lib first)
- Gamification is subtle

### Projects / execution (`CLAUDE-projects.md`) — ~8 rules
- Phase 0 audits — expand loudly on invalidation
- The execution workflow (top-to-bottom)
- Commit per phase, push at project close
- §6 ↔ §11 consistency self-check
- Active robustness review during execution
- Projects live next to the code they touch (three locations)
- Auto-improvement at phase close — apply, don't ask
- Every product has README + MASTER-PROMPT

### Platform / cross-cutting (`CLAUDE-platform.md`) — ~5 rules
- MCP toolkit reviews after every change (keeper observation-only)
- MCP-first — agent-exposable capabilities default to MCP
- Clean folder — every artifact has a home
- LGPD-first
- (componentize-everything's "shared lib first" lens crosses here)

### Meta (stays in `CLAUDE.md` — token-budget rule itself)
- CLAUDE.md vs KB — token budget rule (becomes more important after this project)

**Total**: 36 → 18 universal + 18 topical. Estimated savings on always-loaded CLAUDE.md: 50%+ when bodies trim to terse rule + pointer.

## Memory file retire / merge candidates

Initial scan — Phase 3 will confirm:

| Surviving file | Retire / merge candidate(s) | Rationale |
|---|---|---|
| `feedback_seed_first_at_authoring_time.md` | (keep both — they cover different angles) | The "Always" rule is the seed-compliance fact; the "Authoring time" rule is the §3a refinement. Both are referenced in CLAUDE.md. |
| `feedback_three_way_doc_sync.md` | (none) | The canonical three-way-sync rule. |
| `feedback_execution_workflow.md` | Subsumes parts of `feedback_phase_zero_audit.md`, `feedback_active_robustness_review.md`, `feedback_apply_inline_delete_proposals.md` | Workflow is the umbrella; the others are individual phases of the workflow. **Decision: keep all (each is independently referenced); add cross-pointers in MEMORY.md hooks**. |
| `feedback_no_auto_commit.md` | (none — supersedes itself in-place) | Updated 2026-05-03 with the per-phase + project-close carve-outs. |
| `feedback_silent_ok_is_not_a_substitute_for_logging.md` + `feedback_no_silent_errors.md` | (keep both, distinct) | Silent-OK is the specific anti-pattern; no-silent-errors is the umbrella principle. |
| `feedback_apply_inline_delete_proposals.md` + `feedback_auto_improvement.md` | merge candidate | `feedback_auto_improvement.md` is essentially the 2026-05-02 amendment to `apply_inline_delete_proposals`; both describe phase-end proposal handling. **Decision: merge into `feedback_auto_improvement.md` (the most-recent ruleset)** + retire `feedback_apply_inline_delete_proposals.md` after copying any unique nuance. |
| `feedback_end_of_work_summary.md` | (keep — distinct) | End-of-reply summary discipline. |
| `feedback_keeper_observation_only.md` + `feedback_keeper_warning_triage.md` | (keep both) | First is the principle; second is the triage protocol when warnings fire. |
| `feedback_replication_to_seed_slip.md` | (keep — slip-count history) | Personal slip log; load-bearing for self-correction. |
| `feedback_live_state_sync_discipline.md` | merge into `feedback_replication_to_seed_slip.md`? | Both are slip-history. **Decision: keep separate — different patterns being tracked**. |

**Retire-this-round**: `feedback_apply_inline_delete_proposals.md` (merged into `feedback_auto_improvement.md`).

**Other candidates examined and kept**: 65/66 files. The bulk of memory files are unique behavioral rules.

## MCP allowlist state

| Surface | Currently exposes | Action |
|---|---|---|
| `.mcp.json` | `noctusai` only | ✅ Already minimal; document policy in CLAUDE.md/KB |
| `.claude/settings.local.json` `enabledMcpjsonServers` | `noctusai` only | ✅ Already minimal |
| `~/.claude.json` (project section) `mcpServers` | empty | ✅ Already minimal |
| `~/.claude.json` (project section) `enabledMcpjsonServers` | empty | ✅ Already minimal |
| `mcp__claude-in-chrome__*` (deferred tool list) | Loaded by Chrome extension auto-registration | ⚠ CLI cannot disable — user must toggle in Chrome extension or via Claude.ai connector settings |
| `mcp__claude_ai_*` (deferred tool list) | Catalog of claude.ai connectors (most unauth-stub) | ⚠ Catalog-level, not project-config-level. The "active" ones (Supabase, Excalidraw, Mermaid Chart, Google Calendar, AWS Marketplace, LunarCrush) are user-account-level integrations |

**Conclusion for Phase 5**: project-level config is already at the desired minimum. The `claude-in-chrome` and `claude_ai_*` surfaces are managed outside the project — document the keep-list policy + the disable path so future agents know where to point the user.

## Skills available

From session-start system reminder:
- `update-config` — keep (used for harness config edits)
- `keybindings-help` — drop (rare)
- `simplify` — drop (rare; superseded by repo's review/MCP toolkit)
- `fewer-permission-prompts` — drop (rare; user explicitly approves on-the-fly)
- `loop` — keep (recurring tasks)
- `schedule` — keep (background routines)
- `claude-api` — drop (this repo doesn't build Claude API apps directly; LLM access goes through `noctusai_lib.llm`)
- `init` — drop (CLAUDE.md already exists; not initializing fresh repos)
- `review` — drop (repo has its own MCP keeper review)
- `security-review` — keep (occasional security passes; lightweight)

**Keep-list**: `update-config`, `loop`, `schedule`, `security-review`. **Drop-list (policy)**: the rest. Note: bundled skills can't be CLI-disabled, but encoding the policy reduces accidental invocation.

## Decisions captured for downstream phases

- Phase 1 KB-anchor parking is *light*: most slip-counts / caught-instances are already in the matching memory file's body. The rare KB anchor that's missing principle-level depth gets a brief append.
- Phase 2 CLAUDE.md compaction trims aggressively to one-line rule + pointer.
- Phase 3 retires only `feedback_apply_inline_delete_proposals.md` (merged into `feedback_auto_improvement.md`).
- Phase 4 splits 36 rules → 18 universal + 5 backend + 2 frontend + 8 projects + 5 platform.
- Phase 5 documents keep-list policy; no .mcp.json edits needed.
- Phase 6 documents skills keep-list policy; no harness-side edits needed.
