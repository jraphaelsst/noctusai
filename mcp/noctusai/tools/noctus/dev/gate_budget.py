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
import re as _re


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
    # social-wiring pytest: full suite measured 684-1025 s quiet and 1285 s / 2208 s under load
    # (~/.noctus/hw-runs, 2026-11-06..14) -> 1800 (was 1100, which timed it out 51x as a scoped check).
    "pytest:social-wiring": 1800,
    # scoped CONTRACT_OF consumer files only (contract_of.py)
    "pytest:social-wiring:contract": 300,
    # e2e: p90 ~52 s but page.goto load-timeouts under load -> 600 (was 480).
    "e2e:social-wiring": 600,
    "vite_build:social-wiring": 300,
    # seed roots: seed/lib/backend 277-419 s quiet, 938 s loaded (gate-verdicts) -> 1200 (was 700; 42x timeouts).
    "pytest:seed/lib/backend": 1200,
    "pytest:seed/": 450,
    "vitest:seed/": 300,
    # toolkit: observed timing out at 240 under load (was 300 / 240).
    "mcp_toolkit_tests": 900,
    # no-file-list fallback only (a caller that knows the files uses `derived_suite_budget`): measured 232-file selection 1704 s x1.5
    "mcp_toolkit_tests:scoped": 2600,
    # wiring tests by name when the full toolkit split is CI-only (item 5): freshness + CLI + the module's own tests
    "mcp_toolkit_wiring": 720,
    # non-suite gates gate_sweep can emit (declared, so none rides the default)
    "keeper_meta": 400,
    "keeper_delta": 300,
    "migration_replay": 600,
    "kb_sync_verify": 300,
    "claude_md_router": 120,
    # release_steward scoped_green (`export_ci_parity_check`): one budget PER STAGE, each with the one x1.5 retry, instead
    # of one 1500 s cap on a stage (2026-11-11: a loaded box timed the real-tree keeper pytest out three times).
    "ci_parity:export": 300,
    "ci_parity:pytest": 1100,
    "ci_parity:livetree": 1100,
    "ci_parity:keeper:": 600,
    "ci_parity:prime:": 300,
    # item 5's directly-touched suites (`local_suites` + `migration_guard_suite`). `suite:product:<x>` / `suite:seed:<x>`
    # resolve to the declared `pytest:<x>` row (see `_suite_alias`); this prefix row only covers `db-guards:*`.
    "ci_parity:suite:": 600,
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
MAX_GATE_BUDGET_S = int(_env_float("NOCTUS_GATE_MAX_BUDGET_S", 3000))

# Upper bound on the whole merged-tip phase (parallel gates + any queued behind
# max_workers, incl. retries). Worst single gate = 1800 + 2700 s, so 5400 keeps
# the wall-clock bounded yet lets a double-attempt of the longest gate finish.
DEFAULT_OVERALL_CEILING_S = int(_env_float("NOCTUS_GATE_OVERALL_CEILING_S", 5400))


def env_overrides() -> dict[str, int]:
    """Per-gate overrides from NOCTUS_GATE_BUDGETS_JSON ({} when unset)."""
    raw = _os.environ.get("NOCTUS_GATE_BUDGETS_JSON")
    if not raw or not raw.strip():
        return {}
    data = _json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("NOCTUS_GATE_BUDGETS_JSON must be a JSON object")
    return {str(k): int(v) for k, v in data.items()}


def _suite_alias(gate: str) -> str | None:
    """`ci_parity:suite:product:<x>` / `ci_parity:suite:seed:<x>` -> the declared `pytest:<x>` gate name."""
    prefix = "ci_parity:suite:"
    if not gate.startswith(prefix):
        return None
    label = gate[len(prefix):]
    kind, _, name = label.partition(":")
    if kind in ("product", "seed") and name:
        return f"pytest:{name}"
    # a scoped-check label that IS a declared gate row (`mcp_toolkit_tests:scoped`) follows that row, never the flat
    # `ci_parity:suite:` 600 s prefix (2026-11-15: the 230-file scoped toolkit stage timed out at 600 s then 900 s).
    return label if label in GATE_BUDGETS_S else None


def declared_gate_budget(gate: str, overrides: dict[str, int] | None = None) -> int | None:
    """Declared budget (overrides, then exact row, then longest prefix) or None. A scoped-check suite name
    (`ci_parity:suite:<kind>:<x>`) with no override of its own follows the declared `pytest:<x>` row."""
    alias = _suite_alias(gate)
    if alias is not None and gate not in (overrides or {}):
        return declared_gate_budget(alias, overrides)
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


# ── Per-file derived budgets (2026-11-15) ──────────────────────────────────────────────────────────────────────
# A suite whose size VARIES per run (the scoped toolkit suite = every test file that imports a changed module: 1 to
# 230+ files) cannot be sized by a constant: 720 s was too small for the 230-file selection, 600 s (the generic
# `ci_parity:suite:` row) timed it out twice, and a flat s/file figure is wrong too - one file (test_compliance.py)
# costs 389 s, the median file 1.75 s. The budget is DERIVED per run from the SELECTED FILES' measured cost:
#   FIXED + HEADROOM x sum(cost(file)),  cost = live p90 (ci-stage-timings.ndjson) > SEED_FILE_S > DEFAULT_FILE_S.
#: gates sized this way (`ci_parity:suite:<label>` -> `<label>`).
PER_FILE_GATES = frozenset({"mcp_toolkit_tests:scoped"})
PER_FILE_FIXED_S = 60      # collection + conftest + interpreter start, paid once per pytest invocation
PER_FILE_HEADROOM = 1.5    # the same x1.5 over the observed value every row of GATE_BUDGETS_S carries
#: cost of a file with no seed and no live measurement: the mean of the 206 light files measured below.
DEFAULT_FILE_S = 2.2
#: MEASURED seconds (setup+call+teardown, `pytest --durations=0`) of every toolkit test file that cost >= 10 s, from ONE run
#: of the 232-file scoped selection (4107 tests, 1704 s wall, rc=0; ~/.noctus/hw-runs/scoped-toolkit-durations-20261115T075842Z.log).
#: Sum 1225 s over 26 files; the other 206 files sum 448 s (mean 2.2 s, median 1.75 s). A live measurement replaces a seed.
SEED_FILE_S: dict[str, float] = {
    "test_compliance.py": 389, "test_guardian_pure_push_enqueue.py": 136, "test_eight_way_sync.py": 107,
    "test_access_tiers_keeper.py": 94, "test_gate_alignment.py": 58, "test_migration_replay.py": 44,
    "test_cache_backend.py": 43, "test_agents_camadas_probes_on_replay.py": 42, "test_task_branch.py": 32,
    "test_http_detail_echo_keeper.py": 29, "test_task_branch_cleanup_ownership.py": 25,
    "test_git_hook_file_tampering_detector.py": 19, "test_agents_browser_lockdown_probes_on_replay.py": 19,
    "test_git_hooks_bypass_detector.py": 19, "test_kb_vector_canonical.py": 18, "test_check_guardian_tool_authorship.py": 18,
    "test_lying_loading_state_detector.py": 16, "test_check_motion_import_boundary.py": 15, "test_primary_ff.py": 15,
    "test_check_silent_refusal.py": 14, "test_nosnolimiar_rename_on_replay.py": 14, "test_core_078_probes_on_replay.py": 13,
    "test_sw_240_probes_on_replay.py": 12, "test_sw_249_probes_on_replay.py": 12, "test_doc_staleness.py": 11,
    "test_compliance_hygiene.py": 10,
}
_TEST_FILE_RE = _re.compile(r"(?:^|/)(test_[^/\s:]+\.py)(?:::|$)")
_DURATION_RE = _re.compile(r"^\s*([\d.]+)s (?:call|setup|teardown)\s+(?:\S*/)?(test_[^/\s:]+\.py)::")


def per_file_gate(gate: str) -> str | None:
    """The `PER_FILE_GATES` label `gate` is sized by (`ci_parity:suite:<label>` -> `<label>`), or None."""
    label = gate[len("ci_parity:suite:"):] if gate.startswith("ci_parity:suite:") else gate
    return label if label in PER_FILE_GATES else None


def test_files(argv: list[str]) -> list[str]:
    """Distinct pytest test file BASENAMES named in `argv` (`tests/test_x.py` or `tests/test_x.py::T::t`), in order."""
    out: list[str] = []
    for a in argv:
        m = _TEST_FILE_RE.search(a)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def parse_file_durations(output: str | None, min_s: float = 5.0) -> dict[str, float]:
    """Per-file seconds (setup+call+teardown) from `pytest --durations=0` output; files under `min_s` are dropped (they ride
    DEFAULT_FILE_S)."""
    tot: dict[str, float] = {}
    for line in (output or "").splitlines():
        m = _DURATION_RE.match(line)
        if m:
            tot[m.group(2)] = tot.get(m.group(2), 0.0) + float(m.group(1))
    return {k: round(v, 1) for k, v in tot.items() if v >= min_s}


def measured_file_costs(records: list[dict[str, object]], gate: str, last: int = 20, min_obs: int = 3) -> dict[str, float]:
    """Live per-file p90 seconds from the last `last` COMPLETED stage records of `gate` that carry `file_s`; a file needs
    `min_obs` observations before it replaces its seed."""
    obs: dict[str, list[float]] = {}
    for r in [r for r in records if r.get("gate") == gate and r.get("completed") and isinstance(r.get("file_s"), dict)][-last:]:
        for f, v in r["file_s"].items():  # type: ignore[union-attr]
            obs.setdefault(f, []).append(float(v))
    return {f: sorted(v)[min(len(v) - 1, int(len(v) * 0.9))] for f, v in obs.items() if len(v) >= min_obs}


def estimate_files_s(files: list[str], measured: dict[str, float] | None = None) -> float:
    """Expected seconds for `files`: live p90 > seed > DEFAULT_FILE_S, per file."""
    return sum((measured or {}).get(f, SEED_FILE_S.get(f, DEFAULT_FILE_S)) for f in files)


def derived_suite_budget(gate: str, files: list[str], measured: dict[str, float] | None = None) -> int | None:
    """Wall-clock budget for a per-file-sized suite: FIXED + HEADROOM x estimated seconds of the selected files. None when
    `gate` is not per-file sized or names no file."""
    if per_file_gate(gate) is None or not files:
        return None
    return int(round(PER_FILE_FIXED_S + PER_FILE_HEADROOM * estimate_files_s(files, measured)))


def resolve_gate_budget(gate: str, overrides: dict[str, int] | None = None, *, files: list[str] | None = None,
                        measured: dict[str, float] | None = None) -> int:
    """Budget in seconds for `gate` (explicit `overrides`, then env JSON, then - for a per-file-sized suite with its test
    `files` known - the DERIVED budget, then the table; DEFAULT_BUDGET_S only when undeclared), x NOCTUS_GATE_BUDGET_SCALE,
    capped at MAX_GATE_BUDGET_S."""
    merged = {**env_overrides(), **(overrides or {})}
    declared = declared_gate_budget(gate, merged)
    derived = derived_suite_budget(gate, files or [], measured)
    if derived is not None and gate not in merged and per_file_gate(gate) not in merged:
        declared = derived
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
