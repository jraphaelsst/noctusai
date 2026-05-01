"""Tests for `tools/three_way_sync.py` — KB ↔ CLAUDE.md ↔ memory parity verifier."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.three_way_sync import check_three_way_sync


class TestCheckThreeWaySync:
    def _mk_setup(
        self,
        memory_files: dict[str, str],
        memory_index: str,
        claude_md_content: str,
    ) -> tuple[Path, Path]:
        """Create temp memory dir + temp repo dir with CLAUDE.md."""
        memory_dir = Path(tempfile.mkdtemp(prefix="memory_"))
        for name, content in memory_files.items():
            (memory_dir / name).write_text(content)
        (memory_dir / "MEMORY.md").write_text(memory_index)
        repo_dir = Path(tempfile.mkdtemp(prefix="repo_"))
        (repo_dir / "CLAUDE.md").write_text(claude_md_content)
        return memory_dir, repo_dir

    def test_memory_dir_unresolvable_returns_warning_no_op(self):
        # No env var, no standard path → returns warning + skips check.
        with patch.dict(os.environ, {"NOCTUSAI_MEMORY_DIR": "/nonexistent-path-nope"}, clear=False):
            with patch("tools.three_way_sync._resolve_memory_dir", return_value=None):
                result = check_three_way_sync(repo_root=Path(tempfile.mkdtemp()))
        assert result["memory_dir"] is None
        assert any(i["severity"] == "warning" for i in result["issues"])

    def test_clean_setup_no_issues(self):
        memory_dir, repo_dir = self._mk_setup(
            memory_files={
                "feedback_test_rule.md": (
                    "---\nname: Test rule for testing\ndescription: A test\ntype: feedback\n---\n\n"
                    "Body cites KB § PATTERNS/test.md for testing.\n"
                ),
            },
            memory_index="- [Test rule](feedback_test_rule.md) — testing it\n",
            claude_md_content="rule about testing applies here\n",
        )
        with patch.dict(os.environ, {"NOCTUSAI_MEMORY_DIR": str(memory_dir)}, clear=False):
            result = check_three_way_sync(repo_root=repo_dir)
        # All checks pass; severity-high issues should be 0 (warnings about
        # CLAUDE.md keyword may fire but those are heuristic).
        high_issues = [i for i in result["issues"] if i["severity"] == "high"]
        assert high_issues == []
        assert result["stats"]["memory_files_total"] == 1
        assert result["stats"]["memory_files_in_index"] == 1

    def test_memory_file_not_in_index_flagged_high(self):
        memory_dir, repo_dir = self._mk_setup(
            memory_files={
                "feedback_orphan.md": (
                    "---\nname: Orphan rule\ntype: feedback\n---\n"
                    "Cites KB § PATTERNS/orphan.md.\n"
                ),
            },
            memory_index="(empty index — no entries)\n",
            claude_md_content="orphan rule appears here\n",
        )
        with patch.dict(os.environ, {"NOCTUSAI_MEMORY_DIR": str(memory_dir)}, clear=False):
            result = check_three_way_sync(repo_root=repo_dir)
        high = [i for i in result["issues"] if i["severity"] == "high"]
        assert any("feedback_orphan.md" in i["issue"] for i in high)

    def test_index_link_to_missing_file_flagged_high(self):
        memory_dir, repo_dir = self._mk_setup(
            memory_files={},  # no actual files
            memory_index="- [Ghost](feedback_ghost.md) — promised but not delivered\n",
            claude_md_content="ghost rule mentioned\n",
        )
        with patch.dict(os.environ, {"NOCTUSAI_MEMORY_DIR": str(memory_dir)}, clear=False):
            result = check_three_way_sync(repo_root=repo_dir)
        high = [i for i in result["issues"] if i["severity"] == "high"]
        assert any("feedback_ghost.md" in i["issue"] for i in high)

    def test_missing_kb_anchor_flagged_warning(self):
        memory_dir, repo_dir = self._mk_setup(
            memory_files={
                "feedback_no_kb.md": (
                    "---\nname: No KB rule\ntype: feedback\n---\nBody mentions nothing kb-shaped.\n"
                ),
            },
            memory_index="- [No KB](feedback_no_kb.md) — body has no KB anchor\n",
            claude_md_content="rule about not citing kb anywhere\n",
        )
        with patch.dict(os.environ, {"NOCTUSAI_MEMORY_DIR": str(memory_dir)}, clear=False):
            result = check_three_way_sync(repo_root=repo_dir)
        warnings = [i for i in result["issues"] if i["severity"] == "warning"]
        assert any("kb anchor" in i["issue"].lower() for i in warnings)

    def test_claude_md_keyword_match_heuristic(self):
        # Specific-jargon name whose keywords don't appear in CLAUDE.md
        # is flagged as a warning. Use deliberately-rare keywords so the
        # heuristic firmly produces a miss.
        memory_dir, repo_dir = self._mk_setup(
            memory_files={
                "feedback_specific_jargon.md": (
                    "---\nname: Quokka brouhaha thingamajig\ntype: feedback\n---\n"
                    "Cites KB § PATTERNS/quokka.md for testing.\n"
                ),
            },
            memory_index="- [Quokka](feedback_specific_jargon.md) — quokka rule\n",
            claude_md_content="totally unrelated content here, no keyword matches\n",
        )
        with patch.dict(os.environ, {"NOCTUSAI_MEMORY_DIR": str(memory_dir)}, clear=False):
            result = check_three_way_sync(repo_root=repo_dir)
        # CLAUDE.md has none of "quokka"/"brouhaha"/"thingamajig" → warning.
        warnings = [i for i in result["issues"] if i["severity"] == "warning"]
        assert any("CLAUDE.md" in i["issue"] for i in warnings)
