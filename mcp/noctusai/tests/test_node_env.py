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


def test_transient_entry_predicate():
    from node_env import is_transient_node_modules_entry as t
    for n in (".vite", ".vite-temp", ".cache", ".tmp", ".foo-temp", ".eslintcache"):
        assert t(n), n
    for n in ("react", "@noctusai", ".bin", ".package-lock.json", "vite"):
        assert not t(n), n


def test_prune_removes_only_dangling_transient_links(tmp_path):
    from node_env import prune_dangling_node_modules_links
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / ".vite-temp").symlink_to(tmp_path / "gone")
    (nm / "dangling-pkg").symlink_to(tmp_path / "gone")
    live = tmp_path / "live"
    live.mkdir()
    (nm / ".cache").symlink_to(live)
    assert prune_dangling_node_modules_links(tmp_path) == [".vite-temp"]
    assert not (nm / ".vite-temp").is_symlink()
    assert (nm / "dangling-pkg").is_symlink() and (nm / ".cache").is_symlink()
