"""Regression tests for `check_git_hook_file_tampering` — the STATIC backstop
for `primary_write_guard.decide_hook_integrity` (tested separately in
`test_hook_integrity_guard.py`).

WHY A SEPARATE KEEPER FROM `check_git_hooks_bypass`
──────────────────────────────────────────────────────
`check_git_hooks_bypass`'s predicate is git-ARGV-shaped (`-c core.hooksPath=
…`, `--no-verify`, …). A tracked `rm .git/hooks/pre-commit` or `chmod -x
.git/hooks/pre-commit` is not a `git` invocation at all — invisible to that
predicate — yet disables a hook exactly as effectively. This keeper scans
for THAT shape: a plain filesystem operation on the hook FILES.

WHY THE TESTS WRITE TO A TEMP DIR
───────────────────────────────────
Same reasoning as `test_git_hooks_bypass_detector.py`: the forbidden state
(a tracked file that disables a hook) must never be created for real inside
THIS repo. Every test points `repo_root=`/`paths=` at a throwaway directory.

KB § PATTERNS/common/bypass-rationalization-anti-patterns.md § 2.7
"""
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_git_hook_file_tampering  # noqa: E402


@pytest.fixture
def scratch(tmp_path):
    return tmp_path


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")


def _check(root: Path, rel: str):
    return check_git_hook_file_tampering(repo_root=root, paths=[rel])


# ── shell surfaces ───────────────────────────────────────────────────────

def test_rm_on_a_hook_file_is_flagged(scratch):
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        rm .git/hooks/pre-commit
        """)
    found = _check(scratch, "scripts/sneaky.sh")
    assert len(found) == 1
    assert found[0]["severity"] == "high"


def test_truncating_redirect_is_flagged(scratch):
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        > .git/hooks/pre-commit
        """)
    assert len(_check(scratch, "scripts/sneaky.sh")) == 1


def test_appending_write_to_git_config_is_flagged(scratch):
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        echo "hooksPath = /dev/null" >> .git/config
        """)
    assert len(_check(scratch, "scripts/sneaky.sh")) == 1


def test_cp_overwriting_a_hook_is_flagged(scratch):
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        cp evil.sh .git/hooks/pre-commit
        """)
    assert len(_check(scratch, "scripts/sneaky.sh")) == 1


def test_mv_overwriting_a_hook_is_flagged(scratch):
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        mv evil.sh .git/hooks/pre-commit
        """)
    assert len(_check(scratch, "scripts/sneaky.sh")) == 1


def test_chmod_dash_x_is_flagged(scratch):
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        chmod -x .git/hooks/pre-commit
        """)
    assert len(_check(scratch, "scripts/sneaky.sh")) == 1


def test_chmod_numeric_no_exec_is_flagged(scratch):
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        chmod 0644 .git/hooks/pre-commit
        """)
    assert len(_check(scratch, "scripts/sneaky.sh")) == 1


def test_chmod_plus_x_is_NOT_flagged_it_is_a_repair(scratch):
    _write(scratch, "scripts/repair.sh", """\
        #!/usr/bin/env bash
        chmod +x .git/hooks/pre-commit
        """)
    assert _check(scratch, "scripts/repair.sh") == []


def test_makefile_recipe_is_flagged(scratch):
    _write(scratch, "Makefile", """\
        disable-hooks:
        \trm .git/hooks/pre-commit
        """)
    assert len(_check(scratch, "Makefile")) == 1


def test_ci_workflow_run_step_is_flagged(scratch):
    _write(scratch, ".github/workflows/x.yml", """\
        name: x
        jobs:
          j:
            steps:
              - run: rm .git/hooks/pre-push
        """)
    assert len(_check(scratch, ".github/workflows/x.yml")) == 1


def test_extensionless_shebang_script_is_scanned(scratch):
    _write(scratch, "scripts/hooks/evil", """\
        #!/usr/bin/env bash
        chmod -x .git/hooks/pre-commit
        """)
    assert len(_check(scratch, "scripts/hooks/evil")) == 1


# ── python / subprocess surfaces ────────────────────────────────────────

def test_subprocess_run_rm_is_flagged(scratch):
    _write(scratch, "scripts/tool.py", """\
        import subprocess

        def sneaky():
            subprocess.run(["rm", ".git/hooks/pre-commit"])
        """)
    found = _check(scratch, "scripts/tool.py")
    assert len(found) == 1
    assert found[0]["file"].endswith(":4")


def test_subprocess_run_chmod_dash_x_is_flagged(scratch):
    _write(scratch, "scripts/tool.py", """\
        import subprocess

        def sneaky():
            subprocess.run(["chmod", "-x", ".git/hooks/pre-push"])
        """)
    assert len(_check(scratch, "scripts/tool.py")) == 1


def test_subprocess_run_chmod_plus_x_is_NOT_flagged(scratch):
    _write(scratch, "scripts/tool.py", """\
        import subprocess

        def repair():
            subprocess.run(["chmod", "+x", ".git/hooks/pre-commit"])
        """)
    assert _check(scratch, "scripts/tool.py") == []


def test_shell_true_redirect_to_git_config_is_flagged(scratch):
    _write(scratch, "scripts/tool.py", """\
        import subprocess

        def sneaky():
            subprocess.run("echo 'hooksPath = /dev/null' >> .git/config", shell=True)
        """)
    assert len(_check(scratch, "scripts/tool.py")) == 1


def test_dynamically_built_argv_is_not_flagged_unresolvable(scratch):
    _write(scratch, "scripts/tool.py", """\
        import subprocess

        def maybe_sneaky(target):
            subprocess.run(["rm", target])
        """)
    assert _check(scratch, "scripts/tool.py") == []


# ── the discriminator: declaration vs. citation ─────────────────────────

def test_a_comment_mentioning_the_shape_is_NOT_flagged(scratch):
    _write(scratch, "scripts/hooks/pre-push", """\
        #!/usr/bin/env bash
        # never: rm .git/hooks/pre-commit
        echo "gate ok"
        """)
    assert _check(scratch, "scripts/hooks/pre-push") == []


def test_an_echo_message_with_no_redirect_is_NOT_flagged(scratch):
    _write(scratch, "scripts/hooks/pre-push", """\
        #!/usr/bin/env bash
        echo "never rm .git/hooks/pre-commit directly" >&2
        """)
    assert _check(scratch, "scripts/hooks/pre-push") == []


def test_a_python_docstring_is_NOT_flagged(scratch):
    _write(scratch, "scripts/tool.py", '''\
        """Never rm .git/hooks/pre-commit directly."""

        def do_work():
            return 1
        ''')
    assert _check(scratch, "scripts/tool.py") == []


def test_a_markdown_file_is_never_scanned(scratch):
    _write(scratch, "docs/rule.md", """\
        - Never `rm .git/hooks/pre-commit` directly.
        """)
    assert _check(scratch, "docs/rule.md") == []


def test_an_archived_patch_is_never_scanned(scratch):
    _write(scratch, "project-history/foo.patch", """\
        +rm .git/hooks/pre-commit
        """)
    assert _check(scratch, "project-history/foo.patch") == []


# ── the co-located allowlist ─────────────────────────────────────────────

def test_install_hooks_sh_remove_then_recreate_is_allowlisted(scratch):
    """The sanctioned installer: removes the OLD symlink immediately before
    recreating it pointing at the tracked source. Net effect is a WORKING
    hook, not a disabled one."""
    _write(scratch, "scripts/hooks/install-hooks.sh", """\
        #!/usr/bin/env bash
        set -euo pipefail
        REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
        HOOKS_DIR="$REPO_ROOT/.git/hooks"
        rm -f "$HOOKS_DIR/pre-commit"
        ln -s "$REPO_ROOT/scripts/hooks/pre-commit" "$HOOKS_DIR/pre-commit"
        chmod +x "$REPO_ROOT/scripts/hooks/pre-commit"
        rm -f "$HOOKS_DIR/pre-push"
        ln -s "$REPO_ROOT/scripts/hooks/pre-push" "$HOOKS_DIR/pre-push"
        rm -f "$HOOKS_DIR/post-merge"
        ln -s "$REPO_ROOT/scripts/hooks/post-merge" "$HOOKS_DIR/post-merge"
        rm -f "$HOOKS_DIR/post-checkout"
        ln -s "$REPO_ROOT/scripts/hooks/post-checkout" "$HOOKS_DIR/post-checkout"
        """)
    assert _check(scratch, "scripts/hooks/install-hooks.sh") == []


def test_the_allowlist_is_path_scoped_not_content_scoped(scratch):
    """The SAME line, in a DIFFERENT file, is not exempt."""
    _write(scratch, "scripts/imposter.sh", """\
        #!/usr/bin/env bash
        HOOKS_DIR="$REPO_ROOT/.git/hooks"
        rm -f "$HOOKS_DIR/pre-commit"
        """)
    assert len(_check(scratch, "scripts/imposter.sh")) == 1


# ── legitimate ops that must stay allowed ────────────────────────────────

def test_a_clean_tracked_script_produces_no_findings(scratch):
    _write(scratch, "scripts/hello.sh", """\
        #!/usr/bin/env bash
        echo "hello"
        git status
        rm -rf .claude/worktrees/some-slug
        """)
    assert _check(scratch, "scripts/hello.sh") == []


def test_removing_the_tracked_source_hook_is_allowed(scratch):
    """`scripts/hooks/pre-commit` (the TRACKED source) is never under
    `.git/` — this keeper's job stops at the boundary `decide_hook_
    integrity` draws, not the tracked-repo scripts that manage it."""
    _write(scratch, "scripts/cleanup.sh", """\
        #!/usr/bin/env bash
        rm scripts/hooks/pre-commit
        """)
    assert _check(scratch, "scripts/cleanup.sh") == []


# ── the whole-repo sweep runs and finds nothing (drift regression) ─────

def test_the_real_repo_is_clean():
    root = Path(__file__).resolve().parents[3]
    found = check_git_hook_file_tampering(repo_root=root)
    assert found == [], found


class TestCheckGitHookFileTampering:
    """Named `Test<CamelCase>` so `check_detector_has_regression_test`
    (`KB § PATTERNS/compliance/testing.md § Regression-test-the-detector`)
    recognizes `check_git_hook_file_tampering` as covered."""

    def test_the_incident_shape_is_caught(self, tmp_path):
        _write(tmp_path, "scripts/x.sh", """\
            #!/usr/bin/env bash
            rm .git/hooks/pre-commit
            """)
        found = check_git_hook_file_tampering(repo_root=tmp_path, paths=["scripts/x.sh"])
        assert len(found) == 1
        assert found[0]["severity"] == "high"

    def test_a_clean_tree_is_silent(self, tmp_path):
        _write(tmp_path, "scripts/x.sh", "#!/usr/bin/env bash\necho hi\n")
        assert check_git_hook_file_tampering(repo_root=tmp_path, paths=["scripts/x.sh"]) == []
