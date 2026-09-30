"""`decide_wired_worktree_npm`: plain `npm install` in a wire_env'd worktree
writes through symlinks into the PRIMARY's node_modules; refuse it, allow
`--package-lock-only`. KB § PATTERNS/common/self-branching-mode.md §5a."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.primary_write_guard import decide_wired_worktree_npm  # noqa: E402


def _wired(tmp_path):
    primary = tmp_path / "primary" / "fe" / "node_modules" / "@vitest"
    primary.mkdir(parents=True)
    wt = tmp_path / "repo" / ".claude" / "worktrees" / "x" / "fe"
    (wt / "node_modules").mkdir(parents=True)
    (wt / "package.json").write_text("{}")
    (wt / "node_modules" / "@vitest").symlink_to(primary)
    return wt


def _d(cmd, cwd):
    return decide_wired_worktree_npm("Bash", {"command": cmd}, str(cwd))


def test_plain_install_refused(tmp_path):
    v = _d("npm install", _wired(tmp_path))
    assert v is not None and "--package-lock-only" in v["reason"]


def test_add_ci_prefix_and_cd_refused(tmp_path):
    wt = _wired(tmp_path)
    assert _d("npm i lodash", wt)
    assert _d("npm ci", wt)
    assert _d(f"npm --prefix {wt} install", tmp_path)
    assert _d(f"cd {wt} && npm install", tmp_path)


def test_package_lock_only_allowed(tmp_path):
    assert _d("npm install --package-lock-only", _wired(tmp_path)) is None


def test_readonly_and_run_allowed(tmp_path):
    wt = _wired(tmp_path)
    assert _d("npm run build", wt) is None
    assert _d("npm ls", wt) is None


def test_unwired_worktree_allowed(tmp_path):
    wt = tmp_path / "repo" / ".claude" / "worktrees" / "y" / "fe"
    (wt / "node_modules" / "a").mkdir(parents=True)
    (wt / "package.json").write_text("{}")
    assert _d("npm install", wt) is None


def test_outside_worktree_allowed(tmp_path):
    assert _d("npm install", tmp_path) is None


def test_non_bash_allowed(tmp_path):
    assert decide_wired_worktree_npm("Edit", {"command": "npm install"}, str(tmp_path)) is None
