# Gate↔methodology sync — every gate ships with its compliance-by-construction mechanism

**The rule.** When you add a **gate** (a keeper that hard-blocks on a violation of a platform standard/rule), you MUST ship — in the **same change** — the **code-level mechanism that makes compliance automatic / by-construction**, so the gate rarely fires in normal flow. The gate names the standard; the mechanism *executes* the standard. **Never** ship a gate whose only "compliance path" is a human/agent remembering to do the right thing, and **never** satisfy a gate by working around it (monkeypatching the guard, `--no-verify`, loosening the assertion, deleting the row). Codified 2026-06-02 after the pattern recurred N≥3 times.

**Why.** A gate alone converts a silent drift into a *loud, recurring* drift — every agent that forgets the rule hits the wall, fixes it manually, and the next agent hits it again. That's strictly better than silent drift, but it's not the goal. The goal is **drift that cannot happen**: the standard is encoded in the code path that produces the artifact, so the normal way of doing the thing *is* the compliant way. The gate then becomes a **backstop** for out-of-band edits / legacy rows / foreign contexts — not the primary enforcement. Gate + mechanism are two halves of one contract; shipping the gate without the mechanism is an incomplete commit (`KB § 03-SEED-ARCHITECTURE.md` "no incomplete commits").

This is the same instinct as **fix-on-contact** ([[drift-fix-on-contact]]) and **safety-nets-capture-failures→methodology-evolves** (`KB § 01-PHILOSOPHY.md`), applied to the gate-authoring moment: the net firing IS the methodology working, but the *design target* is a system where the net almost never has to fire because the code already complies.

## The two halves (ship together, same commit)

| Half | What it is | Property |
|---|---|---|
| **Gate** (keeper) | A `compliance.py` detector (high/critical) that hard-blocks (pre-commit / pre-push / CI) when the standard is violated — scanning ALL relevant artifacts, incl. historical/terminal rows where the invariant is "always true". | Catches drift: out-of-band edits, legacy data, a context the mechanism didn't run in. |
| **Compliance mechanism** | The code path that **produces** the artifact does the compliant thing **automatically** (default-fills, derives, normalizes, writes-both, validates-then-refuses). The caller cannot easily produce a violating artifact. | Makes the normal path compliant by construction → the gate rarely fires. |

**No-silent-null corollary.** When the mechanism can't auto-derive a required value, it **refuses loudly** (returns an error / raises) rather than writing a placeholder/null — a null would just trip the gate later, one level removed (`KB § 01-PHILOSOPHY.md` "no silent errors").

## Worked examples (the N≥3 that triggered codification)

- **Branch-tree mirror** — gate `check_branch_tree_mirror` hard-blocks if ledger ≠ mirror; mechanism `branch_pointer._write_row` writes BOTH files on every append/update. An agent can't populate one without the other. (`KB § PATTERNS/architect/branch-tree-tracking.md` §2)
- **Branch-tree session** (2026-06-02) — gate: the same keeper flags any null/empty `session` across ALL rows; mechanism: `branch_pointer.append/update` auto-fill `session` from `CLAUDE_CODE_SESSION_ID` (→ newest-transcript fallback → refuse). A pointer can no longer be written session-null.
- **Detector-has-regression-test** — gate `check_detector_has_regression_test` flags any keeper lacking a test; mechanism: the authoring procedure ships the `Test<Detector>` class with the detector (and `scaffold_keeper` emits the test stub).
- **Cache freshness** — gate `check_*_cache_freshness`; mechanism: structural caches self-heal on contact (`settle_structural_caches`) + refresh pre-commit, so the gate is a backstop, not the refresh path. ([[cache-auto-freshness]])
- **Seed Fake+Real+factory** — gate flags a half-shipped seed IO module; mechanism: the seed-adapter scaffold ships all three so a consumer can't fork. (`KB § PATTERNS/backend/seed-fake-real-adapter.md`)

## Anti-patterns (forbidden)

- **Gate-only** — ship the keeper, leave compliance to memory/discipline. (The drift recurs forever; agents burn cycles re-fixing.)
- **Workaround the gate** — `--no-verify`, monkeypatch the guard, weaken `==` to `in (...)`, delete the offending row to pass. (`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`)
- **Silent-null compliance** — auto-fill a placeholder/null just to clear the gate. Refuse loudly instead.
- **Mechanism-only** — ship the auto-fill but no gate. (Out-of-band edits + legacy rows + foreign contexts silently re-introduce the violation.)

## How to apply (the authoring checklist)

When a rule/standard is worth enforcing:
1. Write the **gate** (keeper detector, `scaffold_keeper`) — scan ALL artifacts, hard-block, name the exact fix in the message.
2. Write the **mechanism** in the producing code path — auto-fill/derive/normalize/write-both; refuse (no silent-null) when it can't.
3. **Backfill** existing artifacts to comply (the gate gates legacy too).
4. Ship the **regression test** for the gate (the detector-has-test gate requires it).
5. Sync the rule across surfaces the SAME commit (`KB § PATTERNS/common/eight-way-sync.md`): CLAUDE.md §1 one-liner + this/the relevant KB pattern + memory.
6. Prove the loop: gate fires on the pre-fix state → mechanism+backfill → gate passes.

Composes with [[drift-fix-on-contact]] · [[methodology-execution-discipline]] · `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` · `KB § PATTERNS/common/eight-way-sync.md` · `KB § PATTERNS/architect/branch-tree-tracking.md`.
