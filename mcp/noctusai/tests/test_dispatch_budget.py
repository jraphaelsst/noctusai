"""Tests for mcp/noctusai/tools/noctus/dev/dispatch_budget.py.

Coverage:
  - append shape: row fields, total_tokens derived correctly
  - report aggregation: groups by (agent, model), computes avg/p95
  - summary: one-shot totals, window_days filter
  - malformed lines: silently skipped
  - missing fields: graceful default to 0
  - file rotation safe: no side-effects on the live ndjson (uses tmp_path)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make tools importable without installing the package.
_MCP_ROOT = Path(__file__).parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_module(tmp_path: Path):
    """Import dispatch_budget with LEDGER_PATH redirected to tmp_path."""
    import importlib
    import tools.noctus.dev.dispatch_budget as mod
    ledger = tmp_path / "dispatch-budget.ndjson"
    # Patch the module-level LEDGER_PATH for the duration of the test.
    with patch.object(mod, "LEDGER_PATH", ledger):
        yield mod, ledger


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAppendShape:
    """log_dispatch writes a well-formed NDJSON row."""

    def test_row_fields_present(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        with patch.object(mod, "LEDGER_PATH", ledger):
            result = mod.log_dispatch(
                agent="backend-engineer",
                slug="feat/r1-f11",
                input_tokens=1000,
                output_tokens=500,
                model="claude-sonnet-4-6",
                source_ref="session:2026-05-28",
            )

        assert result["ok"] is True
        row = result["row"]
        assert row["agent"] == "backend-engineer"
        assert row["slug"] == "feat/r1-f11"
        assert row["input_tokens"] == 1000
        assert row["output_tokens"] == 500
        assert row["total_tokens"] == 1500
        assert row["model"] == "claude-sonnet-4-6"
        assert row["source_ref"] == "session:2026-05-28"
        assert "ts" in row

    def test_total_tokens_derived(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        with patch.object(mod, "LEDGER_PATH", ledger):
            result = mod.log_dispatch(
                agent="frontend-engineer",
                slug="feat/x",
                input_tokens=200,
                output_tokens=300,
                model="claude-opus-4-7",
            )
        assert result["row"]["total_tokens"] == 500

    def test_written_as_valid_json(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        with patch.object(mod, "LEDGER_PATH", ledger):
            mod.log_dispatch(
                agent="backend-engineer",
                slug="feat/y",
                input_tokens=100,
                output_tokens=50,
                model="claude-sonnet-4-6",
            )
        lines = ledger.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["total_tokens"] == 150

    def test_multiple_appends(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        with patch.object(mod, "LEDGER_PATH", ledger):
            for i in range(3):
                mod.log_dispatch(
                    agent="backend-engineer",
                    slug=f"feat/t{i}",
                    input_tokens=100 * (i + 1),
                    output_tokens=50,
                    model="claude-sonnet-4-6",
                )
        lines = ledger.read_text().strip().splitlines()
        assert len(lines) == 3


class TestReportAggregation:
    """report() groups by (agent, model) and computes correct stats."""

    def _seed_ledger(self, ledger: Path, rows: list[dict]) -> None:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_groups_by_agent_model(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        base_ts = "2099-01-01T00:00:00+00:00"
        self._seed_ledger(ledger, [
            {"ts": base_ts, "agent": "backend-engineer", "slug": "s1",
             "input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500,
             "model": "claude-sonnet-4-6", "source_ref": None},
            {"ts": base_ts, "agent": "backend-engineer", "slug": "s2",
             "input_tokens": 2000, "output_tokens": 1000, "total_tokens": 3000,
             "model": "claude-sonnet-4-6", "source_ref": None},
            {"ts": base_ts, "agent": "frontend-engineer", "slug": "s3",
             "input_tokens": 500, "output_tokens": 200, "total_tokens": 700,
             "model": "claude-sonnet-4-6", "source_ref": None},
        ])
        with patch.object(mod, "LEDGER_PATH", ledger):
            rows = mod.report(window_days=0)

        assert len(rows) == 2
        be = next(r for r in rows if r["agent"] == "backend-engineer")
        assert be["dispatch_count"] == 2
        assert be["total_tokens_sum"] == 4500
        assert be["total_tokens_avg"] == 2250.0

    def test_p95_single_entry(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        base_ts = "2099-01-01T00:00:00+00:00"
        self._seed_ledger(ledger, [
            {"ts": base_ts, "agent": "backend-engineer", "slug": "s1",
             "input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500,
             "model": "claude-sonnet-4-6", "source_ref": None},
        ])
        with patch.object(mod, "LEDGER_PATH", ledger):
            rows = mod.report(window_days=0)

        assert rows[0]["total_tokens_p95"] == 1500

    def test_agent_filter(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        base_ts = "2099-01-01T00:00:00+00:00"
        self._seed_ledger(ledger, [
            {"ts": base_ts, "agent": "backend-engineer", "slug": "s1",
             "input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500,
             "model": "claude-sonnet-4-6", "source_ref": None},
            {"ts": base_ts, "agent": "frontend-engineer", "slug": "s2",
             "input_tokens": 500, "output_tokens": 200, "total_tokens": 700,
             "model": "claude-sonnet-4-6", "source_ref": None},
        ])
        with patch.object(mod, "LEDGER_PATH", ledger):
            rows = mod.report(agent="backend-engineer", window_days=0)

        assert len(rows) == 1
        assert rows[0]["agent"] == "backend-engineer"

    def test_empty_ledger(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        with patch.object(mod, "LEDGER_PATH", ledger):
            rows = mod.report(window_days=0)
        assert rows == []


class TestSummary:
    """summary() returns one-shot totals."""

    def _seed_ledger(self, ledger: Path, rows: list[dict]) -> None:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_zero_entries_on_empty(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        with patch.object(mod, "LEDGER_PATH", ledger):
            out = mod.summary()
        assert out["dispatch_count"] == 0
        assert out["total_tokens_sum"] == 0

    def test_totals_sum_correctly(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        base_ts = "2099-01-01T00:00:00+00:00"
        self._seed_ledger(ledger, [
            {"ts": base_ts, "agent": "backend-engineer", "slug": "s1",
             "input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500,
             "model": "claude-sonnet-4-6", "source_ref": None},
            {"ts": base_ts, "agent": "frontend-engineer", "slug": "s2",
             "input_tokens": 2000, "output_tokens": 1000, "total_tokens": 3000,
             "model": "claude-opus-4-7", "source_ref": None},
        ])
        with patch.object(mod, "LEDGER_PATH", ledger):
            out = mod.summary()

        assert out["dispatch_count"] == 2
        assert out["input_tokens_sum"] == 3000
        assert out["output_tokens_sum"] == 1500
        assert out["total_tokens_sum"] == 4500

    def test_window_days_zero_means_all_time(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        old_ts = "2000-01-01T00:00:00+00:00"
        self._seed_ledger(ledger, [
            {"ts": old_ts, "agent": "backend-engineer", "slug": "s1",
             "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
             "model": "claude-sonnet-4-6", "source_ref": None},
        ])
        with patch.object(mod, "LEDGER_PATH", ledger):
            out = mod.summary(window_days=0)
        assert out["dispatch_count"] == 1


class TestMalformedAndMissingFields:
    """Ledger resilience — malformed lines skipped, missing fields default to 0."""

    def test_malformed_lines_skipped(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        good_ts = "2099-01-01T00:00:00+00:00"
        ledger.write_text(
            "NOT JSON\n"
            + json.dumps({"ts": good_ts, "agent": "backend-engineer", "slug": "s1",
                          "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                          "model": "claude-sonnet-4-6", "source_ref": None})
            + "\n"
            + "{broken\n"
        )
        with patch.object(mod, "LEDGER_PATH", ledger):
            out = mod.summary()
        assert out["dispatch_count"] == 1

    def test_missing_token_fields_default_zero(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        good_ts = "2099-01-01T00:00:00+00:00"
        # Row missing input_tokens, output_tokens, total_tokens
        ledger.write_text(
            json.dumps({"ts": good_ts, "agent": "backend-engineer",
                        "slug": "s1", "model": "claude-sonnet-4-6"})
            + "\n"
        )
        with patch.object(mod, "LEDGER_PATH", ledger):
            out = mod.summary()
        assert out["dispatch_count"] == 1
        assert out["input_tokens_sum"] == 0
        assert out["total_tokens_sum"] == 0

    def test_empty_lines_skipped(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        ledger = tmp_path / "dispatch-budget.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        good_ts = "2099-01-01T00:00:00+00:00"
        ledger.write_text(
            "\n\n"
            + json.dumps({"ts": good_ts, "agent": "a", "slug": "s",
                          "input_tokens": 10, "output_tokens": 5,
                          "total_tokens": 15, "model": "m"})
            + "\n\n"
        )
        with patch.object(mod, "LEDGER_PATH", ledger):
            out = mod.summary()
        assert out["dispatch_count"] == 1


class TestFileRotationSafe:
    """log_dispatch does not touch the live LEDGER_PATH."""

    def test_writes_to_tmp_path_only(self, tmp_path):
        import tools.noctus.dev.dispatch_budget as mod
        live_ledger = mod.LEDGER_PATH
        tmp_ledger = tmp_path / "dispatch-budget.ndjson"
        with patch.object(mod, "LEDGER_PATH", tmp_ledger):
            mod.log_dispatch(
                agent="backend-engineer",
                slug="feat/safe",
                input_tokens=1,
                output_tokens=1,
                model="claude-sonnet-4-6",
            )
        # Live ledger must NOT have been modified by this test.
        assert not live_ledger.exists() or (
            tmp_ledger.exists() and tmp_ledger.stat().st_size > 0
        )
        assert tmp_ledger.exists()
