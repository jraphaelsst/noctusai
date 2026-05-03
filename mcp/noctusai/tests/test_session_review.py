"""Tests for `mcp/noctusai/tools/session_review.py`.

Two layers:
1. **Pure-function detector tests** with hand-built `[ToolUse, ToolResult, …]`
   lists. No filesystem, no JSONL parsing — exercises the rule logic.
2. **Fixture-driven end-to-end tests** that round-trip through the adapter
   to confirm the detectors fire correctly when fed real JSONL bytes.

Per `KB § PATTERNS/testing.md § Regression-test-the-detector`, every keeper
detector ships colocated `Test<CamelCase>` regression coverage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from session_loader import ToolResult, ToolUse, load_session
from tools.noctus.dev.session_review import (
    SessionIssue,
    detect_ast_first,
    detect_narrow_read,
    review_session,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"


def _tu(line: int, name: str, **inputs) -> ToolUse:
    return ToolUse(line_no=line, id=f"toolu_{line:03d}", name=name, input=inputs)


def _tr(line: int, ref_line: int, *, content_size: int = 0, is_error: bool = False) -> ToolResult:
    return ToolResult(
        line_no=line,
        tool_use_id=f"toolu_{ref_line:03d}",
        content_size=content_size,
        is_error=is_error,
    )


class TestDetectAstFirst:
    def test_sed_inplace_then_edit_same_file_emits_warning(self):
        events = [
            _tu(1, "Bash", command="sed -i 's/x/y/' /repo/a.py"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/a.py", old_string="y", new_string="z", replace_all=False),
        ]
        issues = detect_ast_first(events)
        assert len(issues) == 1
        assert issues[0].rule == "ast-first"
        assert issues[0].severity == "WARNING"
        assert issues[0].target_path == "/repo/a.py"
        assert issues[0].tool_name == "Bash"

    def test_read_only_sed_n_does_not_flag(self):
        events = [
            _tu(1, "Bash", command="sed -n '1,40p' /repo/a.py"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/a.py", old_string="x", new_string="y", replace_all=False),
        ]
        assert detect_ast_first(events) == []

    def test_substitution_pattern_flags_even_without_dash_i(self):
        events = [
            _tu(1, "Bash", command="cat /repo/a.py | sed 's/foo/bar/' > /repo/a.py"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/a.py", old_string="bar", new_string="baz", replace_all=False),
        ]
        # `>` redirect to `.py` IS a mutation marker; should flag.
        assert len(detect_ast_first(events)) == 1

    def test_perl_pi_then_write_flags(self):
        events = [
            _tu(1, "Bash", command="perl -pi -e 's/foo/bar/' /repo/b.ts"),
            _tr(2, 1),
            _tu(3, "Write", file_path="/repo/b.ts", content="export const x = 1;\n"),
        ]
        assert len(detect_ast_first(events)) == 1

    def test_does_not_flag_edit_on_non_source_extension(self):
        events = [
            _tu(1, "Bash", command="sed -i 's/x/y/' /repo/notes.md"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/notes.md", old_string="y", new_string="z", replace_all=False),
        ]
        assert detect_ast_first(events) == []

    def test_does_not_flag_when_target_paths_differ(self):
        events = [
            _tu(1, "Bash", command="sed -i 's/x/y/' /repo/a.py"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/b.py", old_string="m", new_string="n", replace_all=False),
        ]
        assert detect_ast_first(events) == []

    def test_intervening_edit_resets_cursor(self):
        # If the agent already did an Edit between the Bash mutation and the
        # later Edit, the AST-first cursor is satisfied for the next Edit.
        events = [
            _tu(1, "Bash", command="sed -i 's/x/y/' /repo/a.py"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/a.py", old_string="y", new_string="z", replace_all=False),
            _tr(4, 3),
            _tu(5, "Edit", file_path="/repo/a.py", old_string="z", new_string="zz", replace_all=False),
        ]
        # Only one violation reported — for the FIRST Edit, not the second.
        issues = detect_ast_first(events)
        assert len(issues) == 1
        assert issues[0].jsonl_line == 1

    def test_handles_basename_only_path_in_command(self):
        # Agent might `cd` into the dir and reference the basename. Predicate
        # matches either form.
        events = [
            _tu(1, "Bash", command="cd /repo && sed -i 's/x/y/' a.py"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/a.py", old_string="y", new_string="z", replace_all=False),
        ]
        assert len(detect_ast_first(events)) == 1

    def test_redirect_to_non_source_does_not_flag(self):
        events = [
            _tu(1, "Bash", command="echo done > /repo/log.txt"),
            _tr(2, 1),
            _tu(3, "Edit", file_path="/repo/a.py", old_string="x", new_string="y", replace_all=False),
        ]
        assert detect_ast_first(events) == []

    def test_empty_event_list_no_issues(self):
        assert detect_ast_first([]) == []


def _make_big_file(path: Path, lines: int = 300) -> Path:
    path.write_text("\n".join(f"x = {i}" for i in range(lines)) + "\n", encoding="utf-8")
    return path


class TestDetectNarrowRead:
    """Uses the `repo_root=` DI seam on `detect_narrow_read` rather than
    monkey-patching the module global, per the no-monkey-patching rule."""

    def test_whole_file_read_of_large_repo_file_flags(self, tmp_path):
        big = _make_big_file(tmp_path / "big.py", 300)
        events = [_tu(1, "Read", file_path=str(big))]
        issues = detect_narrow_read(events, repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0].rule == "narrow-read"
        assert issues[0].severity == "INFO"
        assert "300 lines" in issues[0].message

    def test_outline_before_read_does_not_flag(self, tmp_path):
        big = _make_big_file(tmp_path / "big.py", 300)
        events = [
            _tu(1, "noctusai_outline_python", path=str(big)),
            _tu(2, "Read", file_path=str(big)),
        ]
        assert detect_narrow_read(events, repo_root=tmp_path) == []

    def test_read_with_offset_does_not_flag(self, tmp_path):
        big = _make_big_file(tmp_path / "big.py", 300)
        events = [_tu(1, "Read", file_path=str(big), offset=100, limit=50)]
        assert detect_narrow_read(events, repo_root=tmp_path) == []

    def test_small_file_not_flagged(self, tmp_path):
        small = _make_big_file(tmp_path / "small.py", 50)
        events = [_tu(1, "Read", file_path=str(small))]
        assert detect_narrow_read(events, repo_root=tmp_path) == []

    def test_outside_repo_path_not_flagged(self, tmp_path):
        outside = _make_big_file(tmp_path / "outside" / "big.py".replace("outside/", ""), 300) if False else None
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside = _make_big_file(outside_dir / "big.py", 300)
        repo = tmp_path / "repo"
        repo.mkdir()
        events = [_tu(1, "Read", file_path=str(outside))]
        assert detect_narrow_read(events, repo_root=repo) == []

    def test_missing_file_silently_skipped(self, tmp_path):
        events = [_tu(1, "Read", file_path=str(tmp_path / "ghost.py"))]
        assert detect_narrow_read(events, repo_root=tmp_path) == []

    def test_outline_typescript_alias_recognized(self, tmp_path):
        big = tmp_path / "big.tsx"
        big.write_text("\n".join(f"const x{i} = {i};" for i in range(300)) + "\n", encoding="utf-8")
        events = [
            _tu(1, "outline_typescript", file_path=str(big)),
            _tu(2, "Read", file_path=str(big)),
        ]
        assert detect_narrow_read(events, repo_root=tmp_path) == []

    def test_repo_root_kwarg_threads_through_review_session(self, tmp_path):
        # End-to-end check: review_session(repo_root=…) reaches the detector.
        big = _make_big_file(tmp_path / "big.py", 300)
        # Build a minimal in-memory JSONL that reads the big file.
        import json as _json
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(_json.dumps({
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": str(big)}}
            ]},
        }) + "\n", encoding="utf-8")
        result = review_session(path=jsonl, repo_root=tmp_path)
        assert any(i["rule"] == "narrow-read" for i in result["issues"])


class TestFixturesEndToEnd:
    """Round-trip through the adapter to confirm the detector still fires
    when fed real JSONL bytes (not just Event lists in memory)."""

    def test_ast_first_violation_fixture(self):
        events = load_session(FIXTURES / "ast_first_violation.jsonl")
        issues = detect_ast_first(events)
        assert len(issues) == 1
        assert issues[0].rule == "ast-first"
        assert issues[0].target_path.endswith("main.py")

    def test_ast_first_clean_fixture(self):
        events = load_session(FIXTURES / "ast_first_clean.jsonl")
        assert detect_ast_first(events) == []

    def test_ast_first_mixed_fixture(self):
        events = load_session(FIXTURES / "ast_first_mixed.jsonl")
        issues = detect_ast_first(events)
        # Two violations: a.py (sed -i + Edit) + b.ts (perl -pi + Write).
        # The redirect-to-log.txt does NOT flag (extension filter).
        assert len(issues) == 2
        flagged = sorted(i.target_path for i in issues)
        assert any(p.endswith("a.py") for p in flagged)
        assert any(p.endswith("b.ts") for p in flagged)

    def test_narrow_read_violation_fixture(self, tmp_path):
        # Narrow-read fixtures use `__BIG_FILE__` placeholder so tests can
        # substitute a real >200-line file path at runtime.
        big = _make_big_file(tmp_path / "big.py", 300)
        raw = (FIXTURES / "narrow_read_violation.jsonl").read_text()
        rendered = tmp_path / "session.jsonl"
        rendered.write_text(raw.replace("__BIG_FILE__", str(big)), encoding="utf-8")
        events = load_session(rendered)
        issues = detect_narrow_read(events, repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0].rule == "narrow-read"

    def test_narrow_read_clean_fixture(self, tmp_path):
        big = _make_big_file(tmp_path / "big.py", 300)
        raw = (FIXTURES / "narrow_read_clean.jsonl").read_text()
        rendered = tmp_path / "session.jsonl"
        rendered.write_text(raw.replace("__BIG_FILE__", str(big)), encoding="utf-8")
        events = load_session(rendered)
        assert detect_narrow_read(events, repo_root=tmp_path) == []


class TestReviewSession:
    def test_explicit_path_runs_both_detectors(self):
        result = review_session(path=FIXTURES / "ast_first_violation.jsonl")
        assert result["event_count"] > 0
        assert "ast-first" in result["detectors_run"]
        assert "narrow-read" in result["detectors_run"]
        assert any(i["rule"] == "ast-first" for i in result["issues"])

    def test_clean_fixture_zero_issues(self):
        result = review_session(path=FIXTURES / "ast_first_clean.jsonl")
        assert result["issues_found"] == 0

    def test_requires_path_or_latest(self):
        with pytest.raises(ValueError) as exc:
            review_session()
        assert "path" in str(exc.value).lower() or "latest" in str(exc.value).lower()

    def test_issues_sorted_by_jsonl_line(self):
        result = review_session(path=FIXTURES / "ast_first_mixed.jsonl")
        lines = [i["jsonl_line"] for i in result["issues"]]
        assert lines == sorted(lines)

    def test_session_issue_dataclass_serializes_clean(self):
        # Ensures the asdict() output the orchestrator emits is JSON-safe.
        from dataclasses import asdict
        i = SessionIssue(
            rule="ast-first",
            severity="WARNING",
            message="m",
            suggestion="s",
            jsonl_line=1,
            tool_name="Bash",
            target_path="/x.py",
        )
        d = asdict(i)
        import json
        json.dumps(d)
