"""Tests for diff and quality tools."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.diff import diff_product_against_seed, find_orphaned_files, check_api_consistency


class TestDiffAgainstSeed:
    def test_seed_matches_itself(self):
        result = diff_product_against_seed("seed")
        assert result["product"] == "seed"
        for f, status in result["diffs"].items():
            assert status == "identical", f"{f} differs from seed"

    def test_nonexistent_product(self):
        result = diff_product_against_seed("nonexistent")
        assert "error" in result


class TestFindOrphans:
    def test_returns_list(self):
        result = find_orphaned_files("seed")
        assert "orphans" in result
        assert isinstance(result["orphans"], list)

    def test_counts_match(self):
        result = find_orphaned_files("mailing")
        assert result["count"] == len(result["orphans"])


class TestAPIConsistency:
    def test_returns_issues(self):
        result = check_api_consistency("mailing")
        assert "issues" in result
        assert isinstance(result["issues"], list)

    def test_no_product(self):
        result = check_api_consistency("nonexistent")
        assert result["issues"] == []
