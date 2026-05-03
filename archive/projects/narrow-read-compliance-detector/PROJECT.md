# Narrow-Read Compliance Detector — Concept Stub (Infeasible Today)

> **This is a living document, not a rigid checklist.**
> Filed 2026-05-02 as a deliberate Concept stub. The user
> recognized in the QA audit that this gap (a keeper detector
> that flags whole-file Read calls when an outline would have
> sufficed) is *"probably infeasible"* — and they're right: it
> requires agent-runtime telemetry that doesn't exist as a
> detector-accessible surface today. This document preserves
> the design context so a future agent (or a future runtime
> change) inherits the reasoning instead of re-deriving it.
>
> **Status: Concept — INFEASIBLE today. Do NOT start work
> without explicit user reactivation triggered by a runtime
> change.** §6 is intentionally empty. §7 names the runtime
> capabilities that would unblock the work.

- **Created:** 2026-05-02
- **Last updated:** 2026-05-02
- **Status:** Concept — infeasible today. §1, §2, §5, §7
  populated; §6 intentionally empty pending agent-runtime
  telemetry surface + user reactivation.
- **Owner / stakeholders:** Raphael · future zero-context execution agent
- **Related docs:** `CLAUDE.md § Engineering Philosophy § Narrow-read first`; `KB § PATTERNS/agent-reading-discipline.md` (the rule this detector would enforce); `mcp/noctusai/tools/outline_python.py` + `outline_typescript.py` (the alternatives the detector would point users toward); `projects/mcp-ast-tools-hardening/PROJECT.md` (sibling — the AST tools whose adoption this detector would enforce); root `MCP-AST-HARDENING-ROLLOUT.md` (orchestration).
- **Project slug:** `narrow-read-compliance-detector` — cross-product / platform-infra scope, lives at root `projects/`.

---

## 1. Context & Purpose

The narrow-read rule (CLAUDE.md §1, shipped 2026-05-02 by
`methodology-extraction`) says: for any file >200 lines or
unfamiliar shape, default to **structure before bodies** — call
`outline_python` / `outline_typescript`, then `Read offset=<line>
limit=N` only the symbols you actually need.

The QA audit on the AST tools (2026-05-02) named gap C.11 — a
hypothetical keeper detector that would flag agent sessions where
a `Read` of N lines was issued on a file the outline tool would
have served better. The user immediately suspected this was
infeasible; this Concept stub records the reasoning.

The audit's exact phrasing:

> *"No keeper that flags 'agent Read'd 600 lines when outline
> would have sufficed'. Out-of-scope for the AST tools themselves;
> this is the natural Phase-3 follow-up to the narrow-read rule
> once we have data."*

The user response was: *"i guess defer8 and 11 we wont be able,
but if it would be possible, do it already."*

Verdict: **C.11 is not feasible today.** Filed as a Concept stub
so that:
1. A future agent doesn't re-propose the same idea without
   inheriting the infeasibility analysis.
2. If the runtime gains the missing telemetry surface (see §7),
   reactivation is one user prompt away.

---

## 2. Confirmed constraints

- **The user expects this to be infeasible.** *(Drives: file as
  Concept stub, not active project; document the infeasibility;
  do not draft phases.)*
- **If feasible later, ship it.** *(Drives: §7 names the
  unblocking conditions; reactivation gate is documented.)*
- **Don't over-engineer the stub.** *(Drives: short doc; minimal
  ceremony; high signal-to-noise on the infeasibility itself.)*

---

## 3. Design principles (provisional — confirm if reactivated)

1. **The detector would observe, not enforce.** Like other
   keeper detectors, it would emit issues at WARNING / INFO
   severity — not block CI on a single Read call.
2. **The signal would need a session-level lens, not a per-call
   lens.** "User read this 600-line file once" isn't necessarily
   wrong; "user repeatedly reads large files without ever
   calling outline_*" is. So the detector consumes a
   session-level transcript / event log, not an instantaneous
   tool-call event.
3. **Best target shape: a post-session transcript walker.**
   Run as part of an `--review-session` MCP tool that ingests
   the conversation transcript, tallies tool-call patterns,
   emits a narrow-read-compliance score.

---

## 3a. Seed-first analysis

Concept stage — no implementation. Re-run §3a checklist when
reactivated.

---

## 4. Scope

**In scope (when reactivated):**

- A keeper detector or `--review-session` MCP tool that walks an
  agent transcript and flags narrow-read non-compliance.
- Surface in the existing `mcp/noctusai/cli.py --review` family.

**Out of scope:**

- Modifying the agent runtime itself (we don't own that).
- Mid-session intervention (would require runtime hooks).

---

## 5. Architecture / data model (sketch only)

If reactivated, a likely shape:

- Input: a **transcript** in some agreed format (JSONL with
  `tool_calls`, `tool_results`, file paths + sizes per Read).
- Logic:
  - For each `Read(file_path, offset=None, limit=None)` call,
    look up the file's actual line count.
  - For files >200 lines where `offset=None` and `limit=None`,
    check whether an `outline_python(path)` /
    `outline_typescript(path)` call preceded it in the transcript.
  - If not, flag as narrow-read-non-compliant.
- Output: detector-shaped issue list (`{path, line, severity,
  message, suggestion}`) consumable by the existing `--review`
  reporter.

The detector would NOT have access to the actual conversation
the user had with the agent — only the tool-call event stream.

---

## 6. Implementation phases

*(intentionally empty — INFEASIBLE today; do not draft phases
without runtime change + user reactivation; see §7)*

---

## 7. Open questions (the unblock list)

1. **Where does the agent-session transcript live?** **Today: the
   transcript is not exposed to MCP detectors.** Claude Code
   stores session state but doesn't surface a structured
   tool-call log to user-space MCP tools. *Unblocks when:* a
   transcript export API ships (Anthropic side) OR the user
   captures sessions to a file the detector can read.
2. **What's the format / schema?** TBD — depends on what
   ships. Likely JSONL with `{tool_name, args, result_size,
   timestamp}` per call.
3. **How does the detector get triggered?** Today's keeper
   detectors run against repo files at static-analysis time. A
   transcript walker would need a different trigger — e.g.
   `python mcp/noctusai/cli.py --review-session
   <transcript-file>`. Decision deferred.
4. **What's the false-positive risk?** A user reading a large
   file once on purpose (e.g. full review) is legitimate. The
   detector must avoid punishing that. Likely needs a session-
   level threshold ("3+ large reads without any outline call")
   not a per-call rule.
5. **Reactivation triggers.** This project moves to active when
   any of the following happens:
   - Anthropic ships a transcript export / event-log API.
   - The user starts capturing sessions to a file the toolkit
     can read.
   - The `mcp-ast-tools-hardening` + `ast-callers-consolidation`
     projects close AND the user explicitly says
     *"check transcript-exposure status; if available, file a
     phase plan"*.

---

## 8. Dependencies & blockers

- **Hard blocker: no agent-runtime telemetry surface for MCP
  detectors today.** Without one, this project cannot start.
- **Soft dependency: parent `mcp-ast-tools-hardening` close.**
  Until the AST tools are catalog-listed and stable, even a
  hypothetical detector wouldn't have a clean recommendation
  to point users toward.

---

## 9. Success criteria (sketch — confirm at reactivation)

- A keeper detector or session-review tool exists that, given a
  transcript, can identify narrow-read non-compliance.
- Documented in `KB § 06-AGENTS.md`.
- Pinned by a `Test<CamelCase>` regression class.
- Severity calibrated against real session data (not theory).

---

## 10. How to use this project

This is a **Concept stub** — the only valid use today is reading
it before re-proposing the same idea. If you find yourself about
to file "let's add a narrow-read keeper" as a fresh project:
**stop and read this file first.** §7 is the unblock list.

```bash
# Read this file
sed -n '1,200p' projects/narrow-read-compliance-detector/PROJECT.md

# Check if any of the §7 unblock triggers fired
ls ~/.claude/projects/*/transcripts/ 2>&1   # transcript export locally?
gh api repos/anthropics/claude-code/releases | head -50  # runtime release notes?
```

If §7 Q5 reactivation triggers fire, ask the user explicitly
before drafting §6 phases.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | Initial Concept stub filed during the QA-audit rollout (`MCP-AST-HARDENING-ROLLOUT.md`). User identified C.11 as probably-infeasible; agent confirmed: requires agent-runtime telemetry not exposed to MCP detectors today. Filed to preserve the design context + reactivation triggers in §7 for future agents (CLAUDE.md rule: deferred items naming follow-up projects MUST scaffold those projects from `templates/PROJECT-TEMPLATE.md`). §6 intentionally empty. | Claude Opus 4.7 |
