"""Regression tests for `check_agent_archetype_contract` (advisor/executor contract)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_agent_archetype_contract  # noqa: E402


def _write_agent(root: Path, stem: str, body: str) -> Path:
    agents_dir = root / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    p = agents_dir / f"{stem}.md"
    p.write_text(body, encoding="utf-8")
    return p


class TestAgentArchetypeContract:
    def test_advisor_clean_passes(self, tmp_path):
        # An advisor (architect) declaring read-only tools is clean.
        _write_agent(tmp_path, "architect",
            "---\nname: architect\ndescription: advisor.\ntools: Read, Grep, Glob\n---\n# Body\n")
        assert check_agent_archetype_contract(repo_root=tmp_path) == []

    def test_advisor_with_edit_flagged(self, tmp_path):
        _write_agent(tmp_path, "security",
            "---\nname: security\ndescription: advisor.\ntools: Bash, Read, Edit, Grep\n---\n")
        issues = check_agent_archetype_contract(repo_root=tmp_path)
        assert any("declares `Edit`" in i["issue"] for i in issues)

    def test_advisor_with_write_flagged(self, tmp_path):
        _write_agent(tmp_path, "compliance-reviewer",
            "---\nname: compliance-reviewer\ndescription: advisor.\ntools: Read, Write, Grep\n---\n")
        issues = check_agent_archetype_contract(repo_root=tmp_path)
        assert any("declares `Write`" in i["issue"] for i in issues)

    def test_executor_with_engineer_default_passes(self, tmp_path):
        _write_agent(tmp_path, "backend-engineer",
            "---\nname: backend-engineer\ndescription: executor.\ntools: Bash, Read, Edit, Write\n---\nApply the engineer-default protocol.\n")
        assert check_agent_archetype_contract(repo_root=tmp_path) == []

    def test_executor_missing_engineer_default_flagged(self, tmp_path):
        _write_agent(tmp_path, "frontend-engineer",
            "---\nname: frontend-engineer\ndescription: executor.\ntools: Bash, Read, Edit, Write\n---\n# No protocol mention.\n")
        issues = check_agent_archetype_contract(repo_root=tmp_path)
        assert any("does not reference `engineer-default`" in i["issue"] for i in issues)
        assert all(i["severity"] == "warning" for i in issues)

    def test_other_archetype_skipped(self, tmp_path):
        # orchestrator-operator + skill-scout have specialized contracts → skipped.
        _write_agent(tmp_path, "orchestrator-operator",
            "---\nname: orchestrator-operator\ndescription: operator.\ntools: Bash, Read, Write, Edit, Agent\n---\n# No engineer-default mention.\n")
        _write_agent(tmp_path, "skill-scout",
            "---\nname: skill-scout\ndescription: scout.\ntools: Bash, Read, Write, Grep, WebSearch\n---\n# No engineer-default.\n")
        assert check_agent_archetype_contract(repo_root=tmp_path) == []
