"""Spec scan (contract §E.8, W0 audit 2026-09-14): a scan of
``app/agents/julia/**`` asserting the sibling repo's person/company names
and the stale-rule phrases it carried are absent from the ported prompt +
skills.

**The denylist literals live ONLY in this test** (per the G2 brief) — no
other module in this slice references the sibling's names.
"""
from pathlib import Path

_JULIA_DIR = Path(__file__).resolve().parents[2] / "app" / "agents" / "julia"

# The sibling's audited person name (14 occurrences, including the
# hardcoded approver) and company name (8 occurrences) — contract §E.8.
_PERSON_NAME = "Rapha"
_COMPANY_NAME = "One Consultoria"

# Stale rules dropped per contract §E.8 (no longer apply once Julia runs
# via the Claude Agent SDK in the agents control plane, not the terminal):
# read-only sibling workspace, the vendored mcp/_kit absorption seam,
# "files are the source of truth" (the DB is now canonical), git-status
# reads, and WhatsApp (no channel for Julia — roadmap T1).
_STALE_PHRASES = [
    "../noctusai",
    "mcp/_kit",
    "_kit",
    "Files are the source of truth",
    "arquivos são a fonte da verdade",
    "git status",
    "WhatsApp",
    "whatsapp",
]

# Deprecated §C tools removed by the HTTP port — contract §C table.
_DEPRECATED_TOOLS = ["kb.index_sync", "kb_index_sync", "kb.link_check", "kb_link_check", "roadmap.render", "roadmap_render"]


def _all_ported_files() -> list[Path]:
    return [p for p in _JULIA_DIR.rglob("*") if p.is_file()]


class TestNoClientFacts:
    def test_no_person_name(self):
        offenders = [
            str(p.relative_to(_JULIA_DIR))
            for p in _all_ported_files()
            if _PERSON_NAME in p.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"sibling person name leaked into: {offenders}"

    def test_no_company_name(self):
        offenders = [
            str(p.relative_to(_JULIA_DIR))
            for p in _all_ported_files()
            if _COMPANY_NAME in p.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"sibling company name leaked into: {offenders}"

    def test_approver_is_generic_not_a_named_person(self):
        julia_md = (_JULIA_DIR / "JULIA.md").read_text(encoding="utf-8")
        assert "pessoa que aprova" in julia_md or "quem aprova" in julia_md


class TestStaleRulesDropped:
    def test_no_stale_phrase_survives(self):
        offenders = []
        for p in _all_ported_files():
            text = p.read_text(encoding="utf-8")
            for phrase in _STALE_PHRASES:
                if phrase in text:
                    offenders.append((str(p.relative_to(_JULIA_DIR)), phrase))
        assert offenders == [], f"stale rule phrases survived porting: {offenders}"


class TestDeprecatedToolsRemoved:
    def test_no_deprecated_tool_referenced(self):
        offenders = []
        for p in _all_ported_files():
            text = p.read_text(encoding="utf-8")
            for tool in _DEPRECATED_TOOLS:
                if tool in text:
                    offenders.append((str(p.relative_to(_JULIA_DIR)), tool))
        assert offenders == [], f"deprecated §C tool referenced: {offenders}"


class TestSkillsReferenceOnlyE4ToolNames:
    """Every ``mcp__academia__*`` reference inside a skill must be a real
    §E.4 tool name — a typo'd or invented tool name would silently never
    fire (Claude would just fail to find the tool)."""

    def test_every_academia_tool_mention_is_a_real_e4_name(self):
        from app.runtime import gate

        valid = set(gate.LEITURA) | set(gate.ESCRITA)
        skills_dir = _JULIA_DIR / "plugin" / "skills"
        offenders = []
        for path in skills_dir.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            for token in text.split():
                token = token.strip(".,:;()`*\"'")
                if token.startswith("mcp__academia__") and token not in valid:
                    offenders.append((str(path.relative_to(_JULIA_DIR)), token))
        assert offenders == [], offenders

    def test_no_bash_write_or_file_path_instructions_in_skills(self):
        skills_dir = _JULIA_DIR / "plugin" / "skills"
        forbidden = ["Bash(", "`Write`", "`Edit`", "KNOWLEDGE-BASE/", "KB § "]
        offenders = []
        for path in skills_dir.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            for phrase in forbidden:
                if phrase in text:
                    offenders.append((str(path.relative_to(_JULIA_DIR)), phrase))
        assert offenders == [], offenders

    def test_ar_mcp_tool_and_ar_contextualizar_were_not_ported(self):
        skills_dir = _JULIA_DIR / "plugin" / "skills"
        names = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        assert "ar-mcp-tool" not in names
        assert "ar-contextualizar" not in names
