"""Regression tests for `check_seven_way_sync` + `check_skills_listed_in_router`.

KB § PATTERNS/common/seven-way-sync.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_seven_way_sync,
    check_skills_listed_in_router,
)


def _mk_repo(tmp_path: Path) -> Path:
    """Minimum repo shape the keeper needs."""
    (tmp_path / "KNOWLEDGE-BASE").mkdir()
    (tmp_path / "KNOWLEDGE-BASE" / "INDEX.md").write_text("# Index\n")
    (tmp_path / "CONTEXTUALIZE.md").write_text("# Contextualize\n")
    return tmp_path


def _mk_claude_md(tmp_path: Path, skills_line: str) -> None:
    """Write a CLAUDE.md with a stub §2 'Procedure skills' line."""
    (tmp_path / "CLAUDE.md").write_text(
        "# CLAUDE.md\n\n"
        "## 1 · Universal rules\n\n"
        "- **Some rule.** → `KB § ...`\n\n"
        "## 2 · The Map\n\n"
        f"{skills_line}\n",
        encoding="utf-8",
    )


def _mk_skill(tmp_path: Path, name: str) -> None:
    skill_dir = tmp_path / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: stub\n---\n# {name}\n"
    )


# ── check_skills_listed_in_router ───────────────────────────────────────────
class TestSkillsListedInRouter:
    def test_silent_when_no_claude_md(self, tmp_path):
        # No CLAUDE.md → silent skip.
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        assert check_skills_listed_in_router(tmp_path) == []

    def test_silent_when_no_skills_dir(self, tmp_path):
        # No .claude/skills/ → silent skip.
        (tmp_path / "CLAUDE.md").write_text("# stub\n")
        assert check_skills_listed_in_router(tmp_path) == []

    def test_clean_when_skill_listed(self, tmp_path):
        _mk_repo(tmp_path)
        _mk_skill(tmp_path, "noc-foo")
        _mk_claude_md(
            tmp_path,
            "**Procedure skills** (`.claude/skills/`, auto-trigger): `noc-foo`.",
        )
        assert check_skills_listed_in_router(tmp_path) == []

    def test_flags_skill_orphan_on_disk(self, tmp_path):
        # Skill exists on disk but NOT in CLAUDE.md.
        _mk_repo(tmp_path)
        _mk_skill(tmp_path, "noc-undocumented")
        _mk_claude_md(
            tmp_path,
            "**Procedure skills** (`.claude/skills/`, auto-trigger): `noc-something-else`.",
        )
        issues = check_skills_listed_in_router(tmp_path)
        assert any(i["symbol"] == "skill-orphan-on-disk" for i in issues)
        assert any("noc-undocumented" in i["issue"] for i in issues)

    def test_flags_skill_orphan_in_router(self, tmp_path):
        # Listed in CLAUDE.md but no on-disk dir.
        _mk_repo(tmp_path)
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        _mk_claude_md(
            tmp_path,
            "**Procedure skills** (`.claude/skills/`, auto-trigger): `noc-ghost` · `noc-real`.",
        )
        _mk_skill(tmp_path, "noc-real")
        issues = check_skills_listed_in_router(tmp_path)
        assert any(i["symbol"] == "skill-orphan-in-router" for i in issues)
        assert any("noc-ghost" in i["issue"] for i in issues)

    def test_non_skill_helpers_ignored(self, tmp_path):
        # Names like `codify` (a command) shouldn't trip the orphan-in-router check.
        _mk_repo(tmp_path)
        _mk_skill(tmp_path, "noc-only-one")
        _mk_claude_md(
            tmp_path,
            "**Procedure skills** (`.claude/skills/`, auto-trigger): `noc-only-one` · `codify`.",
        )
        # `codify` is heuristic-skipped (not noc-prefixed, not skill-creator).
        issues = check_skills_listed_in_router(tmp_path)
        assert not any("codify" in i["issue"] for i in issues)

    def test_skill_creator_explicit_match(self, tmp_path):
        # `skill-creator` is a real skill name (no noc- prefix).
        _mk_repo(tmp_path)
        _mk_skill(tmp_path, "skill-creator")
        _mk_claude_md(
            tmp_path,
            "**Procedure skills** (`.claude/skills/`, auto-trigger): `skill-creator`.",
        )
        assert check_skills_listed_in_router(tmp_path) == []


# ── check_seven_way_sync (composition) ────────────────────────────────────────
class TestSixWaySync:
    def test_each_issue_carries_composition_prefix(self, tmp_path):
        # Empty repo → kb_sync sub-keeper will return something or nothing,
        # but ANY issues returned MUST carry the seven-way-sync-<sub> prefix.
        _mk_repo(tmp_path)
        # CLAUDE.md missing → contextualize keeper might fire.
        result = check_seven_way_sync(tmp_path)
        # Every result must have the composition prefix.
        for issue in result:
            assert issue["symbol"].startswith("seven-way-sync-"), \
                f"missing composition prefix on {issue}"

    def test_composes_skills_listed_results(self, tmp_path):
        # Create a real orphan-on-disk scenario; the composition keeper
        # MUST surface it (with the seven-way-sync- prefix).
        _mk_repo(tmp_path)
        _mk_skill(tmp_path, "noc-orphan")
        _mk_claude_md(
            tmp_path,
            "**Procedure skills** (`.claude/skills/`, auto-trigger): `noc-other`.",
        )
        result = check_seven_way_sync(tmp_path)
        skills_issues = [i for i in result if "skills-router" in i["symbol"]]
        assert len(skills_issues) >= 1
        assert any("noc-orphan" in i["issue"] for i in skills_issues)

    def test_sub_keeper_exceptions_dont_crash(self, tmp_path, monkeypatch):
        # If a sub-keeper raises, the composition keeper must absorb +
        # surface as a warning-symbol-error, not crash.
        from tools.noctus.dev import compliance as _c

        def _boom(*a, **kw):
            raise RuntimeError("synthetic sub-keeper failure")

        monkeypatch.setattr(_c, "check_agent_kb_alignment", _boom)
        result = check_seven_way_sync(tmp_path)
        # We expect at least one warning-symbol-error issue for agent-kb.
        agent_kb_errs = [i for i in result if "agent-kb-error" in i["symbol"]]
        assert len(agent_kb_errs) == 1
        assert agent_kb_errs[0]["severity"] == "warning"
        assert "synthetic" in agent_kb_errs[0]["issue"]
