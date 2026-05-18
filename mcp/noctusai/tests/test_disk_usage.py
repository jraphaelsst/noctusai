"""Tests for the noctus.dev.check_disk_usage tool.

Behaviour parity with scripts/disk-usage-monitor.sh: the 70/80/90 severity
bands + exit-code 0/1/2/3 mapping + worktree-footprint enumeration.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.disk_usage import _classify, check_disk_usage


class TestClassifyBands:
    """_classify reproduces the shell severity-classification block."""

    def test_under_70_is_ok_exit_0(self):
        sev, code, hint = _classify(69)
        assert (sev, code) == ("OK", 0)
        assert hint == ""

    def test_70_is_caution_exit_1(self):
        sev, code, hint = _classify(70)
        assert (sev, code) == ("CAUTION", 1)
        assert hint

    def test_79_is_caution(self):
        assert _classify(79)[:2] == ("CAUTION", 1)

    def test_80_is_warning_exit_2(self):
        assert _classify(80)[:2] == ("WARNING", 2)

    def test_89_is_warning(self):
        assert _classify(89)[:2] == ("WARNING", 2)

    def test_90_is_critical_exit_3(self):
        assert _classify(90)[:2] == ("CRITICAL", 3)

    def test_100_is_critical(self):
        assert _classify(100)[:2] == ("CRITICAL", 3)


class TestCheckDiskUsageContract:
    def test_returns_structured_dict(self, tmp_path):
        result = check_disk_usage(repo_root=tmp_path, target_path=tmp_path)
        assert set(result) >= {
            "timestamp", "volume", "pct_used", "avail_gb", "total_gb",
            "worktree_count", "worktree_size_bytes", "severity",
            "exit_code", "status", "hint", "auto_clean_ran",
            "auto_clean_result",
        }
        assert result["severity"] in ("OK", "CAUTION", "WARNING", "CRITICAL")
        assert result["status"] == result["severity"]
        assert result["exit_code"] in (0, 1, 2, 3)
        assert result["pct_used"] >= 0
        assert result["auto_clean_ran"] is False
        assert result["auto_clean_result"] is None

    def test_worktree_footprint_counted(self, tmp_path):
        wt = tmp_path / ".claude" / "worktrees"
        (wt / "agent-aaa").mkdir(parents=True)
        (wt / "agent-bbb").mkdir(parents=True)
        (wt / "not-an-agent").mkdir(parents=True)
        (wt / "agent-aaa" / "f.txt").write_text("x" * 100)
        result = check_disk_usage(repo_root=tmp_path, target_path=tmp_path)
        assert result["worktree_count"] == 2  # only agent-* dirs
        assert result["worktree_size_bytes"] >= 100

    def test_no_worktree_dir_is_zero(self, tmp_path):
        result = check_disk_usage(repo_root=tmp_path, target_path=tmp_path)
        assert result["worktree_count"] == 0
        assert result["worktree_size_bytes"] == 0

    def test_band_mapping_via_mocked_usage(self, tmp_path):
        """Mock shutil.disk_usage (external OS call) to drive each band
        deterministically — no monkey-patching of our own code."""
        Usage = mock.Mock()
        # 85% used → WARNING / exit 2.
        fake = mock.Mock(total=1000, used=850, free=150)
        with mock.patch("tools.noctus.dev.disk_usage.shutil.disk_usage", return_value=fake):
            r = check_disk_usage(repo_root=tmp_path, target_path=tmp_path)
        assert r["pct_used"] == 85
        assert r["severity"] == "WARNING"
        assert r["exit_code"] == 2
        assert "Cleanup REQUIRED" in r["hint"]

    def test_critical_band_via_mock(self, tmp_path):
        fake = mock.Mock(total=1000, used=950, free=50)
        with mock.patch("tools.noctus.dev.disk_usage.shutil.disk_usage", return_value=fake):
            r = check_disk_usage(repo_root=tmp_path, target_path=tmp_path)
        assert r["severity"] == "CRITICAL"
        assert r["exit_code"] == 3

    def test_ok_band_via_mock(self, tmp_path):
        fake = mock.Mock(total=1000, used=100, free=900)
        with mock.patch("tools.noctus.dev.disk_usage.shutil.disk_usage", return_value=fake):
            r = check_disk_usage(repo_root=tmp_path, target_path=tmp_path)
        assert r["severity"] == "OK"
        assert r["exit_code"] == 0
        assert r["hint"] == ""


class TestMcpRegistration:
    def test_register_callable(self):
        from tools.noctus.dev.disk_usage import register
        assert callable(register)

    def test_register_wires_tool_onto_a_server(self):
        """The module's own register() wires the tool. (Global build_server()
        wiring lands when the architect adds disk_usage to
        tools/noctus/dev/__init__.py per the integration recipe.)"""
        from mcp.server.fastmcp import FastMCP

        from tools.noctus.dev.disk_usage import register
        s = FastMCP(name="t")
        register(s)
        assert "noctus.dev.check_disk_usage" in s._tool_manager._tools
