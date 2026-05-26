"""Tests for `check_codification_pipeline_health` meta-keeper.

This keeper is advisory — it surfaces when the s1→s4 codification
pipeline goes silent for an extended window. The meta-discipline:
even when no individual keeper fires, infrastructure drift may
accumulate silently if no patterns are being codified.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from datetime import date, timedelta

import pytest

from tools.noctus.dev import compliance


def _write_ledger(tmp_path: Path, entries: list[dict]) -> Path:
    ph = tmp_path / "project-history"
    ph.mkdir(parents=True, exist_ok=True)
    ledger = ph / "auto-improvement.ndjson"
    with ledger.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return ledger


def _entry(days_ago: int, status: str, target: str = "x") -> dict:
    ts = (date.today() - timedelta(days=days_ago)).isoformat()
    return {
        "ts": ts,
        "agent": "tech-lead",
        "scope": "broad",
        "kind": "improvement",
        "target": target,
        "description": "test entry",
        "status": status,
        "source_ref": "test",
    }


class TestPipelineHealth:
    def test_silent_skip_when_no_ledger(self, tmp_path):
        # Fresh tree — no ndjson yet. Pipeline can't be silent if it's brand new.
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        assert issues == []

    def test_green_when_all_three_recent(self, tmp_path):
        _write_ledger(tmp_path, [
            _entry(1, "s2-memory"),
            _entry(2, "s3-codified"),
            _entry(3, "s4-keeper"),
        ])
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        assert issues == []

    def test_surfaces_when_s2_silent(self, tmp_path):
        _write_ledger(tmp_path, [
            _entry(45, "s2-memory"),   # past 30-day threshold
            _entry(2, "s3-codified"),
            _entry(3, "s4-keeper"),
        ])
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        assert len(issues) == 1
        assert "s2-memory" in issues[0]["symbol"]
        assert issues[0]["severity"] == "warning"

    def test_surfaces_when_s3_silent(self, tmp_path):
        _write_ledger(tmp_path, [
            _entry(1, "s2-memory"),
            _entry(75, "s3-codified"),  # past 60-day threshold
            _entry(3, "s4-keeper"),
        ])
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        symbols = [i["symbol"] for i in issues]
        assert any("s3-codified-silent" in s for s in symbols)

    def test_surfaces_when_s4_silent(self, tmp_path):
        _write_ledger(tmp_path, [
            _entry(1, "s2-memory"),
            _entry(2, "s3-codified"),
            _entry(120, "s4-keeper"),  # past 90-day threshold
        ])
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        symbols = [i["symbol"] for i in issues]
        assert any("s4-keeper-silent" in s for s in symbols)

    def test_surfaces_when_status_never_logged(self, tmp_path):
        _write_ledger(tmp_path, [
            _entry(1, "s2-memory"),
            # no s3 or s4 entries ever
        ])
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        symbols = [i["symbol"] for i in issues]
        assert any("s3-codified-never" in s for s in symbols)
        assert any("s4-keeper-never" in s for s in symbols)

    def test_custom_thresholds(self, tmp_path):
        _write_ledger(tmp_path, [
            _entry(15, "s2-memory"),
            _entry(15, "s3-codified"),
            _entry(15, "s4-keeper"),
        ])
        # With strict thresholds (10 days), all three should surface.
        issues = compliance.check_codification_pipeline_health(
            repo_root=tmp_path,
            s2_silence_days=10,
            s3_silence_days=10,
            s4_silence_days=10,
        )
        assert len(issues) == 3

    def test_malformed_json_lines_skipped(self, tmp_path):
        ph = tmp_path / "project-history"
        ph.mkdir(parents=True, exist_ok=True)
        ledger = ph / "auto-improvement.ndjson"
        with ledger.open("w", encoding="utf-8") as fh:
            fh.write("not valid json\n")
            fh.write(json.dumps(_entry(1, "s2-memory")) + "\n")
            fh.write("\n")  # empty line
            fh.write(json.dumps(_entry(1, "s3-codified")) + "\n")
            fh.write(json.dumps(_entry(1, "s4-keeper")) + "\n")
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        # All 3 statuses present and recent → green.
        assert issues == []

    def test_severity_always_warning(self, tmp_path):
        # Force all 3 to surface; all should be 'warning'.
        _write_ledger(tmp_path, [
            _entry(100, "s2-memory"),
            _entry(100, "s3-codified"),
            _entry(100, "s4-keeper"),
        ])
        issues = compliance.check_codification_pipeline_health(repo_root=tmp_path)
        assert all(i["severity"] == "warning" for i in issues)
