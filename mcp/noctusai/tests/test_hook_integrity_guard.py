"""Regression tests for `primary_write_guard.decide_hook_integrity` — the
file-tampering sibling of `decide_git_bypass` (tested in
`test_git_bypass_guard.py`).

THE GAP THIS CLOSES
─────────────────────
`-c core.hooksPath=…` and `--no-verify` are not the only way to disable a
hook. `rm .git/hooks/pre-commit`, `> .git/hooks/pre-commit` (truncate),
`chmod -x .git/hooks/pre-commit`, or writing `.git/config` directly all
disable a hook exactly as effectively — git silently skips a missing or
non-executable hook, no error at all — and NONE of them are a `git`
invocation, so `decide_git_bypass`'s argv-shaped detection cannot see them.

WHY THESE TESTS USE A REAL GIT REPO
──────────────────────────────────────
`decide_hook_integrity` resolves the guarded region via a LIVE
`git rev-parse --git-common-dir` probe — the mechanism that correctly
resolves a linked worktree's `.git` FILE (`gitdir: …`) back to the primary's
real `hooks/`/`config`. Mocking that probe would test the mock, not the
resolution; every test here builds a REAL temporary git repo (and, for the
worktree cases, a REAL linked worktree of it) so the property under test —
"a worktree-relative attack against the PRIMARY's real hooks dir is still
caught" — is exercised for real, the same way the tech-lead verified the
sibling gate live rather than trusting a report.

KB § PATTERNS/common/bypass-rationalization-anti-patterns.md § 2.7 ·
KB § PATTERNS/common/self-branching-mode.md
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.primary_write_guard import (  # noqa: E402
    HOOK_BYPASS_ALLOW_ENV,
    decide_hook_integrity,
)


def _git(*args: str, cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    """A real, throwaway git repo with a real `.git/hooks/` directory."""
    root = tmp_path / "primary"
    root.mkdir()
    _git("init", "-q", cwd=root)
    _git("config", "user.email", "t@example.com", cwd=root)
    _git("config", "user.name", "t", cwd=root)
    (root / "README.md").write_text("x")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "init", cwd=root)
    hooks_dir = root / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "pre-commit").write_text("#!/bin/sh\nexit 0\n")
    (hooks_dir / "pre-commit").chmod(0o755)
    (hooks_dir / "pre-push").write_text("#!/bin/sh\nexit 0\n")
    (hooks_dir / "pre-push").chmod(0o755)
    return root


@pytest.fixture
def linked_worktree(repo) -> Path:
    """A REAL linked worktree of `repo` — `.git` there is a FILE, not a
    directory, which is the exact property this gate has to resolve
    through."""
    wt = repo.parent / "wt"
    _git("worktree", "add", "-q", "-b", "feat/x", str(wt), cwd=repo)
    assert (wt / ".git").is_file()  # the load-bearing assumption of this file
    return wt


def _decide(tool, tool_input, cwd):
    return decide_hook_integrity(tool, tool_input, cwd=str(cwd), allow_override=False)


# ── the incident-class, file-path tools ─────────────────────────────────

def test_editing_git_config_directly_is_refused(repo):
    verdict = _decide("Edit", {"file_path": str(repo / ".git" / "config")}, repo)
    assert verdict is not None
    assert "hooks entirely" not in verdict["reason"]  # sanity: not the OTHER gate's text
    assert ".git" in verdict["reason"]


def test_writing_a_hook_file_directly_is_refused(repo):
    assert _decide("Write", {"file_path": str(repo / ".git" / "hooks" / "pre-commit")}, repo) is not None


def test_multiedit_and_notebookedit_are_covered_too(repo):
    assert _decide("MultiEdit", {"file_path": str(repo / ".git" / "hooks" / "pre-push")}, repo) is not None
    assert _decide("NotebookEdit", {"notebook_path": str(repo / ".git" / "hooks" / "pre-commit")}, repo) is not None


def test_editing_an_ordinary_tracked_file_is_allowed(repo):
    assert _decide("Edit", {"file_path": str(repo / "README.md")}, repo) is None


def test_editing_other_dot_git_content_is_allowed(repo):
    """The deny-list is NARROW — `.git/HEAD`, `.git/refs/…`, `.git/index`
    stay exactly as unguarded as the primary-write gate already leaves
    them; only `hooks/` and `config` are new here."""
    assert _decide("Edit", {"file_path": str(repo / ".git" / "HEAD")}, repo) is None
    assert _decide("Edit", {"file_path": str(repo / ".git" / "index")}, repo) is None


# ── Bash: rm / redirect / cp / mv / tee ──────────────────────────────────

def test_rm_on_a_hook_file_is_refused(repo):
    assert _decide("Bash", {"command": "rm .git/hooks/pre-commit"}, repo) is not None


def test_truncating_redirect_on_a_hook_file_is_refused(repo):
    assert _decide("Bash", {"command": "> .git/hooks/pre-commit"}, repo) is not None


def test_appending_write_to_git_config_is_refused(repo):
    assert _decide("Bash", {"command": 'echo "hooksPath = /dev/null" >> .git/config'}, repo) is not None


def test_overwriting_a_hook_via_cp_is_refused(repo):
    assert _decide("Bash", {"command": "cp evil.sh .git/hooks/pre-commit"}, repo) is not None


def test_overwriting_a_hook_via_mv_is_refused(repo):
    assert _decide("Bash", {"command": "mv evil.sh .git/hooks/pre-commit"}, repo) is not None


def test_the_command_appearing_after_cd_and_ampersand_is_refused(repo):
    assert _decide("Bash", {"command": "cd .git/hooks && rm pre-commit"}, repo) is not None


# ── chmod is MODE-aware ──────────────────────────────────────────────────

def test_chmod_dash_x_on_a_hook_is_refused(repo):
    assert _decide("Bash", {"command": "chmod -x .git/hooks/pre-commit"}, repo) is not None


def test_chmod_symbolic_a_minus_x_is_refused(repo):
    assert _decide("Bash", {"command": "chmod a-x .git/hooks/pre-commit"}, repo) is not None


def test_chmod_numeric_no_exec_bit_is_refused(repo):
    for mode in ("0644", "600", "0400"):
        assert _decide("Bash", {"command": f"chmod {mode} .git/hooks/pre-commit"}, repo) is not None, mode


def test_chmod_plus_x_is_ALLOWED_it_is_a_repair(repo):
    """There is no legitimate reason to chmod anything under `.git/hooks/`
    except RE-ADDING exec — refusing that would block the one remedy this
    gate's own refusal text recommends."""
    assert _decide("Bash", {"command": "chmod +x .git/hooks/pre-commit"}, repo) is None


def test_chmod_numeric_with_exec_bit_is_ALLOWED(repo):
    for mode in ("0755", "700", "0750"):
        assert _decide("Bash", {"command": f"chmod {mode} .git/hooks/pre-commit"}, repo) is None, mode


def test_chmod_plus_x_on_the_tracked_source_is_allowed(repo):
    """`scripts/hooks/pre-commit` (the TRACKED source `.git/hooks/pre-commit`
    is symlinked from) is never under `.git/` at all — untouched by this
    gate regardless of mode."""
    assert _decide("Bash", {"command": "chmod +x scripts/hooks/pre-commit"}, repo) is None
    assert _decide("Bash", {"command": "chmod -x scripts/hooks/pre-commit"}, repo) is None


# ── `ln` is SOURCE-aware, the same way `chmod` is mode-aware ────────────

def test_ln_relinking_the_tracked_source_is_ALLOWED_the_installer_pattern(repo):
    """`ln -s scripts/hooks/pre-commit .git/hooks/pre-commit` is exactly
    what `scripts/hooks/install-hooks.sh` runs — pointing the hook AT the
    tracked source is the repair, not the disable. `bash_write_targets`
    treats `ln` as dest-only (correct — the source is a read) but is
    source-blind; this is the property this test pins."""
    assert _decide(
        "Bash", {"command": "ln -s scripts/hooks/pre-commit .git/hooks/pre-commit"}, repo,
    ) is None


def test_ln_relinking_to_an_untracked_source_is_refused(repo):
    """Anything OTHER than the tracked source (`/dev/null`, `/bin/true`, an
    attacker-planted script) is the real tampering shape."""
    assert _decide("Bash", {"command": "ln -sf /bin/true .git/hooks/pre-commit"}, repo) is not None
    assert _decide("Bash", {"command": "ln -sf /dev/null .git/hooks/pre-commit"}, repo) is not None


# ── the worktree property: resolve through gitdir: ──────────────────────

def test_relative_attack_from_the_worktree_targets_the_worktree_itself(linked_worktree):
    """`.git/hooks/pre-commit`, run from a WORKTREE, is not a real path at
    all (`.git` there is a FILE, not a directory) — `rm` would fail on the
    real filesystem with ENOTDIR, so there is nothing here to protect
    against; the resolved target simply never matches the real guarded
    region. Documented as a NEGATIVE case so the boundary is explicit."""
    assert _decide("Bash", {"command": "rm .git/hooks/pre-commit"}, linked_worktree) is None


def test_absolute_attack_from_the_worktree_against_the_PRIMARYs_real_hooks_is_refused(repo, linked_worktree):
    """🔴 THE property the tech-lead specifically verified: an agent sitting
    in a WORKTREE, using the correct ABSOLUTE path to the PRIMARY's real
    `.git/hooks/`, must still be caught — `git rev-parse --git-common-dir`
    resolves through the worktree's `gitdir:` indirection regardless of
    which cwd the probe runs from, so `common` here is the SAME primary
    `.git` whether this call originates in `repo` or in `linked_worktree`."""
    target = str(repo / ".git" / "hooks" / "pre-commit")
    assert _decide("Bash", {"command": f"rm {target}"}, linked_worktree) is not None
    assert _decide("Edit", {"file_path": target}, linked_worktree) is not None
    assert _decide(
        "Bash", {"command": f"chmod -x {repo / '.git' / 'hooks' / 'pre-push'}"}, linked_worktree,
    ) is not None


def test_absolute_repair_chmod_from_the_worktree_is_still_allowed(repo, linked_worktree):
    target = str(repo / ".git" / "hooks" / "pre-push")
    assert _decide("Bash", {"command": f"chmod +x {target}"}, linked_worktree) is None


# ── legitimate `.git/`-adjacent operations that MUST keep working ───────

def test_worktree_add_is_allowed(repo):
    assert _decide("Bash", {"command": "git worktree add -q ../other feat/y"}, repo) is None


def test_worktree_remove_is_allowed(repo):
    assert _decide("Bash", {"command": "git worktree remove ../other"}, repo) is None


def test_ledger_only_commit_is_allowed(repo):
    assert _decide(
        "Bash",
        {"command": "git add project-history/branch-tree.ndjson && git commit -m x"},
        repo,
    ) is None


def test_git_gc_is_allowed(repo):
    assert _decide("Bash", {"command": "git gc"}, repo) is None


def test_reset_hard_to_remote_is_allowed(repo):
    assert _decide("Bash", {"command": "git reset --hard origin/dev"}, repo) is None


def test_removing_an_unrelated_worktree_directory_is_allowed(repo):
    assert _decide("Bash", {"command": "rm -rf .claude/worktrees/some-slug"}, repo) is None


def test_a_plain_git_config_read_is_allowed(repo):
    assert _decide("Bash", {"command": "git config core.hooksPath"}, repo) is None


# ── not a git repo at all: cannot see, must not block ────────────────────

def test_outside_any_git_repo_is_allowed(tmp_path):
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    assert _decide("Bash", {"command": "rm .git/hooks/pre-commit"}, outside) is None


# ── the escape hatch ─────────────────────────────────────────────────────

def test_allow_override_true_permits_the_incident(repo):
    verdict = decide_hook_integrity(
        "Bash", {"command": "rm .git/hooks/pre-commit"}, cwd=str(repo), allow_override=True,
    )
    assert verdict is None


def test_escape_hatch_is_the_SAME_env_var_as_decide_git_bypass():
    """Deliberate — this is the SAME category of bypass (disabling a hook),
    just aimed at the file instead of the git invocation; a second env var
    would only fragment the one documented override path."""
    assert HOOK_BYPASS_ALLOW_ENV == "NOCTUS_ALLOW_HOOK_BYPASS"


class TestDecideHookIntegrity:
    """Named `Test<CamelCase(function)>` so a future `check_detector_has_
    regression_test`-style sibling for runtime-guard functions (should one
    ever be added) finds this file. The free functions above already pin
    the detailed shapes; this class is a composition anchor."""

    def test_the_incident_class_is_caught(self, repo):
        assert decide_hook_integrity(
            "Bash", {"command": "rm .git/hooks/pre-commit"}, cwd=str(repo),
        ) is not None

    def test_a_clean_command_is_allowed(self, repo):
        assert decide_hook_integrity(
            "Bash", {"command": "git status"}, cwd=str(repo),
        ) is None
