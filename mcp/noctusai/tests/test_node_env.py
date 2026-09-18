"""Colocated tests for the shared node-toolchain-readiness predicate
(`node_env.node_deps_ready`) — the 2026-09-17 fix for the "a fresh worktree
false-reds a node-toolchain gate because node_modules is gitignored and
therefore absent" recurrence (four incidents, one session). Consumed by
`predeploy_check`'s `frontend_build` leg; see also the MCP toolkit's own
ts-morph-availability check in `compliance.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from node_env import node_deps_ready  # noqa: E402


def test_absent_node_modules_is_not_ready(tmp_path):
    pkg = tmp_path / "frontend"
    pkg.mkdir()
    assert node_deps_ready(pkg) is False


def test_empty_node_modules_is_not_ready(tmp_path):
    """An existing-but-empty node_modules (a stray .package-lock.json, no
    real packages) must not read as ready — `npm install` remains the fix."""
    pkg = tmp_path / "frontend"
    (pkg / "node_modules").mkdir(parents=True)
    assert node_deps_ready(pkg) is False


def test_populated_node_modules_is_ready(tmp_path):
    pkg = tmp_path / "frontend"
    (pkg / "node_modules" / "react").mkdir(parents=True)
    assert node_deps_ready(pkg) is True


def test_symlinked_node_modules_is_ready(tmp_path):
    """A wire_env-wired seed frontend's node_modules is a whole-dir symlink
    to the primary — must read as ready, same as a real populated dir."""
    real = tmp_path / "primary_node_modules"
    (real / "react").mkdir(parents=True)
    pkg = tmp_path / "frontend"
    pkg.mkdir()
    (pkg / "node_modules").symlink_to(real)
    assert node_deps_ready(pkg) is True


def test_dangling_symlink_node_modules_is_not_ready(tmp_path):
    pkg = tmp_path / "frontend"
    pkg.mkdir()
    (pkg / "node_modules").symlink_to(tmp_path / "nowhere")
    assert node_deps_ready(pkg) is False


def test_require_narrows_to_one_package(tmp_path):
    pkg = tmp_path / "toolkit"
    (pkg / "node_modules" / "some-other-pkg").mkdir(parents=True)
    assert node_deps_ready(pkg, require="ts-morph") is False
    (pkg / "node_modules" / "ts-morph").mkdir()
    assert node_deps_ready(pkg, require="ts-morph") is True
