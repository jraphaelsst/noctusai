"""Regression tests for `check_contextualize_alignment` — the fresh-agent
read-map pointer-only discipline (sibling of `check_claude_md_router`).

KB § PATTERNS/common/claude-md-router-discipline.md. Phase B (2026-05-26).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_contextualize_alignment,
    _CONTEXTUALIZE_CANONICAL_CORES,
    _CONTEXTUALIZE_LINE_CAP,
)


def _write(root: Path, body: str) -> None:
    (root / "CONTEXTUALIZE.md").write_text(body, encoding="utf-8")


def _valid_body() -> str:
    """A minimal valid body that references every canonical core."""
    lines = ["# CONTEXTUALIZE.md (test fixture)", ""]
    for ref in _CONTEXTUALIZE_CANONICAL_CORES:
        lines.append(f"- pointer → {ref}")
    return "\n".join(lines) + "\n"


class TestContextualizeAlignment:
    def test_file_missing_flagged(self, tmp_path):
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert any(i["symbol"] == "contextualize-missing" for i in issues)

    def test_valid_minimal_body_passes(self, tmp_path):
        _write(tmp_path, _valid_body())
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert issues == []

    def test_line_cap_violation_flagged(self, tmp_path):
        # A body well over the cap.
        big = _valid_body() + ("\n" * (_CONTEXTUALIZE_LINE_CAP + 50))
        _write(tmp_path, big)
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert any(i["symbol"] == "contextualize-bloated" for i in issues)

    def test_missing_canonical_core_flagged(self, tmp_path):
        # Omit one canonical core.
        body = _valid_body().replace("CLAUDE.md", "(deleted)")
        _write(tmp_path, body)
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert any(i["symbol"] == "contextualize-missing-canonical-core" for i in issues)

    def test_every_canonical_core_independently_checked(self, tmp_path):
        # Omit two cores; expect two missing-canonical-core issues.
        body = _valid_body().replace("MEMORY.md", "(removed)").replace("KB § INDEX.md", "(removed)")
        _write(tmp_path, body)
        issues = check_contextualize_alignment(repo_root=tmp_path)
        missing = [i for i in issues if i["symbol"] == "contextualize-missing-canonical-core"]
        assert len(missing) == 2

    def test_severity_high_on_all_violations(self, tmp_path):
        _write(tmp_path, "# tiny\n")  # missing everything
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert all(i["severity"] == "high" for i in issues)
