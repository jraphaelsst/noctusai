"""noctus.dev.mole — wrapper contract + safe-gate (subprocess mocked;
zero real filesystem mutation)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import mole as mole_tool

_JSON = (
    '{"severity":"WARNING","artifacts_mb":120,"environments_mb":0,'
    '"worktrees_stale":7,"next_action":"worktrees: 7 stale → sweep"}'
)


def _fake_proc(returncode=2, stdout=_JSON, stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_scan_is_read_only_and_parses_json():
    with mock.patch("subprocess.run", return_value=_fake_proc()) as m:
        out = mole_tool.run_mole(mode="scan")
    argv = m.call_args[0][0]
    assert argv[2] == "scan" and "--force" not in argv and "--json" in argv
    assert out["ok"] and out["severity"] == "WARNING"
    assert out["worktrees_stale"] == 7
    assert out["executed_destructive"] is False
    assert "merged-to-main" in out["safe_gate"]


def test_sweep_without_force_is_dry_run_never_destructive():
    with mock.patch("subprocess.run", return_value=_fake_proc()) as m:
        out = mole_tool.run_mole(mode="sweep", force=False)
    argv = m.call_args[0][0]
    assert "--force" not in argv  # the safe default — script dry-runs
    assert out["dry_run"] is True
    assert out["executed_destructive"] is False


def test_sweep_with_force_passes_force_flag():
    with mock.patch("subprocess.run", return_value=_fake_proc()) as m:
        out = mole_tool.run_mole(mode="sweep", scope="worktrees", force=True)
    argv = m.call_args[0][0]
    assert "--force" in argv and "--worktrees" in argv
    assert out["executed_destructive"] is True
    assert out["dry_run"] is False


def test_scope_all_emits_no_scope_flag():
    with mock.patch("subprocess.run", return_value=_fake_proc()) as m:
        mole_tool.run_mole(mode="scan", scope="all")
    argv = m.call_args[0][0]
    assert not any(a.startswith("--artifacts") for a in argv)


def test_registers_under_dotted_name():
    captured = {}

    class _Srv:
        def tool(self, *, name, description):
            captured["name"] = name

            def deco(fn):
                return fn

            return deco

    mole_tool.register(_Srv())
    assert captured["name"] == "noctus.dev.mole"
