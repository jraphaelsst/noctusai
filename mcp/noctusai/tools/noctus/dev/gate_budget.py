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
    # scoped CONTRACT_OF consumer files only (contract_of.py), a few seconds-scale tests
    "pytest:social-wiring:contract": 120,
    "e2e:social-wiring": 480,
    "vite_build:social-wiring": 240,
    # seed roots: seed/lib/backend ~180 s observed.
    "pytest:seed/lib/backend": 360,
    "pytest:seed/": 300,
    "vitest:seed/": 240,
    # toolkit: full suite is the long pole; scoped is test files the diff touched.
    "mcp_toolkit_tests": 300,
    "mcp_toolkit_tests:scoped": 240,
    # non-suite gates gate_sweep can emit (declared, so none rides the default)
    "keeper_meta": 180,
    "keeper_delta": 120,
    "migration_replay": 300,
    "kb_sync_verify": 120,
    "claude_md_router": 60,
    # generic product legs
    "pytest:": 300,
    "e2e:": 300,
    "vite_build:": 240,
}

# Fallback for a gate name with NO declared row. Never silent: it is reported
# as a `budget_defaulted` warning on the integrate result, and a test asserts
# every gate name gate_sweep can emit has a declared row.
DEFAULT_BUDGET_S = 120

# Upper bound on the whole merged-tip phase (parallel gates + any queued behind
# max_workers). Not a per-gate budget; just a runaway ceiling.
DEFAULT_OVERALL_CEILING_S = 900


def declared_gate_budget(gate: str, overrides: dict[str, int] | None = None) -> int | None:
    """Declared budget (overrides, then exact row, then longest prefix) or None."""
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
    return None


def resolve_gate_budget(gate: str, overrides: dict[str, int] | None = None) -> int:
    """Budget in seconds for `gate`; DEFAULT_BUDGET_S only when undeclared."""
    declared = declared_gate_budget(gate, overrides)
    return DEFAULT_BUDGET_S if declared is None else declared


def budget_defaulted_warnings(gate_names: list[str]) -> list[dict[str, object]]:
    """One `budget_defaulted` warning per gate that had no declared budget."""
    return [{"warning": "budget_defaulted", "gate": g, "budget_s": DEFAULT_BUDGET_S,
             "fix": "add a row to gate_budget.GATE_BUDGETS_S"}
            for g in gate_names if declared_gate_budget(g) is None]


def is_timeout_summary(summary: str | None) -> bool:
    """True iff a gate's summary says it produced no verdict because time ran
    out (its own subprocess timeout, or the overall ceiling before it started)."""
    s = (summary or "").lower()
    return s.startswith("timeout after") or "time-box exceeded" in s
