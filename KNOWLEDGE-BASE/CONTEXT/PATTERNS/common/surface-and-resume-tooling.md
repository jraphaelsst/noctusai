# Surface-and-resume tooling — ergonomic no-bypass round-trip

**What this is.** Four MCP tools that close the friction gap in the surface-note pattern
(`KB § PATTERNS/common/dispatch-with-project-and-notes.md`): an agent that hits a wall
calls ONE tool, the tech-lead responds with ONE tool, the next dispatch gets a complete
brief automatically. Before this tooling, the friction of writing a well-formed surface
made `--no-verify` bypass feel cheaper; the tools make the round-trip cheap enough that
bypass has no justification.

---

## 1 · The problem this solves

The `dispatch-with-project-and-notes.md` pattern says: alt route emerges → STOP → file
surface note → BLOCK → tech-lead responds. In practice the round-trip suffered two
friction points:

1. **Surface cost.** Writing a structured surface manually (frontmatter + body sections +
   worktree state snapshot) took ~15 minutes. Engineers bypassed with `--no-verify`.
2. **Resume context loss.** The resumed agent got a brief but no shared memory of what the
   previous agent knew — it re-read context from scratch, wasting 40+ minutes per resume.

These tools close both gaps: surface cost → 1 tool call; context loss → `dispatch_resume_brief`
composes the full brief from the original + surface + response automatically.

---

## 2 · The four tools

### 2.1 `noctus.dev.surface_to_tech_lead`

Called by a BLOCKED agent. One call captures:

- Worktree state snapshot: `git diff` bytes, dirty file list, uncommitted count, current SHA
- Writes `.claude/dispatches/<wt-slug>/surface-<iso-ts>.md` with YAML frontmatter:
  ```yaml
  surface_id: <slug>-<ts>
  worktree: <path>
  worktree_sha: <sha>
  reason: <reason>
  state_snapshot:
          diff_bytes: <n>
          dirty_files: [<list>]
          uncommitted_count: <n>
  attempted_resolution: |
      <md>
  status: pending-response
  ts: <iso>
  ```
- Returns `SurfaceReceipt` with `exit_marker_msg` — the agent prints this verbatim as its
  FINAL output line so orchestrators detect the block from tool results.

**Bypass rule:** calling `--no-verify` instead of this tool is FORBIDDEN. The tool makes
the surface cheap; the bypass makes the blocker invisible to the tech-lead.

### 2.2 `noctus.dev.list_pending_surfaces`

Read-only. Tech-leads call this at session start or after a dispatch wave to triage
blocked agents. Walks `.claude/dispatches/*/surface-*.md`, filters `status=pending-response`,
returns summaries (surface_id, worktree, reason, dirty-file count, age in hours).

Pass `include_responded=True` to see all surfaces including already-responded ones.

### 2.3 `noctus.dev.respond_and_resume`

Tech-lead response leg. Takes `surface_id`, `decision` (approve/reject/adapt),
`rationale_md` (required — this is the durable knowledge), optional `updated_brief_md`.

Actions:
1. Writes `.claude/dispatches/<wt-slug>/response-<surface_id>.md`
2. Updates surface frontmatter `status=responded`
3. Returns `ResumeBundle`: original brief excerpt (from brief_ledger), surface text,
   response text, worktree_state_pointer, resume_preamble

Security: `surface_id` validated against path-traversal (alphanumeric + `-._@` only).

### 2.4 `noctus.dev.dispatch_resume_brief`

Final leg. Takes `surface_id` (must already be responded to) and composes the full
dispatch-ready brief text. Pass this verbatim as the `Agent()` brief.

The composed brief includes:
- Resume preamble: worktree verification + file pointers + decision headline
- Original goal excerpt (from brief ledger if available)
- Full surface note body
- Full tech-lead response
- Cache-first reflex reminder (non-negotiable; spelled out once in the brief)
- Safety rules (stage-only / no --no-verify / worktree isolation)
- Worktree path + SHA for the resumed agent to verify

---

## 3 · The round-trip in sequence

```
Agent hits wall
  └→ noctus.dev.surface_to_tech_lead(reason, proposal_md, current_state_md, attempted_resolution_md)
       └→ .claude/dispatches/<wt-slug>/surface-<ts>.md (status=pending-response)
       └→ returns exit_marker_msg — agent prints it, exits

Tech-lead integration session
  └→ noctus.dev.list_pending_surfaces()
       └→ sees surface_id=<id>, reason, age
  └→ noctus.dev.respond_and_resume(surface_id, decision="approve", rationale_md="...")
       └→ .claude/dispatches/<wt-slug>/response-<surface_id>.md
       └→ surface status updated to responded
       └→ returns ResumeBundle
  └→ noctus.dev.dispatch_resume_brief(surface_id)
       └→ returns brief_text (the complete dispatch brief)

Tech-lead dispatches resumed agent
  └→ Agent(brief=brief_text, cwd=worktree_path)
       └→ resumes from where previous agent blocked
```

---

## 4 · Worked example: keeper-pattern-cache cwd-drift

**Background.** An engineer runs `--refresh-keeper-cache` from its worktree at
`.claude/worktrees/feature-x/`. The keeper cache is a Tier-1 shared SQLite at
`<git-common-dir>/noctusai/cache/keeper-patterns.sqlite`. The refresh script computes
`source_sha` from `compliance.py` at the worktree's path — but the keeper cache
`source_sha` check expects the primary's path. The `--check-keeper-cache-freshness`
keeper fires, blocking the pre-commit hook.

**Surface call (the agent):**
```python
surface_to_tech_lead(
    reason="keeper-cache-cwd-drift",
    proposal_md=(
        "The pre-commit hook fires check_keeper_cache_freshness and blocks because the "
        "keeper cache source_sha was computed from my worktree's compliance.py path, not "
        "the primary. I need guidance: should I (a) run --refresh-keeper-cache with the "
        "primary's path explicitly, or (b) use --worktree-path to redirect the cache "
        "refresh to the primary checkout?"
    ),
    current_state_md=(
        "pre-commit: check_keeper_cache_freshness FAIL — source_sha mismatch.\n"
        "My worktree: .claude/worktrees/feature-x/\n"
        "Staged files: mcp/noctusai/tools/noctus/dev/new_tool.py\n"
        "Ran: --refresh-keeper-cache (from my worktree cwd) — mismatch persists."
    ),
    attempted_resolution_md=(
        "Tried running --refresh-keeper-cache from the worktree. The cache refreshes "
        "but the sha mismatch fires anyway because the primary's compliance.py has a "
        "different sha (different file mtimes). Did NOT try --no-verify."
    ),
)
# Agent prints exit_marker_msg and stops.
```

**Tech-lead responds:**
```python
respond_and_resume(
    surface_id="feature-x-20260529T104500Z",
    decision="approve",
    rationale_md=(
        "Run --refresh-keeper-cache --worktree-path <primary-checkout-path>. "
        "The Tier-1 cache lives at <git-common-dir> (shared) but source_sha must match "
        "the PRIMARY compliance.py. Pass the primary worktree path so the refresh reads "
        "the right file. Primary path = `git worktree list --porcelain | head -2 | tail -1`."
    ),
)
```

**Resumed agent gets:**
```python
dispatch_resume_brief("feature-x-20260529T104500Z")
# → brief_text with: resume preamble + original goal + surface body + response + safety rules
```

The resumed agent runs `--refresh-keeper-cache --worktree-path <primary>`, hook passes,
commit lands. Total round-trip cost: ~5 minutes vs ~2 hours of --no-verify debugging.

---

## 5 · Anti-patterns

**(a) Bypass because "surfacing feels slow."**
The tooling makes the surface a 1-call operation + the resume a 1-brief-text operation.
Slow is no longer a valid reason. Bypass = block is invisible to tech-lead = silent-error shape.

**(b) Verbose `proposal_md` (> 200 lines).**
A surface exceeding 200 lines is a brief, not a surface. The proposal must capture WHY you're
blocked in ≤200 lines — the details live in the worktree's git state (the snapshot captures them).
The tool logs a warning on over-length proposals; trim before filing.

**(c) Response without rationale.**
`rationale_md` is REQUIRED in `respond_and_resume`. An empty rationale is rejected with an error.
Rationale = the durable knowledge that makes this round-trip worth more than just "proceed" —
it records WHY the tech-lead made the decision so the next agent AND the methodology both benefit.

**(d) Calling `dispatch_resume_brief` before `respond_and_resume`.**
The tool returns an error with explicit guidance: "Call noctus.dev.respond_and_resume first."
Sequencing is enforced at the tool layer, not by convention.

---

## 6 · File layout

```
.claude/dispatches/
  <wt-slug>/
    surface-<iso-ts>.md          # status: pending-response → responded
    response-<surface_id>.md     # written by respond_and_resume
```

The dispatches dir is in the PRIMARY checkout's `.claude/` (not per-worktree). All surfaces
from all worktrees land there, making `list_pending_surfaces` a fleet-level view.

---

## 7 · Composes with

- `KB § PATTERNS/common/dispatch-with-project-and-notes.md` — the underlying pattern
  (surface-note + delivery-note contract); these tools make the surface leg ergonomic.
- `KB § PATTERNS/architect/dispatch-engineer-tuning.md` — the brief template now includes
  the surface-and-resume tool names in its safety section.
- `KB § PATTERNS/common/brief-similarity-radar.md` — brief ledger is queried by
  `dispatch_resume_brief` for the original goal excerpt.
- `KB § PATTERNS/common/keeper-pattern-cache.md` — the worked example uses the
  keeper-cache cwd-drift as the motivating case.

---

## 8 · Provenance

Born 2026-05-29 to close the friction that drove the build-learn-cache `--no-verify`
rationalization: surfacing was too heavy, bypass felt cheaper. The tools make the
round-trip cheap + lossless (worktree state snapshot + composed resume brief). Cross-
references the bg-engineer-safety-discipline rule (in-flight codification at birth).
