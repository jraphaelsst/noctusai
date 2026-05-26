"""Regression tests for `check_agent_format` (harness-layer format keeper)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_agent_format  # noqa: E402


def _write_agent(root: Path, stem: str, body: str) -> Path:
    agents_dir = root / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    p = agents_dir / f"{stem}.md"
    p.write_text(body, encoding="utf-8")
    return p


class TestAgentFormat:
    def test_no_agents_dir_silent_skip(self, tmp_path):
        assert check_agent_format(repo_root=tmp_path) == []

    def test_clean_agent_passes(self, tmp_path):
        _write_agent(tmp_path, "demo-agent",
            "---\nname: demo-agent\ndescription: demo.\ntools: Read, Grep\n---\n# Body\n")
        assert check_agent_format(repo_root=tmp_path) == []

    def test_missing_frontmatter_flagged(self, tmp_path):
        _write_agent(tmp_path, "bare", "# No frontmatter\n")
        issues = check_agent_format(repo_root=tmp_path)
        assert any("missing/malformed frontmatter" in i["issue"] for i in issues)

    def test_name_mismatch_flagged(self, tmp_path):
        _write_agent(tmp_path, "alpha",
            "---\nname: beta\ndescription: x.\ntools: Read\n---\n")
        issues = check_agent_format(repo_root=tmp_path)
        assert any("≠ filename" in i["issue"] for i in issues)

    def test_missing_tools_flagged(self, tmp_path):
        # The dispatch-engineer-tuning lesson: omitting tools = inherit ~400 deferred names.
        _write_agent(tmp_path, "loose",
            "---\nname: loose\ndescription: x.\n---\n# Body\n")
        issues = check_agent_format(repo_root=tmp_path)
        assert any("missing `tools:`" in i["issue"] for i in issues)
        assert all(i["severity"] == "high" for i in issues)

    def test_missing_description_flagged(self, tmp_path):
        _write_agent(tmp_path, "nodesc",
            "---\nname: nodesc\ntools: Read\n---\n")
        issues = check_agent_format(repo_root=tmp_path)
        assert any("missing `description:`" in i["issue"] for i in issues)
