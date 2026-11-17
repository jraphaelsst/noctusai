"""pre-push / pre-commit: the toolkit is the PRIMARY's, and the branch pointer is written by construction.

CI-refusal inventory 2026-11-14, two recurring classes:
  (12)  72 branch-tree-mirror refusals in 11 sessions: a branch with no pointer / one older than 72h, and every
        engineer hand-appended a pointer and re-pushed. The hook now writes or refreshes it through the
        branch_pointer writer (`--ensure-branch-pointer`) BEFORE the keeper judges; the keeper stays the backstop.
  (15a) ~144 stale or invented CLI flags: hooks ran the WORKTREE's cli.py. They now run the PRIMARY checkout's
        (resolved from --git-common-dir) and pass `--worktree-path <the worktree>` on every hooked call.

Real git, the REAL pre-push hook; only the toolkit CLI is a stub (it records argv so the test can see WHICH
cli.py ran and with what).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[3] / "scripts" / "hooks"
HOOK = HOOKS / "pre-push"
_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t", "NOCTUS_HOOK_QUIET": "1"}
for _k in ("NOCTUS_ALLOW_MAIN_PUSH", "NOCTUS_SKIP_EMBED_REFRESH", "NOCTUS_SKIP_DOC_STALENESS",
           "NOCTUS_HOOK_OWN_TOOLKIT", "NOCTUS_SKIP_BRANCH_TREE_CHECK"):
    _ENV.pop(_k, None)

_STUB_CLI = """\
import pathlib, sys
here = pathlib.Path(__file__).resolve().parent
a = sys.argv[1:]
with open(here / "calls.log", "a") as f:
    f.write(" ".join(a) + "\\n")
if "--ensure-branch-pointer" in a:
    name = a[a.index("--ensure-branch-pointer") + 1]
    if (here / "ensure_fails").exists():
        print("cannot write the pointer: no session id"); sys.exit(1)
    with open(here / "pointers.txt", "a") as f:
        f.write(name + "\\n")
    print("ensured " + name); sys.exit(0)
if "--check-branch-tree-mirror" in a:
    name = a[a.index("--check-branch-tree-mirror") + 1]
    if name in (here / "pointers.txt").read_text().split():
        print("ok"); sys.exit(0)
    print("[high] No branch-pointer found for %r" % name); sys.exit(1)
sys.exit(0)
"""

# A branch cut before a flag landed / carrying a broken cli.py: it knows no flag at all and says so.
_BROKEN_CLI = """\
import pathlib, sys
(pathlib.Path(__file__).resolve().parent / "ran").write_text("the worktree's own cli.py ran")
print("cli.py: error: unrecognized arguments", file=sys.stderr); sys.exit(2)
"""


def git(cwd, *a, check=True):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=_ENV)
    if check and r.returncode:
        raise AssertionError(r.stderr)
    return r


@pytest.fixture()
def primary(tmp_path):
    origin, repo = tmp_path / "origin.git", tmp_path / "primary"
    git(tmp_path, "init", "--bare", "-b", "dev", str(origin))
    git(tmp_path, "clone", str(origin), str(repo))
    git(repo, "checkout", "-b", "dev")
    tool = repo / "mcp" / "noctusai"
    (tool / ".venv" / "bin").mkdir(parents=True)
    (tool / ".venv" / "bin" / "python").symlink_to(sys.executable)
    (tool / "cli.py").write_text(_STUB_CLI)
    (tool / "pointers.txt").write_text("")
    (repo / ".gitignore").write_text("calls.log\npointers.txt\nensure_fails\nran\n.venv\n")
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "init")
    git(repo, "push", "--no-verify", "origin", "dev")  # seeding the fixture only, before the hook exists
    git(repo, "branch", "feat/x")
    git(repo, "worktree", "add", str(tmp_path / "wt"), "feat/x")
    wt = tmp_path / "wt"
    (wt / "b.txt").write_text("b\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-m", "feat: b")
    hook = repo / ".git" / "hooks" / "pre-push"
    shutil.copy(HOOK, hook)
    hook.chmod(0o755)
    return repo


def calls(repo):
    log = repo / "mcp" / "noctusai" / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


# -- (12) the pointer is written by construction ---------------------------------------------------

def test_a_push_with_no_pointer_succeeds_and_leaves_the_pointer_written(primary):
    r = git(primary.parent / "wt", "push", "origin", "feat/x", check=False)
    assert r.returncode == 0, r.stderr
    assert "feat/x" in (primary / "mcp" / "noctusai" / "pointers.txt").read_text().split()
    assert any("--ensure-branch-pointer feat/x" in c for c in calls(primary))


def test_the_pointer_is_written_before_the_keeper_judges_it(primary):
    git(primary.parent / "wt", "push", "origin", "feat/x")
    order = [c for c in calls(primary) if "--ensure-branch-pointer" in c or "--check-branch-tree-mirror" in c]
    assert [("ensure" if "--ensure" in c else "check") for c in order] == ["ensure", "check"]


def test_a_pointer_that_cannot_be_written_still_blocks_loudly_naming_why(primary):
    (primary / "mcp" / "noctusai" / "ensure_fails").write_text("1")
    r = git(primary.parent / "wt", "push", "origin", "feat/x", check=False)
    assert r.returncode != 0
    assert "was NOT written" in r.stderr and "no session id" in r.stderr
    assert "branch-tree mirror keeper BLOCKED" in r.stderr
    assert "refs/heads/feat/x" not in git(primary, "ls-remote", "origin").stdout


# -- (15a) the primary's toolkit judges the worktree -----------------------------------------------

def _wt_broken_cli(primary):
    wt = primary.parent / "wt"
    (wt / "mcp" / "noctusai" / "cli.py").write_text(_BROKEN_CLI)
    git(wt, "add", "-A")
    git(wt, "commit", "-m", "chore: this branch's cli.py is broken")
    return wt


def test_a_worktree_whose_cli_is_broken_is_still_judged_by_the_primary_toolkit(primary):
    wt = _wt_broken_cli(primary)
    r = git(wt, "push", "origin", "feat/x", check=False)
    assert r.returncode == 0, r.stderr
    assert not (wt / "mcp" / "noctusai" / "ran").exists(), "the worktree's own cli.py must not run"
    assert calls(primary), "the primary's cli.py must have run"


def test_every_hooked_call_judges_the_worktree_tree(primary):
    wt = _wt_broken_cli(primary)
    git(wt, "push", "origin", "feat/x")
    want = f"--worktree-path {os.path.realpath(wt)}"
    cs = [c for c in calls(primary) if c.startswith("--")]  # a multi-line --bp-paths value spills onto extra log lines
    assert cs and all(want in c for c in cs), [c for c in cs if want not in c]


def test_the_branch_own_toolkit_is_a_named_exception_with_a_reason(primary):
    wt = _wt_broken_cli(primary)
    hook_env = {**_ENV, "NOCTUS_HOOK_OWN_TOOLKIT": "short"}
    r = subprocess.run(["git", "push", "origin", "feat/x"], cwd=wt, capture_output=True, text=True, env=hook_env)
    assert r.returncode != 0 and "needs a reason of 10+ characters" in r.stderr
    hook_env["NOCTUS_HOOK_OWN_TOOLKIT"] = "this commit introduces the flag the hook calls"
    r = subprocess.run(["git", "push", "origin", "feat/x"], cwd=wt, capture_output=True, text=True, env=hook_env)
    assert "running THIS branch's own toolkit" in r.stderr
    assert (wt / "mcp" / "noctusai" / "ran").exists()


# -- static audit, derived from the hook files themselves ------------------------------------------

@pytest.mark.parametrize("hook,var", [("pre-push", "CLI_PP"), ("pre-commit", "CLI")])
def test_every_toolkit_invocation_in_the_hook_passes_worktree_path(hook, var):
    """No hand list: every line that runs `"$<var>"` as a command carries --worktree-path."""
    run = re.compile(r'"\$(?:PY|PY_PP|_ld_py)"\s+"\$' + var + r'"')
    bad = []
    for n, line in enumerate((HOOKS / hook).read_text().splitlines(), 1):
        if line.lstrip().startswith("#") or not run.search(line):
            continue
        if "--worktree-path" not in line:
            bad.append(f"{hook}:{n}: {line.strip()[:140]}")
    assert not bad, "a hooked call without --worktree-path judges the toolkit's own tree:\n" + "\n".join(bad)


@pytest.mark.parametrize("hook", ["pre-push", "pre-commit"])
def test_the_hook_resolves_its_toolkit_from_the_primary_checkout(hook):
    text = (HOOKS / hook).read_text()
    assert "--git-common-dir" in text and "NOCTUS_HOOK_OWN_TOOLKIT" in text
