"""Regression test for the `check_stranded_branches` detector.

🔴 WHAT THIS PINS (2026-09-19)
------------------------------
Four branches sat unintegrated for 3 days–3 weeks and every one conflicted by
the time anyone looked. The expensive part was not the merging — it was the
archaeology:

* two of them (`matricula-ruido-seed`, `contract-f6-termos-fe`) carried NOTHING:
  their content was already on `dev`, patch-equivalent or byte-identical. They
  still looked like pending work to every naive `ahead > 0` check.
* one (`abnt-formatting-contract`) carried 5 real commits whose approach had
  been SUPERSEDED the next day by a production incident fix. Merging it on
  autopilot would have reverted that fix.

So the detector must count commits by PATCH-EQUIVALENCE (`git cherry`), never by
`rev-list` distance — otherwise it cries wolf on leftovers and trains people to
ignore it, which is how the real one hides.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.noctus.dev.compliance import check_stranded_branches  # noqa: E402

OLD = "1600000000"   # 2020 — far past any threshold
NEW = "99999999999"  # far future — never stale


def _fake_git(refs: dict[str, tuple[str, str]]):
    """refs: {ref: (cherry_output, committer_timestamp)}."""
    def run(args: list[str]) -> tuple[int, str, str]:
        if args[1] == "for-each-ref":
            return 0, "\n".join(refs) + "\n", ""
        if args[1] == "cherry":
            return 0, refs.get(args[3], ("", OLD))[0], ""
        if args[1] == "log":
            return 0, refs.get(args[-1], ("", OLD))[1], ""
        return 1, "", "unexpected"
    return run


class TestStrandedBranches:
    def test_flags_an_old_branch_with_real_unmerged_commits(self, tmp_path):
        run = _fake_git({"origin/feat/x": ("+ abc123\n+ def456\n", OLD)})
        issues = check_stranded_branches(repo_root=tmp_path, run=run)
        assert len(issues) == 1
        assert "2 commit(s) not on `dev`" in issues[0]["issue"]

    def test_ignores_a_branch_whose_work_already_landed(self, tmp_path):
        """The leftover shape: `git cherry` says every commit is upstream."""
        run = _fake_git({"origin/feat/leftover": ("- abc123\n- def456\n", OLD)})
        assert check_stranded_branches(repo_root=tmp_path, run=run) == []

    def test_ignores_a_recent_branch(self, tmp_path):
        """A young branch with unmerged work is normal in-flight work."""
        run = _fake_git({"origin/feat/fresh": ("+ abc123\n", NEW)})
        assert check_stranded_branches(repo_root=tmp_path, run=run) == []

    def test_never_flags_dependabot_or_release_refs(self, tmp_path):
        run = _fake_git({
            "origin/dependabot/npm_and_yarn/x": ("+ abc\n", OLD),
            "origin/backup/old-thing": ("+ abc\n", OLD),
            "origin/dev": ("+ abc\n", OLD),
            "origin/main": ("+ abc\n", OLD),
            "origin/prod": ("+ abc\n", OLD),
        })
        assert check_stranded_branches(repo_root=tmp_path, run=run) == []

    def test_a_check_that_cannot_run_is_not_a_pass(self, tmp_path):
        """No silent errors: an unusable git must report, never return clean."""
        def broken(args):
            return 1, "", "fatal: not a git repository"
        issues = check_stranded_branches(repo_root=tmp_path, run=broken)
        assert len(issues) == 1
        assert "could not run" in issues[0]["issue"]
