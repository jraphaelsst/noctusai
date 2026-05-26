"""Regression tests for `check_skill_format` (harness-layer format keeper).

Sibling of TestClaudeMdRouter / TestMemoryMdIndex / TestAgentFormat /
TestAgentArchetypeContract. Per `KB § PATTERNS/compliance/testing.md § Regression-test-
the-detector` — the colocated suite the meta-detector requires.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_skill_format  # noqa: E402


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill_dir = root / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    p = skill_dir / "SKILL.md"
    p.write_text(body, encoding="utf-8")
    return p


class TestSkillFormat:
    def test_no_skills_dir_silent_skip(self, tmp_path):
        assert check_skill_format(repo_root=tmp_path) == []

    def test_clean_skill_passes(self, tmp_path):
        _write_skill(tmp_path, "noc-demo",
            "---\nname: noc-demo\ndescription: When user asks to 'demo'.\n---\n# Body\n")
        assert check_skill_format(repo_root=tmp_path) == []

    def test_missing_skill_md_flagged(self, tmp_path):
        (tmp_path / ".claude" / "skills" / "noc-orphan").mkdir(parents=True)
        issues = check_skill_format(repo_root=tmp_path)
        assert any("has no SKILL.md" in i["issue"] for i in issues)

    def test_missing_frontmatter_flagged(self, tmp_path):
        _write_skill(tmp_path, "noc-bad", "# No frontmatter at all\nbody\n")
        issues = check_skill_format(repo_root=tmp_path)
        assert any("missing/malformed frontmatter" in i["issue"] for i in issues)

    def test_name_mismatch_flagged(self, tmp_path):
        _write_skill(tmp_path, "noc-x",
            "---\nname: noc-y\ndescription: x.\n---\n")
        issues = check_skill_format(repo_root=tmp_path)
        assert any("≠ directory" in i["issue"] for i in issues)

    def test_missing_description_flagged(self, tmp_path):
        _write_skill(tmp_path, "noc-nodesc",
            "---\nname: noc-nodesc\n---\n# Body\n")
        issues = check_skill_format(repo_root=tmp_path)
        assert any("missing `description:`" in i["issue"] for i in issues)
