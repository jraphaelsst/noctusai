"""Tests for ``noctus.dev.verify_db_guards`` — executable proof that a
declared database guard actually REFUSES what it claims to refuse.

All tests are fully hermetic — a scripted ``_CannedExecutor`` (no real
Supabase calls), matching the ``SqlExecutor`` Protocol+Fake+Real DI seam
``noctus.dev.migrate_product`` establishes. No monkey-patching of our own
code (per ``KB § PATTERNS/compliance/testing.md``).

The runner's classification is ENTIRELY driven by the sentinel text a
probe's SQL would raise INSIDE Postgres (``NOC_PROBE:<outcome>: ...``) —
so these tests exercise the runner by scripting exactly that text back
from the executor, the same way a real Management-API HTTP error would
surface it. This is what makes the negative control meaningful: it does
not require a real database at all, only a faithful stand-in for what
Postgres would have said.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.verify_db_guards import (  # noqa: E402
    DEFAULT_REGISTRY,
    REGISTERED_GUARD_NAMES,
    GuardProbe,
    run_probe,
    verify_db_guards,
    wrap_rollback_only,
)


class _CannedExecutor:
    """Returns a FIXED canned result for every ``execute()`` call,
    regardless of the SQL text — sufficient here because a probe's
    outcome is entirely determined by what Postgres WOULD have raised,
    which these tests script directly rather than re-deriving from SQL
    text."""

    def __init__(self, *, ok: bool, error: str | None = None, rows: list[dict] | None = None):
        self.ok = ok
        self.error = error
        self.rows = rows if rows is not None else []
        self.executed: list[str] = []

    def execute(self, sql: str) -> dict:
        self.executed.append(sql)
        return {"ok": self.ok, "rows": self.rows, "error": self.error}


_ANY_PROBE = GuardProbe(
    id="fixture.probe",
    product="fixture-product",
    schema="fixture_schema",
    guard_name="fixture_guard",
    kind="write_refusal",
    migrations=("000_fixture.sql",),
    rationale="a fixture probe for these tests",
    sql="DO $noc_probe$\nBEGIN\n  RAISE EXCEPTION 'NOC_PROBE:refused: fixture';\nEND;\n$noc_probe$;",
)


# ---------------------------------------------------------------------------
# wrap_rollback_only — the structural seam
# ---------------------------------------------------------------------------


class TestWrapRollbackOnly:
    def test_sandwiches_begin_and_rollback(self):
        wrapped = wrap_rollback_only(_ANY_PROBE.sql)
        lines = wrapped.strip().splitlines()
        assert lines[0] == "BEGIN;"
        assert lines[-1] == "ROLLBACK;"

    def test_never_emits_a_bare_commit(self):
        """No probe run through this wrapper can ever contain COMMIT —
        this is the module's own emitter, and it literally does not have
        the string 'COMMIT' anywhere in its vocabulary."""
        wrapped = wrap_rollback_only(_ANY_PROBE.sql)
        assert "COMMIT" not in wrapped.upper()

    def test_refuses_empty_sql(self):
        import pytest

        with pytest.raises(ValueError):
            wrap_rollback_only("")

    def test_refuses_a_probe_that_is_not_exactly_one_do_block(self):
        """A probe body that tries to smuggle a second top-level statement
        alongside the DO block (e.g. its own explicit COMMIT) is refused
        BEFORE it ever reaches the database — the static half of the
        rollback-only guarantee."""
        import pytest

        sneaky = _ANY_PROBE.sql + "\nCOMMIT;"
        with pytest.raises(ValueError):
            wrap_rollback_only(sneaky)

    def test_refuses_sql_missing_the_probe_tag(self):
        import pytest

        with pytest.raises(ValueError):
            wrap_rollback_only("SELECT 1;")

    def test_every_registry_probe_wraps_cleanly(self):
        """Every probe actually shipped in DEFAULT_REGISTRY is built via
        the shared `_do_block` constructor and wraps without error — this
        would fail loudly for any registry entry hand-assembled outside
        that seam."""
        for probe in DEFAULT_REGISTRY:
            wrapped = wrap_rollback_only(probe.sql)
            assert wrapped.startswith("BEGIN;\n")
            assert wrapped.rstrip().endswith("ROLLBACK;")
            assert "COMMIT" not in wrapped.upper()


# ---------------------------------------------------------------------------
# run_probe — classification from the sentinel channel
# ---------------------------------------------------------------------------


class TestRunProbeClassification:
    def test_refused_is_a_pass(self):
        ex = _CannedExecutor(ok=False, error="ERROR: NOC_PROBE:refused: guard fired as expected")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "pass"
        assert result["outcome"] == "refused"
        assert result["severity"] is None

    def test_clean_state_assertion_is_a_pass(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:clean: 0 public buckets")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "pass"
        assert result["outcome"] == "clean"

    def test_permitted_is_a_high_severity_finding(self):
        """THE core case: the guard did NOT fire. This must never read as
        a pass."""
        ex = _CannedExecutor(ok=False, error="ERROR: NOC_PROBE:permitted: UPDATE succeeded, guard did not fire")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "finding"
        assert result["outcome"] == "permitted"
        assert result["severity"] == "high"

    def test_violation_state_assertion_is_a_critical_finding(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:violation: 2 public bucket(s) found")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "finding"
        assert result["outcome"] == "violation"
        assert result["severity"] == "critical"

    def test_no_fixture_is_a_failure_never_a_skip(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:no_fixture: no row matching predicate")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"
        assert result["outcome"] == "no_fixture"

    def test_ambiguous_is_a_failure(self):
        """The wrong exception fired (not the guard under test) — this
        must not be misread as a refusal."""
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:ambiguous: unrelated FK violation")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"
        assert result["outcome"] == "ambiguous"

    def test_unclassifiable_executor_error_is_a_failure(self):
        """A connectivity/HTTP error with no NOC_PROBE sentinel at all —
        the probe never even ran. Fail-closed, never a silent pass."""
        ex = _CannedExecutor(ok=False, error="HTTP 503 Service Unavailable")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"
        assert result["outcome"] is None

    def test_ok_true_with_no_sentinel_is_a_failure(self):
        """Every probe body raises on every branch (see module docstring)
        — an `ok=True` response means our own classification logic never
        ran. Silence must never be treated as a pass."""
        ex = _CannedExecutor(ok=True, rows=[])
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"

    def test_malformed_probe_sql_is_refused_before_execution(self):
        bad_probe = GuardProbe(
            id="bad.probe",
            product="fixture-product",
            schema="fixture_schema",
            guard_name="bad_guard",
            kind="write_refusal",
            migrations=(),
            rationale="malformed on purpose",
            sql="SELECT 1;",  # not a DO $noc_probe$ block
        )
        ex = _CannedExecutor(ok=True)
        result = run_probe(bad_probe, ex)
        assert result["status"] == "failure"
        assert ex.executed == []  # never even reached the executor


# ---------------------------------------------------------------------------
# 🔴 Negative control — the classifier must FAIL a stubbed-to-permit guard.
# ---------------------------------------------------------------------------


class TestNegativeControl:
    def test_a_guard_stubbed_to_permit_is_never_reported_as_pass(self):
        """The meta-test: if the underlying guard logic were broken and
        silently permitted the forbidden write, this MUST NOT come back
        as status=pass. A probe/runner pair that can't fail here is the
        exact bug this tool exists to catch."""
        stubbed_permit = _CannedExecutor(
            ok=False,
            error=(
                "ERROR: NOC_PROBE:permitted: UPDATE "
                "social_wiring.matricula_extracoes.ruido for id=<uuid> "
                "succeeded — the write-once guard did not fire"
            ),
        )
        result = run_probe(DEFAULT_REGISTRY[0], stubbed_permit)
        assert result["status"] != "pass"
        assert result["status"] == "finding"
        assert result["severity"] == "high"


# ---------------------------------------------------------------------------
# The rollback property — nothing persists regardless of outcome.
# ---------------------------------------------------------------------------


class TestRollbackProperty:
    def test_every_probe_call_is_exactly_one_execute_and_always_carries_rollback(self):
        """Whatever the outcome, run_probe never issues more than the ONE
        wrapped statement per probe — the same statement that always ends
        in ROLLBACK; — so there is no second, unguarded call where a
        commit could sneak in."""
        for outcome_error in (
            "NOC_PROBE:refused: x",
            "NOC_PROBE:permitted: x",
            "NOC_PROBE:no_fixture: x",
        ):
            ex = _CannedExecutor(ok=False, error=outcome_error)
            run_probe(_ANY_PROBE, ex)
            assert len(ex.executed) == 1
            assert ex.executed[0].strip().startswith("BEGIN;")
            assert ex.executed[0].strip().endswith("ROLLBACK;")


# ---------------------------------------------------------------------------
# verify_db_guards — top-level aggregation + fail-closed posture
# ---------------------------------------------------------------------------


class TestVerifyDbGuards:
    def test_not_configured_when_no_executor_resolves(self):
        result = verify_db_guards(executor=None, registry=(_ANY_PROBE,))
        # No credentials in this test process (and none should be reached
        # for) — make_sql_executor() returns None without network access.
        assert result["status"] in ("not_configured",)
        assert result["ok"] is False

    def test_empty_registry_is_an_error_not_a_silent_clean(self):
        result = verify_db_guards(executor=_CannedExecutor(ok=False, error="NOC_PROBE:refused: x"), registry=())
        assert result["status"] == "error"

    def test_all_pass_is_clean(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:refused: fixture")
        result = verify_db_guards(executor=ex, registry=(_ANY_PROBE,))
        assert result["status"] == "clean"
        assert result["ok"] is True
        assert result["checked"] == 1
        assert result["findings"] == []
        assert result["failures"] == []

    def test_one_finding_blocks_even_with_others_passing(self):
        class _SequencedExecutor:
            def __init__(self, responses):
                self._responses = list(responses)
                self.executed = []

            def execute(self, sql):
                self.executed.append(sql)
                return self._responses.pop(0)

        ex = _SequencedExecutor(
            [
                {"ok": False, "rows": None, "error": "NOC_PROBE:refused: x"},
                {"ok": False, "rows": None, "error": "NOC_PROBE:permitted: x"},
            ]
        )
        second_probe = GuardProbe(
            id="fixture.probe.2",
            product="fixture-product",
            schema="fixture_schema",
            guard_name="fixture_guard_2",
            kind="write_refusal",
            migrations=(),
            rationale="a second fixture probe",
            sql=_ANY_PROBE.sql,
        )
        result = verify_db_guards(executor=ex, registry=(_ANY_PROBE, second_probe))
        assert result["status"] == "violations_found"
        assert result["ok"] is False
        assert len(result["findings"]) == 1
        assert result["findings"][0]["guard_name"] == "fixture_guard_2"

    def test_a_failure_with_no_findings_is_unverified_not_clean(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:no_fixture: nothing to test against")
        result = verify_db_guards(executor=ex, registry=(_ANY_PROBE,))
        assert result["status"] == "unverified"
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Registry sanity — every seeded probe is well-formed.
# ---------------------------------------------------------------------------


class TestRegistrySanity:
    def test_registry_is_non_empty(self):
        assert len(DEFAULT_REGISTRY) >= 10

    def test_every_probe_has_a_registered_guard_name(self):
        for probe in DEFAULT_REGISTRY:
            assert probe.guard_name in REGISTERED_GUARD_NAMES

    def test_probe_ids_are_unique(self):
        ids = [p.id for p in DEFAULT_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_every_probe_sql_contains_a_no_fixture_or_needs_no_fixture(self):
        """Every write_refusal / (fixture-dependent) probe declares an
        explicit no_fixture escape hatch; the platform-wide state
        assertion needs none (nothing is fixture-dependent about reading
        storage.buckets)."""
        for probe in DEFAULT_REGISTRY:
            if probe.kind == "state_assertion":
                continue
            assert "no_fixture" in probe.sql

    def test_every_probe_ends_in_a_sentinel_raising_branch_for_permitted(self):
        for probe in DEFAULT_REGISTRY:
            assert "NOC_PROBE:permitted" in probe.sql or "NOC_PROBE:violation" in probe.sql
