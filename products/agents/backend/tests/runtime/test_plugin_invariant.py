"""Plugin invariant (contract §E.5, build-time test): ``agents/julia/plugin/``
contains ONLY ``skills/`` (no ``hooks/``, ``.mcp.json``, ``agents/`` or
``commands/``), and no ``SKILL.md`` declares ``allowed-tools`` frontmatter."""
from pathlib import Path

import yaml

_PLUGIN_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "agents" / "julia" / "plugin"
)


class TestPluginContainsOnlySkills:
    def test_plugin_dir_exists(self):
        assert _PLUGIN_DIR.is_dir(), _PLUGIN_DIR

    def test_only_skills_directory_at_the_top_level(self):
        top_level = {p.name for p in _PLUGIN_DIR.iterdir()}
        assert top_level == {"skills"}, top_level

    def test_no_hooks_mcp_config_agents_or_commands_anywhere_under_plugin(self):
        forbidden_names = {"hooks", ".mcp.json", "agents", "commands"}
        offenders = []
        for path in _PLUGIN_DIR.rglob("*"):
            if path.name in forbidden_names:
                offenders.append(str(path.relative_to(_PLUGIN_DIR)))
        assert offenders == [], offenders

    def test_at_least_one_skill_is_present(self):
        skills_dir = _PLUGIN_DIR / "skills"
        skill_dirs = [p for p in skills_dir.iterdir() if p.is_dir()]
        assert len(skill_dirs) >= 1


class TestNoSkillDeclaresAllowedTools:
    def _iter_skill_md(self):
        skills_dir = _PLUGIN_DIR / "skills"
        yield from skills_dir.glob("*/SKILL.md")

    def test_at_least_one_skill_md_found(self):
        assert list(self._iter_skill_md()), "no SKILL.md files found under plugin/skills/"

    def test_no_skill_md_declares_allowed_tools_frontmatter(self):
        offenders = []
        for path in self._iter_skill_md():
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end == -1:
                continue
            frontmatter_raw = text[3:end]
            frontmatter = yaml.safe_load(frontmatter_raw) or {}
            if "allowed-tools" in frontmatter or "allowed_tools" in frontmatter:
                offenders.append(str(path.relative_to(_PLUGIN_DIR)))
        assert offenders == [], (
            "SKILL.md frontmatter must never declare allowed-tools "
            f"(bypasses the gate): {offenders}"
        )

    def test_every_skill_md_has_name_and_description_frontmatter(self):
        for path in self._iter_skill_md():
            text = path.read_text(encoding="utf-8")
            assert text.startswith("---"), path
            end = text.find("\n---", 3)
            frontmatter = yaml.safe_load(text[3:end]) or {}
            assert frontmatter.get("name"), path
            assert frontmatter.get("description"), path
