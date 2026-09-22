"""Regression tests for `check_contextualize_alignment` — the fresh-agent
read-map pointer-only discipline (sibling of `check_claude_md_router`).

KB § PATTERNS/common/claude-md-router-discipline.md. Phase B (2026-05-26).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_contextualize_alignment,
    _CONTEXTUALIZE_CANONICAL_CORES,
    _CONTEXTUALIZE_LINE_CAP,
)


def _write(root: Path, body: str) -> None:
    (root / "CONTEXTUALIZE.md").write_text(body, encoding="utf-8")


def _valid_body() -> str:
    """A minimal valid body that references every canonical core."""
    lines = ["# CONTEXTUALIZE.md (test fixture)", ""]
    for ref in _CONTEXTUALIZE_CANONICAL_CORES:
        lines.append(f"- pointer → {ref}")
    return "\n".join(lines) + "\n"


class TestContextualizeAlignment:
    def test_file_missing_flagged(self, tmp_path):
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert any(i["symbol"] == "contextualize-missing" for i in issues)

    def test_valid_minimal_body_passes(self, tmp_path):
        _write(tmp_path, _valid_body())
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert issues == []

    def test_line_cap_violation_flagged(self, tmp_path):
        # A body well over the cap.
        big = _valid_body() + ("\n" * (_CONTEXTUALIZE_LINE_CAP + 50))
        _write(tmp_path, big)
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert any(i["symbol"] == "contextualize-bloated" for i in issues)

    def test_missing_canonical_core_flagged(self, tmp_path):
        # Omit one canonical core.
        body = _valid_body().replace("CLAUDE.md", "(deleted)")
        _write(tmp_path, body)
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert any(i["symbol"] == "contextualize-missing-canonical-core" for i in issues)

    def test_every_canonical_core_independently_checked(self, tmp_path):
        # Omit two cores; expect two missing-canonical-core issues.
        body = _valid_body().replace("MEMORY.md", "(removed)").replace("KB § INDEX.md", "(removed)")
        _write(tmp_path, body)
        issues = check_contextualize_alignment(repo_root=tmp_path)
        missing = [i for i in issues if i["symbol"] == "contextualize-missing-canonical-core"]
        assert len(missing) == 2

    def test_severity_high_on_all_violations(self, tmp_path):
        _write(tmp_path, "# tiny\n")  # missing everything
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert all(i["severity"] == "high" for i in issues)


# ──────────────────────────────────────────────────────────────────
# Content-freshness legs (d) + (e) — 2026-09-21 contextualize-freshness-gate.
# Legs (a)-(c) guard SHAPE only: CONTEXTUALIZE.md listed 8 of 9 slash commands,
# claimed 14 procedure skills (20 on disk) and 197 MCP tools (254) — all green.
# ──────────────────────────────────────────────────────────────────

_ROSTER_BLOCK = (
    "- **Specialist subagents** (`.claude/agents/`) — {agents}\n"
    "- **Procedure skills** (`.claude/skills/`, auto-trigger) — {skills}\n"
    "- **Slash commands** (`.claude/commands/`, via `/<name>`) — {commands}\n"
)


def _harness(root: Path, skills=(), commands=(), agents=()) -> None:
    for s in skills:
        d = root / ".claude" / "skills" / s
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text("# s\n", encoding="utf-8")
    for kind, names in (("commands", commands), ("agents", agents)):
        d = root / ".claude" / kind
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / f"{n}.md").write_text("# x\n", encoding="utf-8")


def _body_listing(skills=(), commands=(), agents=(), extra: str = "") -> str:
    return _valid_body() + _ROSTER_BLOCK.format(
        agents=" · ".join(f"`{a}`" for a in agents),
        skills=" · ".join(f"`{s}`" for s in skills),
        commands=" · ".join(f"`/{c}`" for c in commands),
    ) + extra


def _symbols(tmp_path) -> list[str]:
    return [i["symbol"] for i in check_contextualize_alignment(repo_root=tmp_path)]


class TestContextualizeFreshness:
    ROSTER = dict(skills=("noc-ship", "skill-creator"), commands=("gc",), agents=("architect",))

    def test_complete_roster_passes(self, tmp_path):
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _body_listing(**self.ROSTER))
        assert check_contextualize_alignment(repo_root=tmp_path) == []

    def test_unlisted_command_flagged(self, tmp_path):
        """The exact regression: `/gc` on disk, absent from the map."""
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _body_listing(skills=self.ROSTER["skills"], agents=self.ROSTER["agents"]))
        assert "contextualize-commands-unlisted" in _symbols(tmp_path)

    def test_unlisted_skill_and_agent_flagged(self, tmp_path):
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _body_listing(commands=self.ROSTER["commands"]))
        syms = _symbols(tmp_path)
        assert "contextualize-skills-unlisted" in syms
        assert "contextualize-agents-unlisted" in syms

    def test_stale_listed_names_flagged(self, tmp_path):
        """A name on a roster line with nothing on disk is the reverse drift."""
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _body_listing(
            skills=self.ROSTER["skills"] + ("noc-retired",),
            commands=self.ROSTER["commands"] + ("gone",),
            agents=self.ROSTER["agents"] + ("qa-engineer",),
        ))
        syms = _symbols(tmp_path)
        for kind in ("skills", "commands", "agents"):
            assert f"contextualize-{kind}-stale" in syms, kind

    def test_missing_roster_line_flagged(self, tmp_path):
        _harness(tmp_path, **self.ROSTER)
        body = _body_listing(**self.ROSTER).replace("(`.claude/commands/`", "(commands")
        _write(tmp_path, body.replace("`/gc`", "`/gc` "))  # still listed, but no marker
        assert "contextualize-commands-roster-line-missing" in _symbols(tmp_path)

    def test_count_claim_must_equal_derived(self, tmp_path):
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _body_listing(**self.ROSTER, extra="The 14 procedure skills exist.\n"))
        assert "contextualize-count-drift" in _symbols(tmp_path)

    def test_correct_count_claim_passes(self, tmp_path):
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _body_listing(
            **self.ROSTER, extra="The 1 specialist agents + 2 procedure skills exist.\n",
        ))
        assert check_contextualize_alignment(repo_root=tmp_path) == []

    def test_hand_written_tool_count_forbidden(self, tmp_path):
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _body_listing(**self.ROSTER, extra="the MCP dev toolkit (197 tools)\n"))
        assert "contextualize-hand-count" in _symbols(tmp_path)

    def test_freshness_violations_are_high(self, tmp_path):
        _harness(tmp_path, **self.ROSTER)
        _write(tmp_path, _valid_body())  # lists nothing
        issues = check_contextualize_alignment(repo_root=tmp_path)
        assert issues and all(i["severity"] == "high" for i in issues)


def test_the_live_tree_is_clean():
    """CI leg: the merged tip must satisfy the gate, not just each branch.

    Two branches that each add a skill are green alone; only the merged tree
    shows CONTEXTUALIZE.md missing one of them. Pre-commit cannot see that —
    the Tooling Tests job runs this on every non-ledger push to dev.
    """
    from settings import REPO_ROOT
    issues = check_contextualize_alignment(repo_root=REPO_ROOT)
    assert issues == [], "\n".join(f"{i['symbol']}: {i['issue']}" for i in issues)
