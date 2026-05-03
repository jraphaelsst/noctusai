"""Tests for the LGPD flagging tool."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import lgpd


@pytest.fixture(autouse=True)
def _redirect_warnings_file(tmp_path, monkeypatch):
    """Point the tool at a fresh temp file per test."""
    warnings_file = tmp_path / "LGPD-WARNINGS.md"
    monkeypatch.setattr(lgpd, "WARNINGS_FILE", warnings_file)
    monkeypatch.setattr(lgpd, "REPO_ROOT", tmp_path)
    return warnings_file


class TestFlag:
    def test_creates_file_with_header(self, _redirect_warnings_file):
        result = lgpd.flag(
            code_path="a.py:10",
            concern="x",
            reason="y.",
        )
        content = _redirect_warnings_file.read_text(encoding="utf-8")
        assert "LGPD Concerns" in content
        assert "**x**" in content
        assert "a.py:10" in content
        assert "TBD" in content  # default mitigation
        assert result["notification"].startswith("⚠️")
        assert result["deduped"] is False

    def test_new_entries_prepend_to_file(self, _redirect_warnings_file):
        lgpd.flag(code_path="p1", concern="c1", reason="r1")
        lgpd.flag(code_path="p2", concern="c2", reason="r2")
        content = _redirect_warnings_file.read_text(encoding="utf-8")
        # c2 was added second — should appear BEFORE c1 (newest first).
        idx_c1 = content.index("c1")
        idx_c2 = content.index("c2")
        assert idx_c2 < idx_c1

    def test_same_concern_same_path_deduped(self, _redirect_warnings_file):
        first = lgpd.flag(code_path="p", concern="c", reason="r")
        second = lgpd.flag(code_path="p", concern="c", reason="r", mitigation="fix it")
        assert first["deduped"] is False
        assert second["deduped"] is True
        # Only one entry with this (concern, path) combo.
        content = _redirect_warnings_file.read_text(encoding="utf-8")
        assert content.count("`p`") == 1

    def test_different_path_same_concern_creates_separate_entry(self, _redirect_warnings_file):
        lgpd.flag(code_path="p1", concern="c", reason="r")
        lgpd.flag(code_path="p2", concern="c", reason="r")
        result = lgpd.list_warnings()
        assert result["unresolved_count"] == 2

    def test_mitigation_surfaces_in_entry(self, _redirect_warnings_file):
        lgpd.flag(
            code_path="x.py",
            concern="n",
            reason="because.",
            mitigation="redact patient tokens before the call",
        )
        content = _redirect_warnings_file.read_text(encoding="utf-8")
        assert "redact patient tokens" in content

    def test_missing_required_args_returns_error(self, _redirect_warnings_file):
        result = lgpd.flag(code_path="", concern="c", reason="r")
        assert "error" in result
        assert not _redirect_warnings_file.exists()

    def test_notification_mentions_file(self, _redirect_warnings_file):
        result = lgpd.flag(code_path="p", concern="c", reason="r")
        assert "LGPD-WARNINGS.md" in result["notification"]

    def test_not_a_blocker(self, _redirect_warnings_file):
        """Explicit invariant — flag never raises, never exits."""
        result = lgpd.flag(code_path="p", concern="c", reason="r")
        assert "error" not in result
        # No exception even after three flags in a row.
        for i in range(3):
            lgpd.flag(code_path=f"p{i}", concern="c", reason="r")


class TestListWarnings:
    def test_empty_when_no_file(self, _redirect_warnings_file):
        result = lgpd.list_warnings()
        assert result["entries"] == []

    def test_counts_resolved_vs_unresolved(self, _redirect_warnings_file):
        lgpd.flag(code_path="p1", concern="c1", reason="r")
        lgpd.flag(code_path="p2", concern="c2", reason="r")
        # Manually resolve one by ticking the checkbox.
        content = _redirect_warnings_file.read_text(encoding="utf-8")
        content = content.replace("- [ ] **c1**", "- [x] **c1**", 1)
        _redirect_warnings_file.write_text(content, encoding="utf-8")
        result = lgpd.list_warnings()
        assert result["unresolved_count"] == 1
        assert result["resolved_count"] == 1

    def test_preserves_order_of_entries(self, _redirect_warnings_file):
        lgpd.flag(code_path="p-old", concern="old", reason="r")
        lgpd.flag(code_path="p-new", concern="new", reason="r")
        result = lgpd.list_warnings()
        concerns = [e["concern"] for e in result["entries"]]
        # Newer entry appears first (prepended).
        assert concerns[0] == "new"
        assert concerns[1] == "old"


class TestIdempotency:
    def test_refresh_preserves_first_flagged_timestamp(self, _redirect_warnings_file, monkeypatch):
        """Re-flagging the same concern/path updates `Last seen` but keeps
        the original `First flagged` date intact."""
        monkeypatch.setattr(lgpd, "_now", lambda: "2026-04-01")
        lgpd.flag(code_path="p", concern="c", reason="r")

        monkeypatch.setattr(lgpd, "_now", lambda: "2026-04-18")
        lgpd.flag(code_path="p", concern="c", reason="r")

        content = _redirect_warnings_file.read_text(encoding="utf-8")
        assert "First flagged*: 2026-04-01" in content
        assert "Last seen*: 2026-04-18" in content
