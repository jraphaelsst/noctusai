"""Regression tests for `check_eight_way_sync` + `check_skills_listed_in_router`
+ `check_all_cache_freshness`.

KB § PATTERNS/common/eight-way-sync.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_all_cache_freshness,
    check_eight_way_sync,
    check_seven_way_sync,
    check_six_way_sync,
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


# ── check_eight_way_sync (composition) ─────────────────────────────────────
class TestEightWaySync:
    def test_each_issue_carries_composition_prefix(self, tmp_path):
        # Empty repo → kb_sync sub-keeper will return something or nothing,
        # but ANY issues returned MUST carry the eight-way-sync-<sub> prefix.
        _mk_repo(tmp_path)
        # CLAUDE.md missing → contextualize keeper might fire.
        result = check_eight_way_sync(tmp_path)
        # Every result must have the composition prefix.
        for issue in result:
            assert issue["symbol"].startswith("eight-way-sync-"), \
                f"missing composition prefix on {issue}"

    def test_composes_skills_listed_results(self, tmp_path):
        # Create a real orphan-on-disk scenario; the composition keeper
        # MUST surface it (with the eight-way-sync- prefix).
        _mk_repo(tmp_path)
        _mk_skill(tmp_path, "noc-orphan")
        _mk_claude_md(
            tmp_path,
            "**Procedure skills** (`.claude/skills/`, auto-trigger): `noc-other`.",
        )
        result = check_eight_way_sync(tmp_path)
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
        result = check_eight_way_sync(tmp_path)
        # We expect at least one warning-symbol-error issue for agent-kb.
        agent_kb_errs = [i for i in result if "agent-kb-error" in i["symbol"]]
        assert len(agent_kb_errs) == 1
        assert agent_kb_errs[0]["severity"] == "warning"
        assert "synthetic" in agent_kb_errs[0]["issue"]

    def test_composes_cache_freshness_leg(self, tmp_path):
        # The 8th surface — .claude/cache/ — is checked via
        # check_all_cache_freshness composed at the cache-freshness leg.
        # On an empty tree most cache keepers silent-skip; the leg should
        # exist with its composition prefix when issues do arise.
        _mk_repo(tmp_path)
        result = check_eight_way_sync(tmp_path)
        # Any cache-related issue must carry the eight-way-sync-cache-freshness prefix.
        cache_issues = [i for i in result if "cache-freshness" in i["symbol"]]
        for issue in cache_issues:
            assert issue["symbol"].startswith("eight-way-sync-cache-freshness::")


# ── back-compat aliases ─────────────────────────────────────────────────────
class TestBackCompatAliases:
    def test_check_seven_way_sync_alias_resolves(self):
        # The old symbol MUST still be callable and dispatch to the new one.
        assert check_seven_way_sync is check_eight_way_sync

    def test_check_six_way_sync_alias_resolves(self):
        # Two-promotions-back alias preserved.
        assert check_six_way_sync is check_eight_way_sync


# ── check_all_cache_freshness (composition over 8 cache keepers) ────────────
class TestAllCacheFreshness:
    def test_each_issue_carries_composition_prefix(self, tmp_path):
        # Empty repo — most cache freshness keepers silent-skip (no source,
        # no cache). Any issues must carry the composition prefix.
        result = check_all_cache_freshness(tmp_path)
        for issue in result:
            assert issue["symbol"].startswith("all-cache-freshness-"), \
                f"missing composition prefix on {issue}"

    def test_composes_eight_legs(self, tmp_path, monkeypatch):
        # Each of the 8 sub-keepers must be invoked. Patch them to return
        # a tagged sentinel issue; assert all 8 appear in the output.
        from tools.noctus.dev import compliance as _c

        sub_names = [
            "check_keeper_cache_freshness",
            "check_agent_context_cache_freshness",
            "check_auto_improvement_cache_freshness",
            "check_code_embeddings_cache_freshness",
            "check_noc_graph_cache_freshness",
            "check_kb_embeddings_cache_freshness",
            "check_corpus_embeddings_cache_freshness",
            "check_memory_embeddings_cache_freshness",
        ]
        for name in sub_names:
            def _factory(n):
                def _stub(*_a, **_kw):
                    return [{
                        "product": "<test>", "file": f"<{n}>",
                        "issue": f"sentinel from {n}",
                        "severity": "warning",
                        "symbol": f"sentinel-{n}",
                    }]
                return _stub
            monkeypatch.setattr(_c, name, _factory(name))

        result = check_all_cache_freshness(tmp_path)
        # Each sub-keeper contributed exactly one issue, decorated.
        assert len(result) == 8
        for issue in result:
            assert issue["symbol"].startswith("all-cache-freshness-")
            assert "::sentinel-check_" in issue["symbol"]

    def test_sub_keeper_exception_absorbed(self, tmp_path, monkeypatch):
        # If a per-cache keeper raises, the composition emits a
        # warning-error issue and doesn't crash.
        from tools.noctus.dev import compliance as _c

        def _boom(*a, **kw):
            raise RuntimeError("synthetic cache-keeper failure")

        monkeypatch.setattr(_c, "check_noc_graph_cache_freshness", _boom)
        result = check_all_cache_freshness(tmp_path)
        noc_errs = [i for i in result if "noc-graph-error" in i["symbol"]]
        assert len(noc_errs) == 1
        assert noc_errs[0]["severity"] == "warning"
        assert "synthetic" in noc_errs[0]["issue"]

    def test_heals_structural_caches_on_contact(self, tmp_path, monkeypatch):
        # The check MUST settle the zero-OpenAI structural caches first, so a
        # structural cache left stale by an out-of-commit auto-improvement.ndjson
        # append (or an FF-merge that skips post-merge) SELF-HEALS instead of
        # blocking [high] an unrelated commit. (2026-06-01 regression.)
        from tools.noctus.dev import refresh_all_caches as _r

        called = {"n": 0}

        def _spy(repo_root=None):
            called["n"] += 1
            return {"ok": True, "healed": [], "stale_embedding": [], "detail": None}

        monkeypatch.setattr(_r, "settle_structural_caches", _spy)
        check_all_cache_freshness(tmp_path)
        assert called["n"] == 1, \
            "check_all_cache_freshness must settle structural caches (heal-on-contact)"

    def test_heal_failure_is_logged_not_raised(self, tmp_path, monkeypatch):
        # Heal is BEST-EFFORT: if settle raises, the check still runs the
        # sub-keepers (no crash, no silent swallow — residual staleness still
        # surfaces through the composed sub-keepers).
        from tools.noctus.dev import refresh_all_caches as _r

        def _boom(repo_root=None):
            raise RuntimeError("synthetic settle failure")

        monkeypatch.setattr(_r, "settle_structural_caches", _boom)
        result = check_all_cache_freshness(tmp_path)  # must NOT raise
        assert isinstance(result, list)
