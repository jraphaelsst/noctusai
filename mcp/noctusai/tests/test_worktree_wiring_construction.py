"""Fresh worktrees are wired by construction (2026-11-15): the node toolchain, and the pre-push hook that runs.

  * `node_toolchain.provision`: a lockfile-identical link, else a LOUD `npm ci --prefix` (never through a symlink).
  * the SessionStart/SubagentStart hook gives a harness agent worktree its toolchain.
  * a stale installed pre-push hands over to the tree's newer hook, or says which legs are absent.

Real git + real filesystem in tmp dirs; `npm` is a real executable on PATH (a recorder script), the hook is the REAL one.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import node_toolchain as nt  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
HOOK = REPO / "scripts" / "hooks" / "pre-push"
WIRE_HOOK = REPO / "scripts" / "hooks" / "claude-wire-worktree-toolchain.py"
_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
for _k in ("NOC_HOOK_REEXEC", "NOCTUS_HOOK_OWN_TOOLKIT", "NOCTUS_ALLOW_MAIN_PUSH"):
    _ENV.pop(_k, None)


def git(cwd, *a):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=_ENV)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _fake_npm(bindir: Path, *, rc: int = 0) -> Path:
    """A real `npm`: records its argv and, on `ci --prefix <dir>`, creates <dir>/node_modules/ts-morph."""
    bindir.mkdir(parents=True, exist_ok=True)
    exe = bindir / "npm"
    exe.write_text(f"""#!/bin/sh
echo "$@" >> "{bindir}/npm.log"
[ {rc} -ne 0 ] && {{ echo "npm ERR! boom" >&2; exit {rc}; }}
dir="$3"; mkdir -p "$dir/node_modules/ts-morph"
""")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def _node_tree(root: Path, lock: str, *, installed: bool) -> Path:
    nd = root / "mcp" / "noctusai" / "node"
    nd.mkdir(parents=True, exist_ok=True)
    (nd / "package-lock.json").write_text(lock)
    if installed:
        (nd / "node_modules" / "ts-morph").mkdir(parents=True)
    return nd


@pytest.fixture()
def path_with_npm(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    _fake_npm(bindir)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return bindir


def test_provision_links_a_lockfile_identical_install_without_npm(tmp_path, path_with_npm):
    primary = tmp_path / "primary"
    _node_tree(primary, "L1", installed=True)
    wt = tmp_path / "wt"
    _node_tree(wt, "L1", installed=False)
    tc = nt.provision(wt, sources=[primary])
    assert tc.ok and tc.source == "linked" and (wt / "mcp/noctusai/node/node_modules").is_symlink()
    assert not (path_with_npm / "npm.log").exists()  # nothing was installed


def test_provision_installs_loudly_when_the_lockfile_differs_and_never_through_a_link(tmp_path, path_with_npm):
    primary = tmp_path / "primary"
    pn = _node_tree(primary, "OLD", installed=True)
    wt = tmp_path / "wt"
    wn = _node_tree(wt, "NEW", installed=False)
    (wn / "node_modules").symlink_to(pn / "node_modules")  # a stale link into the primary's install
    tc = nt.provision(wt, sources=[primary])
    assert tc.ok and tc.source == "installed"
    assert not (wn / "node_modules").is_symlink()                  # the link was removed first ...
    assert (pn / "node_modules" / "ts-morph").is_dir()             # ... so the primary's install is untouched
    assert f"ci --prefix {wn}" in (path_with_npm / "npm.log").read_text()


def test_provision_failure_is_loud_with_npms_own_words(tmp_path, monkeypatch):
    _fake_npm(tmp_path / "bin", rc=3)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    wt = tmp_path / "wt"
    _node_tree(wt, "NEW", installed=False)
    tc = nt.provision(wt, sources=[])
    assert not tc.ok and "npm ci --prefix" in tc.reason and "exit 3" in tc.reason and "boom" in tc.reason


def test_provision_install_false_is_resolve(tmp_path, path_with_npm):
    wt = tmp_path / "wt"
    _node_tree(wt, "NEW", installed=False)
    tc = nt.provision(wt, sources=[], install=False)
    assert not tc.ok and not (path_with_npm / "npm.log").exists()


def _repo_with_agent_worktree(tmp_path: Path, *, wt_lock: str) -> tuple[Path, Path]:
    repo = tmp_path / "primary"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "dev")
    (repo / ".gitignore").write_text("node_modules\n")
    _node_tree(repo, "P", installed=False)
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "scripts" / "hooks" / "claude-wire-worktree-toolchain.py").write_text(WIRE_HOOK.read_text())
    (repo / "mcp" / "noctusai" / "node_toolchain.py").write_text((REPO / "mcp" / "noctusai" / "node_toolchain.py").read_text())
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    (repo / "mcp/noctusai/node/node_modules/ts-morph").mkdir(parents=True)  # the primary IS provisioned (gitignored)
    wt = repo / ".claude" / "worktrees" / "agent-1"
    git(repo, "worktree", "add", "-q", "-b", "feat/a", str(wt))
    if wt_lock != "P":
        (wt / "mcp/noctusai/node/package-lock.json").write_text(wt_lock)
    return repo, wt


def _run_wire_hook(repo: Path, cwd: Path, env_extra: dict | None = None) -> dict:
    r = subprocess.run([sys.executable, str(repo / "scripts/hooks/claude-wire-worktree-toolchain.py")],
                       input=json.dumps({"cwd": str(cwd), "hook_event_name": "SubagentStart"}),
                       capture_output=True, text=True, env={**_ENV, **(env_extra or {})})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else {}


def test_the_session_hook_wires_a_harness_agent_worktree(tmp_path):
    repo, wt = _repo_with_agent_worktree(tmp_path, wt_lock="P")
    out = _run_wire_hook(repo, wt)
    assert (wt / "mcp/noctusai/node/node_modules").is_symlink()
    assert "node toolchain linked" in out["additionalContext"] and out["hookEventName"] == "SubagentStart"
    assert _run_wire_hook(repo, wt) == {}  # idempotent: second run has nothing to say


def test_the_session_hook_is_loud_when_it_cannot_provision(tmp_path, monkeypatch):
    repo, wt = _repo_with_agent_worktree(tmp_path, wt_lock="DIFFERENT")
    empty = tmp_path / "emptybin"
    empty.mkdir()
    out = _run_wire_hook(repo, wt, {"PATH": f"{empty}{os.pathsep}/usr/bin{os.pathsep}/bin"})  # no npm anywhere
    assert "LOUD" in out["additionalContext"] and "npm ci --prefix" in out["additionalContext"]


def test_the_session_hook_does_nothing_in_the_primary(tmp_path):
    repo, _ = _repo_with_agent_worktree(tmp_path, wt_lock="P")
    assert _run_wire_hook(repo, repo) == {}


# ── the stale installed pre-push ────────────────────────────────────────────────────────────────────────────────
def _hook_world(tmp_path: Path, *, tree_hook_exec: bool = True):
    """Primary with an INSTALLED (stale) copy of the real hook; a worktree whose own scripts/hooks/pre-push is newer."""
    repo = tmp_path / "primary"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "dev")
    (repo / "scripts" / "hooks").mkdir(parents=True)
    tree_hook = repo / "scripts" / "hooks" / "pre-push"
    tree_hook.write_text("#!/usr/bin/env bash\n# NOC-HOOK-STAMP: 9\n# NOC-HOOK-LEGS: protected-branches brand-new-leg\n"
                         'echo "TREE-HOOK RAN args=$* reexec=${NOC_HOOK_REEXEC:-} stdin=$(cat)"\nexit 0\n')
    tree_hook.chmod(0o755 if tree_hook_exec else 0o644)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    stale = HOOK.read_text().replace("# NOC-HOOK-STAMP: 1", "# NOC-HOOK-STAMP: 0", 1)
    installed = repo / ".git" / "hooks" / "pre-push"
    installed.write_text(stale)
    installed.chmod(0o755)
    return repo, installed


def _push(installed: Path, cwd: Path, lines: str, **env):
    return subprocess.run([str(installed), "origin", "x"], cwd=cwd, input=lines, capture_output=True, text=True,
                          env={**_ENV, **env})


def test_a_stale_installed_hook_dispatches_to_the_trees_current_hook(tmp_path):
    repo, installed = _hook_world(tmp_path)
    r = _push(installed, repo, "refs/heads/feat/a abc refs/heads/feat/a 000")
    assert "TREE-HOOK RAN" in r.stdout and "reexec=1" in r.stdout and "stdin=refs/heads/feat/a abc" in r.stdout  # stdin handed over
    assert "older than this tree's" in r.stderr and "brand-new-leg" in r.stderr and "fast-forward the primary" in r.stderr


def test_when_it_cannot_dispatch_the_missing_legs_are_named_loudly(tmp_path):
    repo, installed = _hook_world(tmp_path, tree_hook_exec=False)
    r = _push(installed, repo, "refs/heads/feat/a abc refs/heads/main 000")
    assert "NOC-REMEDIATE[hook-leg-absent-loud]" in r.stderr and "brand-new-leg" in r.stderr
    assert "TREE-HOOK RAN" not in r.stdout


def test_a_current_hook_is_silent(tmp_path):
    repo, installed = _hook_world(tmp_path)
    installed.write_text(HOOK.read_text())  # stamp equal to the real hook's, tree hook stamp lowered below
    (repo / "scripts" / "hooks" / "pre-push").write_text("# NOC-HOOK-STAMP: 1\n")
    r = _push(installed, repo, "refs/heads/feat/a abc refs/heads/main 000")
    assert "older than" not in r.stderr and "hook-leg-absent-loud" not in r.stderr
