"""Declared per-gate wall-clock budgets for the integrate-time merged-tip check.

ROOT CAUSE this replaces (2026-10-19): `task_branch.merged_tip_timeout=90`
was ONE shared deadline for the whole gate set, and `_deadline_boxed_run_gate`
handed every gate the *remaining* seconds as its subprocess timeout. The big
suites (pytest:social-wiring ~5 min / 11.9k tests, pytest:seed/lib/backend
~3 min, e2e:social-wiring, sometimes mcp_toolkit_tests) therefore always died
at ~80-90 s with `timeout after Ns`, were classed UNMEASURED, and the branch
integrated on "CI is their verdict" - a red reached dev (eight SW branding
tests). A time-box sized to the *fastest* gate cannot judge the slowest.

Design: a DECLARED table (data-sized from observed runs, not a flat constant)
resolved per gate. Gates run in parallel (`gate_sweep._run_gates`), so the
wall-clock is bounded by the largest budget in the scheduled set, not their
sum. Values are observed duration x ~1.5 headroom, rounded; revise a row
when its suite grows (the floor rows are deliberately above the numbers the
task brief fixed: SW >= 420, seed/lib >= 300, mcp full >= 240).

KB: PATTERNS/common/methodology-execution-discipline.md (merged-tip section).
"""
from __future__ import annotations

# (exact gate name | name prefix ending in ":" or "/") -> seconds.
# Exact names win over prefixes; longest prefix wins among prefixes.
GATE_BUDGETS_S: dict[str, int] = {
    # social-wiring: ~300 s pytest (11.9k tests) on a quiet box, slower under load.
    "pytest:social-wiring": 480,
    "e2e:social-wiring": 480,
    "vite_build:social-wiring": 240,
    # seed roots: seed/lib/backend ~180 s observed.
    "pytest:seed/lib/backend": 360,
    "pytest:seed/": 300,
    # toolkit: full suite is the long pole; scoped is test files the diff touched.
    "mcp_toolkit_tests": 300,
    "mcp_toolkit_tests:scoped": 240,
    # generic product legs
    "pytest:": 300,
    "e2e:": 300,
    "vite_build:": 240,
}

# Anything not matched above (keepers, kb_sync, router checks) is cheap.
DEFAULT_BUDGET_S = 120

# Upper bound on the whole merged-tip phase (parallel gates + any queued behind
# max_workers). Not a per-gate budget; just a runaway ceiling.
DEFAULT_OVERALL_CEILING_S = 900


def resolve_gate_budget(gate: str, overrides: dict[str, int] | None = None) -> int:
    """Budget in seconds for `gate`: caller overrides, then exact table row,
    then the longest matching prefix, then DEFAULT_BUDGET_S."""
    for table in (overrides or {}, GATE_BUDGETS_S):
        if gate in table:
            return int(table[gate])
        best = None
        for key in table:
            if key.endswith((":", "/")) and gate.startswith(key):
                if best is None or len(key) > len(best):
                    best = key
        if best is not None:
            return int(table[best])
    return DEFAULT_BUDGET_S


def is_timeout_summary(summary: str | None) -> bool:
    """True iff a gate's summary says it produced no verdict because time ran
    out (its own subprocess timeout, or the overall ceiling before it started)."""
    s = (summary or "").lower()
    return s.startswith("timeout after") or "time-box exceeded" in s
