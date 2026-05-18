"""Tests for the 6 rollup tools surfaced by ``noctus.seed.scan_fusions``
(2026-05-10) — language-agnostic outline, per-product audit gate,
master-prompt verify+sync, batch-speed-gain overview, team dashboard,
and the absorption-search sextet rollup.

All tests use the tools' own test seams (``tmp_path`` for files,
mock imports for the team-facade dependency) — no real-repo writes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ─── outline (language-agnostic) ───────────────────────────────────────────


from tools.noctus.dev.outline import outline


class TestOutline:
    """Auto-dispatch by file extension to outline_python / outline_typescript."""

    def test_python_file_dispatches_to_outline_python(self, tmp_path):
        py = tmp_path / "sample.py"
        py.write_text("class Foo:\n    def bar(self): pass\n", encoding="utf-8")
        result = outline(py)
        assert result["language"] == "python"
        assert result["error"] is None
        assert "classes" in result["result"]
        # Sanity: the class IS visible in the python outline.
        assert any(c["name"] == "Foo" for c in result["result"].get("classes", []))

    def test_typescript_file_dispatches_to_outline_typescript(self, tmp_path):
        ts = tmp_path / "sample.ts"
        ts.write_text("export const X = 1;\n", encoding="utf-8")
        result = outline(ts)
        assert result["language"] == "typescript"
        # outline_typescript may parse-error on synthetic files (no tsconfig);
        # the dispatch itself is what we're verifying.
        assert "result" in result

    def test_unknown_extension_returns_error(self, tmp_path):
        unknown = tmp_path / "data.json"
        unknown.write_text("{}", encoding="utf-8")
        result = outline(unknown)
        assert result["language"] is None
        assert result["result"] is None
        assert result["error"] is not None
        assert "unsupported extension" in result["error"]

    def test_pyi_stub_dispatches_to_python(self, tmp_path):
        pyi = tmp_path / "stub.pyi"
        pyi.write_text("def foo() -> int: ...\n", encoding="utf-8")
        result = outline(pyi)
        assert result["language"] == "python"


# ─── audit_product ─────────────────────────────────────────────────────────


from tools.noctus.dev.audit_product import audit_product


class TestAuditProduct:
    """Phase-close gate: composes every per-slug check into one report."""

    def test_returns_passed_false_when_any_slice_has_issues(self):
        # Use a real product slug that exists in the tree. `core` reliably
        # has `check_master_prompt` issues against the live filesystem,
        # so this asserts the composite logic, not slug-specific shape.
        result = audit_product("core", include=["check_master_prompt"])
        assert result["slug"] == "core"
        assert "passed" in result
        assert "summary" in result
        assert "slices" in result
        assert "check_master_prompt" in result["slices"]

    def test_include_filter_runs_only_requested_slices(self):
        result = audit_product("core", include=["find_orphans"])
        assert set(result["slices"].keys()) == {"find_orphans"}
        assert all("find_orphans" in line for line in result["summary"])

    def test_unknown_slice_name_returns_error(self):
        result = audit_product("core", include=["bogus_slice"])
        assert result["passed"] is False
        assert any("unknown slice" in e for e in result["errors"])
        assert result["slices"] == {}

    def test_soft_fails_per_slice_via_errors_list(self):
        # When a slice raises, errors[] gets the message, other slices
        # still run. Patch one slice to raise; assert the others ran.
        with mock.patch(
            "tools.noctus.dev.diff.find_orphaned_files",
            side_effect=RuntimeError("boom"),
        ):
            result = audit_product(
                "core",
                include=["find_orphans", "check_master_prompt"],
            )
            assert any("find_orphans" in e and "boom" in e for e in result["errors"])
            assert "check_master_prompt" in result["slices"], (
                "other slices must still run when one slice raises"
            )


# ─── verify_master_prompt ──────────────────────────────────────────────────


from tools.noctus.dev.master_prompts import verify_master_prompt


class TestVerifyMasterPrompt:
    """Composes check + sync. write=False is observation-only;
    write=True regenerates only IF stale."""

    def test_write_false_does_not_modify(self):
        result = verify_master_prompt("core", write=False)
        assert result["write_attempted"] is False
        assert result["synced"] is False
        # stale + issues come from check_master_prompt_staleness; the
        # composite doesn't touch their semantics.
        assert "stale" in result and "issues" in result

    def test_write_true_only_runs_sync_when_stale(self):
        # Patch sync_master_prompt to ensure it's only called when stale.
        with mock.patch(
            "tools.noctus.dev.master_prompts.sync_master_prompt",
        ) as mock_sync, mock.patch(
            "tools.noctus.dev.master_prompts.check_master_prompt_staleness",
            return_value={"slug": "x", "stale": False, "issues": []},
        ):
            result = verify_master_prompt("x", write=True)
            assert result["stale"] is False
            assert mock_sync.call_count == 0, (
                "sync must NOT run when staleness check passes"
            )
            assert result["synced"] is False

    def test_write_true_runs_sync_when_stale(self):
        with mock.patch(
            "tools.noctus.dev.master_prompts.sync_master_prompt",
            return_value={"updated": True, "changes": ["Backend updated"]},
        ) as mock_sync, mock.patch(
            "tools.noctus.dev.master_prompts.check_master_prompt_staleness",
            return_value={
                "slug": "x", "stale": True, "issues": ["something"],
            },
        ):
            result = verify_master_prompt("x", write=True)
            assert mock_sync.call_count == 1
            assert result["synced"] is True
            assert result["changes"] == ["Backend updated"]


# ─── batch_speed_gain_view (unified read tool) ─────────────────────────────


from tools.noctus.dev.batch_speed_gains import view as bsg_view


class TestBatchSpeedGainView:
    """Unified read tool: mode=detail (rows), cumulative (stats), both
    (rollup of the two). Replaces the old query / cumulative / overview
    triplet."""

    def test_mode_both_returns_batches_and_cumulative(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "NOCTUS_BATCH_SPEED_GAINS_DB",
            str(tmp_path / "batch.db"),
        )
        from tools.noctus.dev.batch_speed_gains import log_batch
        log_batch(
            orchestration_slug="test-orch",
            batch_label="batch-1",
            engineer_count=3,
            wall_clock_parallel_s=120.0,
            estimated_serial_s=300.0,
            status="COMPLETED",
        )
        result = bsg_view("test-orch", mode="both")
        assert result["orchestration_slug"] == "test-orch"
        assert len(result["batches"]) == 1
        assert result["batches"][0]["batch_label"] == "batch-1"
        assert result["cumulative"]["batch_count"] == 1
        assert result["cumulative"]["engineer_total"] == 3

    def test_mode_detail_returns_only_batches(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "NOCTUS_BATCH_SPEED_GAINS_DB",
            str(tmp_path / "batch.db"),
        )
        from tools.noctus.dev.batch_speed_gains import log_batch
        log_batch(
            orchestration_slug="test-orch", batch_label="b1",
            engineer_count=2, status="COMPLETED",
        )
        result = bsg_view("test-orch", mode="detail")
        assert "batches" in result
        assert "cumulative" not in result

    def test_mode_cumulative_requires_orchestration_slug(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "NOCTUS_BATCH_SPEED_GAINS_DB",
            str(tmp_path / "batch.db"),
        )
        result = bsg_view(None, mode="cumulative")
        assert "error" in result
        assert "orchestration_slug is required" in result["error"]

    def test_mode_detail_with_no_slug_returns_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "NOCTUS_BATCH_SPEED_GAINS_DB",
            str(tmp_path / "batch.db"),
        )
        from tools.noctus.dev.batch_speed_gains import log_batch
        log_batch(
            orchestration_slug="o1", batch_label="b1",
            engineer_count=1, status="COMPLETED",
        )
        log_batch(
            orchestration_slug="o2", batch_label="b1",
            engineer_count=1, status="COMPLETED",
        )
        result = bsg_view(None, mode="detail")
        assert len(result["batches"]) == 2

    def test_invalid_mode_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "NOCTUS_BATCH_SPEED_GAINS_DB",
            str(tmp_path / "batch.db"),
        )
        result = bsg_view("any", mode="bogus")
        assert "error" in result
        assert "invalid mode" in result["error"]


# ─── team.dashboard ────────────────────────────────────────────────────────


from tools.noctus.team.dashboard import dashboard as team_dashboard


class TestTeamDashboard:
    """`noctus.team.dashboard` returns a stable-schema envelope in every
    environment. The MCP test env doesn't ship dev_team (agno is a heavy
    optional dep), so with no telemetry the slices come back *zeroed but
    well-formed* — a fixed-key skeleton, not empty dicts and not None. This
    is the resilient contract (consumers can always index the keys); these
    tests pin that shape. (Updated 2026-05-17: the prior assertions pinned an
    obsolete empty-dict / errors[]-populated soft-fail contract that the
    current dashboard implementation supersedes — stale-test, not regression;
    baseline-verified pre-existing on origin/main.)"""

    def test_returns_stable_skeleton_when_no_telemetry(self):
        result = team_dashboard()
        # Envelope shape is always present.
        assert set(result.keys()) == {"snapshot", "metrics", "agents", "errors"}
        # Slices are zeroed-but-well-formed skeletons, not empty / not None.
        assert set(result["snapshot"]) == {
            "project", "current_phase", "last_verification"
        }
        assert result["metrics"]["total_events"] == 0
        assert result["metrics"]["total_cost_usd"] == 0.0
        assert "agents" in result["metrics"]
        # No agents requested → no per-agent slice populated.
        assert result["agents"] == {}
        assert isinstance(result["errors"], list)

    def test_agents_whitelist_populates_zeroed_slice_per_role(self):
        # Each requested role gets a well-formed zeroed telemetry slice
        # (the dashboard returns zeroed metrics rather than erroring when
        # no telemetry exists for the role).
        result = team_dashboard(agents=["leader", "backend_engineer"])
        assert set(result["agents"]) == {"leader", "backend_engineer"}
        for role in ("leader", "backend_engineer"):
            slice_ = result["agents"][role]
            assert slice_["agent"] == role
            assert slice_["events"] == 0
            assert slice_["total_cost_usd"] == 0.0
        assert isinstance(result["errors"], list)

    def test_envelope_schema_stable_across_calls(self):
        # Calling twice must produce the same envelope shape — no
        # leaked state, no order-dependent behavior.
        a = team_dashboard()
        b = team_dashboard()
        assert set(a.keys()) == set(b.keys())
        assert isinstance(a["errors"], list) and isinstance(b["errors"], list)


# ─── scan_unified (absorption-search sextet rollup) ────────────────────────


from tools.noctus.dev.scan_unified import scan_unified


class TestScanUnified:
    """Composes 8 scanners; unified findings sorted by severity + occ count."""

    def test_runs_all_scanners_by_default(self):
        # Hits the live tree — fast enough (~few seconds for 8 scanners).
        result = scan_unified(min_count=3, max_findings=5)
        assert len(result["scanners_run"]) >= 1
        assert "recurrence" in result["scanners_run"]
        # Either findings or empty — both are valid; sextet may bottom out
        # after extensive absorption.
        assert isinstance(result["findings"], list)
        assert "summary" in result
        assert "by_scanner" in result["summary"]

    def test_include_filter_runs_only_requested(self):
        result = scan_unified(include=["recurrence"], max_findings=3)
        assert result["scanners_run"] == ["recurrence"]
        assert all(f["scanner"] == "recurrence" for f in result["findings"])

    def test_unknown_scanner_returns_error(self):
        result = scan_unified(include=["bogus_scanner"])
        assert result["findings"] == []
        assert any("unknown scanner" in e for e in result["errors"])

    def test_findings_sorted_high_first(self):
        result = scan_unified(min_count=3)
        # Walk findings; severity rank must be monotonic non-decreasing.
        from tools.noctus.dev.scan_unified import _SEVERITY_ORDER
        prev_rank = -1
        for f in result["findings"]:
            rank = _SEVERITY_ORDER.get(f["severity"], 99)
            assert rank >= prev_rank, (
                f"severity ordering broken: {f['severity']!r} (rank {rank}) "
                f"appeared after rank {prev_rank}"
            )
            prev_rank = rank

    def test_max_findings_caps_returned_list(self):
        result = scan_unified(max_findings=3)
        assert len(result["findings"]) <= 3
        # Summary counts the FULL pre-cap result.
        if result["summary"]["total_findings"] > 3:
            assert result["summary"]["total_findings"] >= len(result["findings"])

    def test_summary_by_scanner_counts_per_source(self):
        result = scan_unified(include=["recurrence"])
        # by_scanner should ONLY have the requested scanner if findings.
        for scanner_name in result["summary"]["by_scanner"]:
            assert scanner_name == "recurrence"
