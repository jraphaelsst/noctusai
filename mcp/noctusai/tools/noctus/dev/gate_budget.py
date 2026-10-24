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

# ── Single configuration point (2026-10-21) ────────────────────────────────
# Owner directive: gate timeouts on a loaded laptop kept blocking integrate
# (`gate_timeout`) on suites that pass when run directly. Every knob lives
# HERE; all are env-overridable so a slow box needs no code change:
#   NOCTUS_GATE_BUDGET_SCALE      float, default 1.0 - multiplies EVERY budget below
#   NOCTUS_GATE_BUDGETS_JSON      JSON {gate-or-prefix: seconds} - per-gate overrides
#   NOCTUS_GATE_RETRY_FACTOR      float, default 1.5 - a TIMED-OUT gate is retried
#                                 ONCE with budget x this (a FAILED gate never is)
#   NOCTUS_GATE_MAX_BUDGET_S      int, default 1800 - hard per-attempt ceiling
#   NOCTUS_GATE_OVERALL_CEILING_S int, default 3600 - whole merged-tip phase
import json as _json
import os as _os


def _env_float(name: str, default: float) -> float:
    raw = _os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        val = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name}={raw!r} is not a number") from exc
    if val <= 0:
        raise ValueError(f"{name}={raw!r} must be > 0")
    return val


# Values = ~3x the p90 of observed durations (2026-10-21 integrate outputs:
# pytest:social-wiring 314-373 s, seed/lib/backend 198-233 s, agents 79-123 s,
# vitest:seed/lib 60 s, e2e:social-wiring 27-52 s, mcp_toolkit_tests:scoped 6 s
# quiet but >240 s TIMED OUT on a loaded laptop - collection alone took ~5 min),
# never below the previous value. Revise a row when its suite grows.
# (exact gate name | name prefix ending in ":" or "/") -> seconds.
# Exact names win over prefixes; longest prefix wins among prefixes.
GATE_BUDGETS_S: dict[str, int] = {
    # social-wiring pytest: p90 ~370 s -> 3x ~1100 s (was 480).
    "pytest:social-wiring": 1100,
    # scoped CONTRACT_OF consumer files only (contract_of.py)
    "pytest:social-wiring:contract": 300,
    # e2e: p90 ~52 s but page.goto load-timeouts under load -> 600 (was 480).
    "e2e:social-wiring": 600,
    "vite_build:social-wiring": 300,
    # seed roots: seed/lib/backend p90 ~233 s -> 700 (was 360).
    "pytest:seed/lib/backend": 700,
    "pytest:seed/": 450,
    "vitest:seed/": 300,
    # toolkit: observed timing out at 240 under load (was 300 / 240).
    "mcp_toolkit_tests": 900,
    "mcp_toolkit_tests:scoped": 720,
    # non-suite gates gate_sweep can emit (declared, so none rides the default)
    "keeper_meta": 400,
    "keeper_delta": 300,
    "migration_replay": 600,
    "kb_sync_verify": 300,
    "claude_md_router": 120,
    # generic product legs: pytest:agents p90 ~123 s -> 3x ~370, rounded up.
    "pytest:": 600,
    "e2e:": 600,
    "vite_build:": 300,
    # product frontend unit suites (vitest:<slug>); seed roots keep "vitest:seed/".
    "vitest:": 600,
}

# Fallback for a gate name with NO declared row. Never silent: it is reported
# as a `budget_defaulted` warning on the integrate result, and a test asserts
# every gate name gate_sweep can emit has a declared row.
DEFAULT_BUDGET_S = 300

# Retry-once-on-TIMEOUT (never on failure): second attempt gets budget x factor.
RETRY_FACTOR = _env_float("NOCTUS_GATE_RETRY_FACTOR", 1.5)
# Hard per-attempt ceiling after scale/retry.
MAX_GATE_BUDGET_S = int(_env_float("NOCTUS_GATE_MAX_BUDGET_S", 1800))

# Upper bound on the whole merged-tip phase (parallel gates + any queued behind
# max_workers, incl. retries). Worst single gate = 1100 + 1650 s, so 3600 keeps
# the wall-clock bounded yet lets a double-attempt of the longest gate finish.
DEFAULT_OVERALL_CEILING_S = int(_env_float("NOCTUS_GATE_OVERALL_CEILING_S", 3600))


def env_overrides() -> dict[str, int]:
    """Per-gate overrides from NOCTUS_GATE_BUDGETS_JSON ({} when unset)."""
    raw = _os.environ.get("NOCTUS_GATE_BUDGETS_JSON")
    if not raw or not raw.strip():
        return {}
    data = _json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("NOCTUS_GATE_BUDGETS_JSON must be a JSON object")
    return {str(k): int(v) for k, v in data.items()}


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
    """Budget in seconds for `gate` (explicit `overrides`, then env JSON, then the
    table; DEFAULT_BUDGET_S only when undeclared), x NOCTUS_GATE_BUDGET_SCALE,
    capped at MAX_GATE_BUDGET_S."""
    declared = declared_gate_budget(gate, {**env_overrides(), **(overrides or {})})
    base = DEFAULT_BUDGET_S if declared is None else declared
    scaled = int(round(base * _env_float("NOCTUS_GATE_BUDGET_SCALE", 1.0)))
    return max(1, min(scaled, MAX_GATE_BUDGET_S))


def retry_budget(first_budget_s: int) -> int:
    """Extended limit for the single retry of a TIMED-OUT gate."""
    return max(1, min(int(round(first_budget_s * RETRY_FACTOR)), MAX_GATE_BUDGET_S))


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
