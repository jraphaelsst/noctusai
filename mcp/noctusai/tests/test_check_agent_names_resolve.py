"""Regression tests for `check_agent_names_resolve`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.noctus.dev.compliance import check_agent_names_resolve  # noqa: E402


def _mk(tmp_path):
    ag = tmp_path / ".claude" / "agents"
    ag.mkdir(parents=True)
    (ag / "product-engineer.md").write_text("---\nname: product-engineer\ndescription: d\ntools: Read\nowns_kb: []\n---\n")
    (ag / "engineer-seed.md").write_text(
        '---\nname: engineer-seed\ndescription: d\ntools: Read\nowns_kb: []\ndeprecated: "alias; retire after 4.1.0"\n---\n'
    )
    return tmp_path


class TestCheckAgentNamesResolve:
    """unresolved -> high, deprecated alias -> warning, real -> clean."""

    def test_green_resolving_name(self, tmp_path):
        root = _mk(tmp_path)
        (root / "CLAUDE.md").write_text("Dispatch `subagent_type: product-engineer` and `product-engineer`.\n")
        assert check_agent_names_resolve(repo_root=root) == []

    def test_red_unresolved_name(self, tmp_path):
        root = _mk(tmp_path)
        (root / "CLAUDE.md").write_text('Use subagent_type="ghost-engineer" or see `.claude/agents/other-thing.md`.\n')
        issues = check_agent_names_resolve(repo_root=root)
        assert {i["severity"] for i in issues} == {"high"}
        assert len(issues) == 2

    def test_alias_is_warning_with_note(self, tmp_path):
        root = _mk(tmp_path)
        (root / "CLAUDE.md").write_text("| S1 | engineer-seed | files |\n")
        issues = check_agent_names_resolve(repo_root=root)
        assert len(issues) == 1 and issues[0]["severity"] == "warning"
        assert "retire after 4.1.0" in issues[0]["issue"]
