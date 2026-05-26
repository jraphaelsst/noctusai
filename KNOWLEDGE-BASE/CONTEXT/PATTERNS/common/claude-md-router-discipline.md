# CLAUDE.md router discipline

> **The rule.** `CLAUDE.md` is the **always-on, auto-loaded router** — its budget compounds across *every* reply. It carries **PRINCIPLE + MAP**, never PROCEDURE or rule-bodies. Procedures live in `.claude/skills/` (auto-triggered on demand); depth lives in `KB § …` (read on demand). The router only *points*.

This is a Stage-4-codified pattern (`KB § PATTERNS/common/methodology-codification-pipeline.md`): the discipline below is enforced by the `check_claude_md_router` keeper, not left to habit.

## Why (the design reasoning)

The always-on layer and the on-demand layers have **different jobs**:

| Layer | Job | Carries |
|---|---|---|
| `CLAUDE.md` §1 (always-on) | the behavioral contract | **principle** — rule + one-clause why + `→` pointer |
| `.claude/skills/noc-*` (on-trigger) | the procedures | **the WHAT/how** (the steps + which tools) |
| `KB § …` (on-demand) | the depth | bodies, slip-history, examples |

An LLM applies a **principle** robustly and generalizes it to novel cases; an enumerated *procedure* only fires when the situation matches. So the always-on rule keeps the *why*; the *what* is recovered from the skill/pointer when actually needed. Putting procedure-bodies in the always-on file is **redundant** (the skills/pointers already carry them) and **expensive** (paid every turn).

## The synthesis (why this exact shape)

The v4.0 router was chosen by comparing three poles (all preserved in `backup/`):

- **original** (`backup/CLAUDE.md.bak`, ~11.7k words) — full bodies inline. Baseline.
- **aggressive** (`backup/CLAUDE-Aggressive.md.bak`) — §1 = operational *what* (redundant with skills); §2 = shortlist + `→ INDEX.md` (DRY-clean).
- **moderate** (`backup/CLAUDE-Moderate.md.bak`) — §1 = *why* (higher quality); §2 = full pattern list (duplicates `INDEX.md` → drift risk).

**Live = the synthesis:** moderate's **§1 (why-based)** + aggressive's **§2 (shortlist + `→ KB § INDEX.md`)**. Smallest, highest-quality, drift-free — `INDEX.md` stays the single canonical pattern roster (no parallel list to drift).

## Enforced invariants (`check_claude_md_router`)

Deterministic, commit-gating:

1. **Whole-file word budget** — `CLAUDE.md` ≤ `_CLAUDE_MD_MAX_WORDS` (2500). Blocks re-bloat toward the verbose original.
2. **§1 rules are one-line** — every `- **Rule.**` bullet is a single line carrying a `→` pointer (routes to its KB/skill depth) and ≤ `_CLAUDE_MD_MAX_RULE_WORDS` (60) words.
3. **§1 has no prose bodies** — only rule bullets + the section header + blanks/`---`/`>`. A non-bullet prose line in §1 IS the inlined-body tell.

Caps are one-line knobs at the top of the detector. The synthesis passes all three by construction.

## Mechanism (where it lives — Stage-4)

- **Detector:** `check_claude_md_router(repo_root)` in `mcp/noctusai/tools/noctus/dev/compliance.py` (mirrors `check_doc_symbology_drift`).
- **Validate gate:** registered in `check_all_products()` → runs under `noctus.dev.validate` (regression-baseline semantics — `KB § PATTERNS/compliance/compliance-regression-baseline.md`).
- **Commit gate:** `cli.py --check-claude-md-router` + a blocking block in `scripts/hooks/pre-commit` (fires when `CLAUDE.md` is staged).
- **Test:** `mcp/noctusai/tests/test_claude_md_router.py` (`TestClaudeMdRouter`, 6 cases).

**Activation note:** the installed git hook is a symlink to the main checkout's `scripts/hooks/pre-commit`, so the commit-gate goes live for all worktrees once this lands on `dev` (main repo on that tip). Until then it enforces on demand via `validate` + the CLI flag.

## Provenance
Born from the `harness-agents-skills` refactor (2026-05-25): the always-on budget was cut 11.7k→~1.5k words by re-homing procedures into `.claude/skills/` and personas into `.claude/agents/`. The "is aggressive really better?" comparison surfaced the principle-vs-procedure split — codified here so the router can't silently re-bloat. Siblings: `KB § PATTERNS/common/doc-symbology.md`, `KB § PATTERNS/common/lossless-doc-refactor.md`.
