"""Regression tests for `check_piped_exit_code_pattern` — the
verdict-channel-integrity keeper (KB § PATTERNS/common/
methodology-execution-discipline.md § 6). See that keeper's docstring in
`tools/noctus/dev/compliance.py` for the two 2026-09-17 incidents that
motivated it.

Covers the 3 flaggable shapes (`$?` after a bare pipe; a pipe-into-filter
used as an if/&&/|| condition; missing pipefail alongside either), the
git-hook (extensionless) surface, the `.github/workflows/*.yml` `run:`-step
surface (including the GitHub-Actions-defaults-bash-to-pipefail carve-out),
the `noctusai-keeper: allow-piped-exit-code` opt-out, and the negative case
— a correctly-written `rc=$?` capture after a NON-piped command must never
be flagged.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_piped_exit_code_pattern,
    _scan_shell_text_for_piped_exit_code,
)


def _write_sh(tmp_path: Path, name: str, body: str) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    p = scripts / name
    p.write_text(body)
    return p


class TestPipedExitCodePattern:
    # ── shape 1: $? read after a bare pipe ──────────────────────────

    def test_shape1_next_line_dollar_question_flagged(self, tmp_path):
        _write_sh(tmp_path, "a.sh", (
            "#!/usr/bin/env bash\n"
            "set -e\n"
            "cmd | tail\n"
            "echo $?\n"
        ))
        issues = check_piped_exit_code_pattern(tmp_path)
        shape1 = [i for i in issues if "reads `$?` off a PIPELINE" in i["issue"]]
        assert len(shape1) == 1
        assert "line 4" in shape1[0]["issue"]
        assert shape1[0]["severity"] == "high"  # no pipefail in this script

    def test_shape1_same_line_dollar_question_flagged(self, tmp_path):
        _write_sh(tmp_path, "b.sh", (
            "#!/usr/bin/env bash\n"
            'npx tsc --noEmit 2>&1 | tail -5 && echo "tsc-rc=$?"\n'
        ))
        issues = check_piped_exit_code_pattern(tmp_path)
        shape1 = [i for i in issues if "reads `$?` off a PIPELINE" in i["issue"]]
        assert any("line 2" in i["issue"] for i in shape1)

    # ── shape 2: pipe-into-filter used as an if/&&/|| condition ────

    def test_shape2_if_pipe_tail_then_flagged(self, tmp_path):
        _write_sh(tmp_path, "c.sh", (
            "#!/usr/bin/env bash\n"
            'if git merge --no-edit -q "$b" 2>&1 | tail -1; then\n'
            "    echo MERGED\n"
            "else\n"
            "    echo CONFLICT\n"
            "fi\n"
        ))
        issues = check_piped_exit_code_pattern(tmp_path)
        shape2 = [i for i in issues if "directly as an if/&&/|| condition" in i["issue"]]
        assert len(shape2) == 1
        assert "line 2" in shape2[0]["issue"]

    def test_shape2_pipe_grep_q_double_pipe_flagged(self, tmp_path):
        _write_sh(tmp_path, "d.sh", (
            "#!/usr/bin/env bash\n"
            'cmd | grep -q pattern || echo "not found"\n'
        ))
        issues = check_piped_exit_code_pattern(tmp_path)
        shape2 = [i for i in issues if "directly as an if/&&/|| condition" in i["issue"]]
        assert len(shape2) == 1

    def test_bare_grep_no_leading_pipe_not_flagged_as_shape2(self, tmp_path):
        _write_sh(tmp_path, "e.sh", (
            "#!/usr/bin/env bash\n"
            'if grep -q "foo" file.txt; then\n'
            "    echo yes\n"
            "fi\n"
        ))
        issues = check_piped_exit_code_pattern(tmp_path)
        shape2 = [i for i in issues if "directly as an if/&&/|| condition" in i["issue"]]
        assert shape2 == []

    # ── shape 3: missing pipefail alongside shape 1 or 2 ────────────

    def test_shape3_missing_pipefail_flagged_and_severity_escalates(self, tmp_path):
        body = (
            "#!/usr/bin/env bash\n"
            "cmd | tail\n"
            "echo $?\n"
        )
        _write_sh(tmp_path, "no_pipefail.sh", body)
        issues = check_piped_exit_code_pattern(tmp_path)
        missing = [i for i in issues if "no effective pipefail" in i["issue"]]
        assert len(missing) == 1
        assert missing[0]["severity"] == "high"
        shape1 = [i for i in issues if "reads `$?` off a PIPELINE" in i["issue"]]
        assert shape1[0]["severity"] == "high"

    def test_shape3_absent_when_pipefail_present_severity_downgrades(self, tmp_path):
        body = (
            "#!/usr/bin/env bash\n"
            "set -o pipefail\n"
            "cmd | tail\n"
            "echo $?\n"
        )
        _write_sh(tmp_path, "with_pipefail.sh", body)
        issues = check_piped_exit_code_pattern(tmp_path)
        missing = [i for i in issues if "no effective pipefail" in i["issue"]]
        assert missing == [], "pipefail is present — the missing-pipefail finding must not fire"
        shape1 = [i for i in issues if "reads `$?` off a PIPELINE" in i["issue"]]
        assert len(shape1) == 1
        assert shape1[0]["severity"] == "warning"  # technically correct, still fragile

    # ── negative case: a correctly-written rc=$? capture ────────────

    def test_non_piped_rc_capture_never_flagged(self, tmp_path):
        _write_sh(tmp_path, "clean.sh", (
            "#!/usr/bin/env bash\n"
            "set -o pipefail\n"
            "cmd > /tmp/out 2>&1\n"
            "rc=$?\n"
            "echo \"rc=$rc\"\n"
        ))
        issues = check_piped_exit_code_pattern(tmp_path)
        assert issues == [], f"a non-piped rc=$? capture must never be flagged, got: {issues}"

    def test_no_pipe_no_dollar_question_clean_script(self, tmp_path):
        _write_sh(tmp_path, "quiet.sh", (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "echo hello\n"
        ))
        assert check_piped_exit_code_pattern(tmp_path) == []

    # ── opt-out marker ────────────────────────────────────────────

    def test_allow_marker_suppresses_finding(self, tmp_path):
        _write_sh(tmp_path, "suppressed.sh", (
            "#!/usr/bin/env bash\n"
            'if cmd | tail -1; then echo ok; fi  '
            "# noctusai-keeper: allow-piped-exit-code\n"
        ))
        assert check_piped_exit_code_pattern(tmp_path) == []

    # ── git-hook surface (extensionless) ────────────────────────────

    def test_extensionless_git_hook_scanned(self, tmp_path):
        hooks = tmp_path / "scripts" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "pre-commit").write_text(
            "#!/usr/bin/env bash\ncmd | tail\necho $?\n"
        )
        issues = check_piped_exit_code_pattern(tmp_path)
        assert any("scripts/hooks/pre-commit" in i["file"] for i in issues)

    def test_python_hook_not_treated_as_shell(self, tmp_path):
        hooks = tmp_path / "scripts" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "claude-guard-primary-write").write_text(
            "#!/usr/bin/env python3\nprint('cmd | tail')\n"
        )
        assert check_piped_exit_code_pattern(tmp_path) == []

    # ── .github/workflows/*.yml `run:` steps ────────────────────────

    def test_workflow_bash_step_flagged_as_warning_not_high(self, tmp_path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "test.yml").write_text(
            "name: CI\n"
            "on: [push]\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: run it\n"
            "        run: |\n"
            "          cmd | tail\n"
            "          echo $?\n"
        )
        issues = check_piped_exit_code_pattern(tmp_path)
        shape1 = [i for i in issues if "reads `$?` off a PIPELINE" in i["issue"]]
        assert len(shape1) == 1
        # bash is GHA's default shell -> pipefail is effectively active ->
        # warning, not high; and no missing-pipefail finding at all.
        assert shape1[0]["severity"] == "warning"
        missing = [i for i in issues if "no effective pipefail" in i["issue"]]
        assert missing == []

    def test_workflow_sh_shell_step_has_no_default_pipefail(self, tmp_path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "test.yml").write_text(
            "name: CI\n"
            "on: [push]\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: run it\n"
            "        shell: sh\n"
            "        run: |\n"
            "          cmd | tail\n"
            "          echo $?\n"
        )
        issues = check_piped_exit_code_pattern(tmp_path)
        shape1 = [i for i in issues if "reads `$?` off a PIPELINE" in i["issue"]]
        assert shape1[0]["severity"] == "high"
        missing = [i for i in issues if "no effective pipefail" in i["issue"]]
        assert len(missing) == 1

    def test_workflow_custom_shell_template_without_pipefail_treated_as_missing(self, tmp_path):
        """`shell: bash -e {0}` is a CUSTOM template GitHub Actions runs
        VERBATIM — it does NOT get `-o pipefail` auto-appended just
        because the template happens to start with `bash` (unlike the
        bare recognized keyword `shell: bash`)."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "test.yml").write_text(
            "name: CI\n"
            "on: [push]\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: run it\n"
            "        shell: 'bash -e {0}'\n"
            "        run: |\n"
            "          cmd | tail\n"
            "          echo $?\n"
        )
        issues = check_piped_exit_code_pattern(tmp_path)
        shape1 = [i for i in issues if "reads `$?` off a PIPELINE" in i["issue"]]
        assert shape1[0]["severity"] == "high"

    def test_workflow_non_run_steps_ignored(self, tmp_path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "test.yml").write_text(
            "name: CI\n"
            "on: [push]\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v7\n"
        )
        assert check_piped_exit_code_pattern(tmp_path) == []

    # ── empty / absent tree ───────────────────────────────────────

    def test_missing_root_returns_empty(self, tmp_path):
        assert check_piped_exit_code_pattern(tmp_path / "does-not-exist") == []

    def test_no_scripts_dir_returns_empty(self, tmp_path):
        assert check_piped_exit_code_pattern(tmp_path) == []


class TestScanShellTextForPipedExitCode:
    """Unit tests for the line-scanner in isolation (no filesystem)."""

    def test_blank_and_comment_lines_do_not_reset_state(self):
        text = "cmd | tail\n\n# a comment\necho $?\n"
        hits = _scan_shell_text_for_piped_exit_code(text)
        assert hits["shape1"] == [4]

    def test_rename_shape_irrelevant_here_but_pipe_then_dollar_same_line(self):
        hits = _scan_shell_text_for_piped_exit_code('cmd | tail; echo "$?"\n')
        assert hits["shape1"] == [1]

    def test_double_pipe_is_not_a_bare_pipe(self):
        hits = _scan_shell_text_for_piped_exit_code("cmd1 || cmd2\necho $?\n")
        assert hits["shape1"] == []
