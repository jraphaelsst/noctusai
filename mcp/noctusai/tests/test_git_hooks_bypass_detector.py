"""Regression tests for `check_git_hooks_bypass` — the STATIC backstop for
`primary_write_guard.decide_git_bypass` (tested separately in
`test_git_bypass_guard.py`).

WHY A SEPARATE, STATIC GATE EXISTS
────────────────────────────────────
`decide_git_bypass` refuses the bypass shape at WRITE time, for a Bash
command actually run through the harness. It cannot see a bypass typed once
into a helper script, a Makefile recipe, a CI workflow step, or a
`subprocess.run(...)` call and then invoked indirectly (`bash scripts/foo.sh`)
— the runtime gate only parses the literal command TEXT handed to the tool,
and a script invocation is opaque to it by design. This keeper scans the
FILES instead.

WHY THE TESTS WRITE TO A TEMP DIR
───────────────────────────────────
The forbidden state is "a tracked file hardcodes a hooks bypass" — a test
must never create that for real inside THIS repo (it would trip the very
keeper under test, and pre-commit, on save). Every test builds a throwaway
directory and points `repo_root=`/`paths=` at it directly, mirroring
`test_conflict_markers_detector.py`'s own approach to the same problem.

KB § PATTERNS/common/bypass-rationalization-anti-patterns.md ·
KB § PATTERNS/common/gate-methodology-sync.md
"""
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_git_hooks_bypass  # noqa: E402


@pytest.fixture
def scratch(tmp_path):
    return tmp_path


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")


def _check(root: Path, rel: str):
    return check_git_hooks_bypass(repo_root=root, paths=[rel])


# ── the incident, verbatim, hardcoded in a script ───────────────────────────

def test_THE_incident_command_in_a_shell_script_is_flagged(scratch):
    """🔴 THE incident, hardcoded into a tracked script. If this stops
    failing, the static backstop is blind to the exact shape that started
    this gate."""
    _write(scratch, "scripts/sneaky.sh", """\
        #!/usr/bin/env bash
        git -c core.hooksPath=.git/hooks commit -q -F - <<'MSG'
        some message
        MSG
        """)
    found = _check(scratch, "scripts/sneaky.sh")
    assert len(found) == 1
    assert "scripts/sneaky.sh" in found[0]["file"]
    assert "core.hooksPath" in found[0]["issue"]


# ── shell / Makefile surfaces ───────────────────────────────────────────────

def test_no_verify_in_a_dot_sh_script_is_flagged(scratch):
    _write(scratch, "scripts/deploy.sh", """\
        #!/usr/bin/env bash
        git commit -m "auto" --no-verify
        """)
    assert len(_check(scratch, "scripts/deploy.sh")) == 1


def test_no_verify_in_a_makefile_recipe_is_flagged(scratch):
    _write(scratch, "Makefile", """\
        release:
        \tgit push --no-verify origin main
        """)
    assert len(_check(scratch, "Makefile")) == 1


def test_extensionless_shebang_hook_script_is_scanned(scratch):
    """`scripts/hooks/pre-commit`/`pre-push` carry no extension — recognized
    by their own shebang, not a hardcoded filename allowlist."""
    _write(scratch, "scripts/hooks/pre-commit", """\
        #!/usr/bin/env bash
        git -c core.hooksPath=/dev/null commit -m x
        """)
    assert len(_check(scratch, "scripts/hooks/pre-commit")) == 1


def test_ci_workflow_run_step_is_flagged(scratch):
    _write(scratch, ".github/workflows/deploy.yml", """\
        name: deploy
        jobs:
          ship:
            steps:
              - run: git push --no-verify origin main
        """)
    assert len(_check(scratch, ".github/workflows/deploy.yml")) == 1


# ── python / subprocess surfaces ────────────────────────────────────────────

def test_subprocess_run_list_form_is_flagged(scratch):
    _write(scratch, "scripts/tool.py", """\
        import subprocess

        def sneaky():
            subprocess.run(["git", "commit", "--no-verify", "-m", "x"])
        """)
    found = _check(scratch, "scripts/tool.py")
    assert len(found) == 1
    assert found[0]["file"].endswith(":4")


def test_os_system_string_form_is_flagged(scratch):
    _write(scratch, "scripts/tool.py", """\
        import os

        def sneaky():
            os.system("git -c core.hooksPath=/dev/null commit -m x")
        """)
    assert len(_check(scratch, "scripts/tool.py")) == 1


def test_dynamically_built_argv_is_not_flagged_unresolvable(scratch):
    """A variable/function-built argv escapes static analysis by
    construction — same posture as the runtime gate's `_is_unresolvable`. Not
    a hole this keeper claims to close; the PreToolUse gate still catches the
    LIVE invocation regardless of how the argv was assembled."""
    _write(scratch, "scripts/tool.py", """\
        import subprocess

        def maybe_sneaky(extra_flags):
            subprocess.run(["git", "commit"] + extra_flags)
        """)
    assert _check(scratch, "scripts/tool.py") == []


# ── the discriminator: declaration vs. citation ─────────────────────────────

def test_a_shell_comment_mentioning_no_verify_is_NOT_flagged(scratch):
    _write(scratch, "scripts/hooks/pre-push", """\
        #!/usr/bin/env bash
        # Hard bypass (rare): git push --no-verify
        echo "gate ok"
        """)
    assert _check(scratch, "scripts/hooks/pre-push") == []


def test_an_echo_message_about_no_verify_is_NOT_flagged(scratch):
    _write(scratch, "scripts/hooks/pre-push", """\
        #!/usr/bin/env bash
        echo "   If truly intended, re-run with: git push --no-verify" >&2
        """)
    assert _check(scratch, "scripts/hooks/pre-push") == []


def test_a_python_docstring_mentioning_no_verify_is_NOT_flagged(scratch):
    _write(scratch, "scripts/tool.py", """\
        \"\"\"NEVER `--no-verify`. If a hook fails, surface it instead.\"\"\"

        def do_work():
            return 1
        """)
    assert _check(scratch, "scripts/tool.py") == []


def test_a_test_assertion_comparing_generated_text_is_NOT_flagged(scratch):
    """Mirrors `mcp/noctusai/tests/test_surface_and_resume.py:419` —
    `assert "NEVER \\`--no-verify\\`" in brief` checks that some OTHER
    function emits the string; it never spawns a process."""
    _write(scratch, "scripts/tool_test.py", '''\
        def test_brief_carries_the_safety_language():
            brief = compose_brief()
            assert "NEVER `--no-verify`" in brief
        ''')
    assert _check(scratch, "scripts/tool_test.py") == []


def test_a_python_list_constant_with_trailing_comment_is_NOT_flagged(scratch):
    """Mirrors `compliance.py`'s own `_DEFINING_DOCS`-style tuple: the
    string VALUE is a path, the `--no-verify` mention is a TRAILING comment
    (outside any process-spawning call)."""
    _write(scratch, "scripts/tool.py", """\
        DOCS = (
            "CONTEXT/PATTERNS/common/bypass-rationalization-anti-patterns.md",  # closes the --no-verify loophole
        )
        """)
    assert _check(scratch, "scripts/tool.py") == []


def test_a_markdown_file_is_never_scanned_prose_cannot_execute(scratch):
    _write(scratch, "docs/rule.md", """\
        - **NEVER `--no-verify`** on `git commit` or `git push`.
        - `git -c core.hooksPath=/dev/null commit -m x` is the incident shape.
        """)
    assert _check(scratch, "docs/rule.md") == []


def test_an_archived_patch_is_never_scanned_frozen_history(scratch):
    _write(scratch, "project-history/foo.patch", """\
        +git commit --no-verify -m "old work, committed with --no-verify"
        """)
    assert _check(scratch, "project-history/foo.patch") == []


def test_an_ndjson_event_log_is_never_scanned(scratch):
    _write(scratch, "project-history/auto-improvement.ndjson", """\
        {"description": "agent used git commit --no-verify with a bad rationalization"}
        """)
    assert _check(scratch, "project-history/auto-improvement.ndjson") == []


# ── the co-located allowlist ─────────────────────────────────────────────

def test_bootstrap_seed_workspace_hookspath_set_is_allowlisted(scratch):
    """Provisions a BRAND-NEW, separate sibling repo — enables ITS OWN real
    hooks, never touches this repo's config. See `_HOOKS_BYPASS_ALLOWLIST`."""
    _write(scratch, "scripts/bootstrap/bootstrap-seed-workspace.sh", """\
        #!/usr/bin/env bash
        echo "==> git init"
        (cd "$TARGET" && git init -q)
        echo "==> git config core.hooksPath .githooks"
        (cd "$TARGET" && git config core.hooksPath .githooks)
        """)
    assert _check(scratch, "scripts/bootstrap/bootstrap-seed-workspace.sh") == []


def test_the_allowlist_is_path_scoped_not_content_scoped(scratch):
    """The SAME line, in a DIFFERENT file, is not exempt — the allowlist
    names an exact (path, substring) pair, never a bare content match. A
    genuinely new bypass elsewhere must never accidentally inherit someone
    else's rationale."""
    _write(scratch, "scripts/imposter.sh", """\
        #!/usr/bin/env bash
        (cd "$TARGET" && git config core.hooksPath .githooks)
        """)
    assert len(_check(scratch, "scripts/imposter.sh")) == 1


# ── real ALLOW cases the module itself carries ──────────────────────────

def test_git_config_hookspath_read_alone_is_NOT_flagged(scratch):
    _write(scratch, "scripts/diag.sh", """\
        #!/usr/bin/env bash
        echo "current hooksPath:"
        git config core.hooksPath
        """)
    assert _check(scratch, "scripts/diag.sh") == []


def test_an_unrelated_dash_c_flag_is_NOT_flagged(scratch):
    _write(scratch, "scripts/setup.sh", """\
        #!/usr/bin/env bash
        git -c user.name=CI -c user.email=ci@example.com commit -m "automated"
        """)
    assert _check(scratch, "scripts/setup.sh") == []


def test_a_clean_tracked_script_produces_no_findings(scratch):
    _write(scratch, "scripts/hello.sh", """\
        #!/usr/bin/env bash
        echo "hello"
        git status
        """)
    assert _check(scratch, "scripts/hello.sh") == []


# ── the whole-repo sweep runs and finds nothing (drift regression) ─────────

def test_the_real_repo_is_clean():
    """The actual noc tree, scanned for real. If this starts failing without
    a deliberate new violation, something regressed the discriminator (a
    prose mention started reading as a declaration) rather than the tree
    having grown a genuine bypass."""
    root = Path(__file__).resolve().parents[3]
    found = check_git_hooks_bypass(repo_root=root)
    assert found == [], found


class TestCheckGitHooksBypass:
    """Named `Test<CamelCase(detector)>` so `check_detector_has_regression_test`
    (`KB § PATTERNS/compliance/testing.md § Regression-test-the-detector`)
    recognizes `check_git_hooks_bypass` as covered. The free functions above
    already pin the detailed true-/false-positive shapes; this class is the
    composition anchor the platform-wide keeper-coverage gate scans for."""

    def test_the_incident_shape_is_caught(self, tmp_path):
        _write(tmp_path, "scripts/x.sh", """\
            #!/usr/bin/env bash
            git -c core.hooksPath=/dev/null commit -m x
            """)
        found = check_git_hooks_bypass(repo_root=tmp_path, paths=["scripts/x.sh"])
        assert len(found) == 1
        assert found[0]["severity"] == "high"

    def test_a_clean_tree_is_silent(self, tmp_path):
        _write(tmp_path, "scripts/x.sh", "#!/usr/bin/env bash\necho hi\n")
        assert check_git_hooks_bypass(repo_root=tmp_path, paths=["scripts/x.sh"]) == []
