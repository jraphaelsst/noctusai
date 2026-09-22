"""Colocated tests for noctus.dev.build (noctus.dev.build_parallel).

Focused on the ASLEEP-product skip (`deploy/fleet/active-scope.txt`,
`product_scope.filter_active`) added alongside `gate_sweep` / `testing` /
`smoke_fleet` / `predeploy_check`'s: an implicit fleet-wide build (slugs=None)
must skip an asleep product and name it in `skipped_asleep`; an explicit
`slugs=[...]` request still builds an asleep one but flags it in
`asleep_requested` — never silently either way.

No real vite/npm/git — `subprocess.run` is monkeypatched (the smoke_fleet
pattern used across this toolkit's other colocated tests).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import build as B  # noqa: E402


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="✓ built in 10ms", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_frontend(root: Path, slug: str) -> None:
    fe = root / "products" / slug / "frontend"
    fe.mkdir(parents=True)
    (fe / "package.json").write_text("{}")


def _write_active_scope(root: Path, active: list[str]) -> None:
    fleet_dir = root / "deploy" / "fleet"
    fleet_dir.mkdir(parents=True, exist_ok=True)
    (fleet_dir / "active-scope.txt").write_text("\n".join(active) + "\n")


def _fake_vite_run(cmd, cwd, capture_output, text, timeout):
    return _FakeCompletedProcess()


def test_build_products_default_sweep_skips_asleep_product(tmp_path, monkeypatch):
    _make_frontend(tmp_path, "awake-one")
    _make_frontend(tmp_path, "asleep-one")
    _write_active_scope(tmp_path, ["awake-one"])

    monkeypatch.setattr(B.subprocess, "run", _fake_vite_run)
    result = B.build_products(repo_root=tmp_path)

    assert result["requested"] == ["awake-one"]
    assert result["skipped_asleep"] == ["asleep-one"]
    assert result["all_green"] is True


def test_build_products_no_scope_file_builds_everyone(tmp_path, monkeypatch):
    """Missing active-scope.txt fails toward COVERAGE — no product is
    silently dropped just because the scope file hasn't been generated."""
    _make_frontend(tmp_path, "a-product")
    _make_frontend(tmp_path, "b-product")

    monkeypatch.setattr(B.subprocess, "run", _fake_vite_run)
    result = B.build_products(repo_root=tmp_path)

    assert sorted(result["requested"]) == ["a-product", "b-product"]
    assert "skipped_asleep" not in result


def test_build_products_explicit_asleep_slug_still_builds_but_flagged(tmp_path, monkeypatch):
    _make_frontend(tmp_path, "asleep-one")
    _write_active_scope(tmp_path, ["core"])  # asleep-one not active

    monkeypatch.setattr(B.subprocess, "run", _fake_vite_run)
    result = B.build_products(slugs=["asleep-one"], repo_root=tmp_path)

    assert result["requested"] == ["asleep-one"]
    assert result["results"][0]["success"] is True  # actually ran
    assert result["asleep_requested"] == ["asleep-one"]


def test_build_products_explicit_active_slug_no_flag(tmp_path, monkeypatch):
    _make_frontend(tmp_path, "awake-one")
    _write_active_scope(tmp_path, ["awake-one"])

    monkeypatch.setattr(B.subprocess, "run", _fake_vite_run)
    result = B.build_products(slugs=["awake-one"], repo_root=tmp_path)

    assert "asleep_requested" not in result


def test_build_products_changed_only_seed_fanout_skips_asleep_product(tmp_path, monkeypatch):
    """A `seed/` change fans `_detect_changed_products` out to every
    product — the same fan-out `gate_sweep`'s `seed_fleet_wide` covers —
    and that fan-out must also stay active-only."""
    _make_frontend(tmp_path, "awake-one")
    _make_frontend(tmp_path, "asleep-one")
    _write_active_scope(tmp_path, ["awake-one"])

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        if cmd[:2] == ["git", "diff"]:
            return _FakeCompletedProcess(returncode=0, stdout="seed/lib/backend/x.py\n")
        return _fake_vite_run(cmd, cwd, capture_output, text, timeout)

    monkeypatch.setattr(B.subprocess, "run", fake_run)
    result = B.build_products(changed_only=True, repo_root=tmp_path)

    assert result["requested"] == ["awake-one"]
    assert result["skipped_asleep"] == ["asleep-one"]
