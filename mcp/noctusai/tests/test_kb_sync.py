"""kb_sync — native verify_kb_sync() + update_kb_counts() parity.

Asserts the native ports of scripts/verify-kb-sync.sh and
scripts/update-kb-counts.py:
  * preserve the KBSyncResult shape + exit-code semantics (0/1/2),
  * detect broken pointers, unindexed docs, layout-tree drift,
  * regenerate kb-counts marker blocks byte-stably (idempotent),
  * honor check=True drift-only semantics.

Built on synthetic temp trees with tools.kb_sync.REPO_ROOT monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import kb_sync


# ──────────────────────────────────────────────────────────────────
# Temp-tree builder
# ──────────────────────────────────────────────────────────────────

def _mk_tree(root: Path, *, claude_md: str, index_md: str, kb_docs: dict[str, str]):
    (root / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    (root / "KNOWLEDGE-BASE").mkdir(parents=True, exist_ok=True)
    (root / "KNOWLEDGE-BASE" / "INDEX.md").write_text(index_md, encoding="utf-8")
    for rel, body in kb_docs.items():
        p = root / "KNOWLEDGE-BASE" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


_LAYOUT = "## Layout\n\n```\n{tree}\n```\n\n---\n"


# ──────────────────────────────────────────────────────────────────
# verify_kb_sync — exit-code parity
# ──────────────────────────────────────────────────────────────────

def test_verify_clean_tree_exit_0(tmp_path, monkeypatch):
    _mk_tree(
        tmp_path,
        claude_md="See `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md` for depth.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        kb_docs={"CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n"},
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 0
    assert r["ok"] is True
    assert "✓ KB sync OK" in r["stdout"]
    assert r["stderr"] == ""
    assert set(r.keys()) == {"ok", "exit_code", "stdout", "stderr"}


def test_verify_broken_pointer_exit_1(tmp_path, monkeypatch):
    _mk_tree(
        tmp_path,
        claude_md="Broken: `KNOWLEDGE-BASE/CONTEXT/DOES-NOT-EXIST.md`.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        kb_docs={"CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n"},
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 1
    assert r["ok"] is False
    assert "BROKEN" in r["stderr"]
    assert "broken pointer" in r["stderr"]  # count ≥1 (may be caught by multiple checks)


def test_verify_brace_alternation_pointer_skipped(tmp_path, monkeypatch):
    # `{a,b}.md` illustrative patterns must NOT count as broken.
    _mk_tree(
        tmp_path,
        claude_md="Specs `KNOWLEDGE-BASE/backend/{01-CORE,02-ERP}.md` here.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        kb_docs={"CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n"},
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 0


def test_verify_unindexed_doc_exit_2(tmp_path, monkeypatch):
    _mk_tree(
        tmp_path,
        claude_md="See `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        kb_docs={
            "CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n",
            "CONTEXT/ORPHAN.md": "# Orphan not indexed\n",
        },
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 2
    assert r["ok"] is False
    assert "NOT INDEXED" in r["stderr"]
    assert "drift warning(s)" in r["stderr"]


def test_verify_layout_tree_drift_exit_2(tmp_path, monkeypatch):
    # Doc IS indexed (basename present in INDEX) but absent from the
    # Layout tree block → advisory warning, exit 2.
    _mk_tree(
        tmp_path,
        claude_md="See `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n- LATE.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        kb_docs={
            "CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n",
            "CONTEXT/LATE.md": "# Late, indexed but not in layout\n",
        },
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 2
    assert "NOT IN LAYOUT TREE" in r["stderr"]


def test_verify_collective_subtree_exempt(tmp_path, monkeypatch):
    # SKILLS/ docs are indexed collectively — neither index nor layout
    # membership required → still exit 0.
    _mk_tree(
        tmp_path,
        claude_md="See `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        kb_docs={
            "CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n",
            "SKILLS/some-skill.md": "# A skill artifact\n",
        },
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 0


def test_verify_agent_context_indexed_exempt_but_layout_checked(tmp_path, monkeypatch):
    # Behaviour-preserving vs verify-kb-sync.sh: AGENT-CONTEXT.md is
    # exempt from the "must be INDEXED" check (#2) but NOT from the
    # Layout-tree check (#3) — the .sh only skips $KB_INDEX + collective
    # subtrees in #3. So when it IS in the layout tree → exit 0; when it
    # is absent from the layout tree → advisory warning (exit 2).
    _mk_tree(
        tmp_path,
        claude_md="See `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(
            tree="CONTEXT/01-PHILOSOPHY.md\nAGENT-CONTEXT.md"
        ),
        kb_docs={
            "CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n",
            "AGENT-CONTEXT.md": "# Prose, indexed-exempt\n",
        },
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 0

    # Drop it from the layout tree → still index-exempt, but layout
    # check #3 fires (parity with the .sh, which does NOT skip it in #3).
    (tmp_path / "KNOWLEDGE-BASE" / "INDEX.md").write_text(
        "# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        encoding="utf-8",
    )
    r2 = kb_sync.verify_kb_sync()
    assert r2["exit_code"] == 2
    assert "AGENT-CONTEXT.md" in r2["stderr"]
    assert "NOT INDEXED" not in r2["stderr"]  # #2 still exempts it


def test_verify_topical_claude_router_pointers_checked(tmp_path, monkeypatch):
    _mk_tree(
        tmp_path,
        claude_md="Router only.\n",
        index_md="# Index\n\n- 01-PHILOSOPHY.md\n\n"
        + _LAYOUT.format(tree="CONTEXT/01-PHILOSOPHY.md"),
        kb_docs={"CONTEXT/01-PHILOSOPHY.md": "# Philosophy\n"},
    )
    cd = tmp_path / "CLAUDE"
    cd.mkdir()
    (cd / "backend.md").write_text(
        "Broken topical pointer `KNOWLEDGE-BASE/CONTEXT/NOPE.md`.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    r = kb_sync.verify_kb_sync()
    assert r["exit_code"] == 1
    assert "NOPE.md" in r["stderr"]


# ──────────────────────────────────────────────────────────────────
# update_kb_counts — region regeneration parity
# ──────────────────────────────────────────────────────────────────

def _mk_counts_tree(root: Path) -> Path:
    landscape = root / "KNOWLEDGE-BASE" / "CONTEXT" / "02-LANDSCAPE.md"
    agents = root / "KNOWLEDGE-BASE" / "CONTEXT" / "06-AGENTS.md"
    agent_ctx = root / "KNOWLEDGE-BASE" / "AGENT-CONTEXT.md"
    for p in (landscape, agents, agent_ctx):
        p.parent.mkdir(parents=True, exist_ok=True)
    landscape.write_text(
        "# Landscape\n\n"
        "<!-- kb-counts:start:inventory -->\nSTALE\n<!-- kb-counts:end:inventory -->\n\n"
        "<!-- kb-counts:start:database -->\nSTALE\n<!-- kb-counts:end:database -->\n",
        encoding="utf-8",
    )
    agents.write_text(
        "# Agents\n\n"
        "<!-- kb-counts:start:mcp_tools -->\nSTALE\n<!-- kb-counts:end:mcp_tools -->\n",
        encoding="utf-8",
    )
    agent_ctx.write_text(
        "Tools: <!-- kb-counts:start:agent_context_tools -->STALE"
        "<!-- kb-counts:end:agent_context_tools --> available.\n",
        encoding="utf-8",
    )
    # _count_mcp_tools (fixed 2026-05-18) scans the hierarchical
    # `mcp/noctusai/tools/**` package for the `@server.tool` registration
    # idiom (1/tool) — NOT flat `_tool(` in server.py (that shape died in
    # the scripts-mcp-absorption restructure; the old fixture asserted it
    # and silently regressed since pre-commit runs no pytest).
    tools_pkg = root / "mcp" / "noctusai" / "tools"
    tools_pkg.mkdir(parents=True, exist_ok=True)
    (tools_pkg / "leaf.py").write_text(
        "@server.tool\ndef a(): ...\n"
        "@server.tool\ndef b(): ...\n"
        "@server.tool\ndef c(): ...\n",
        encoding="utf-8",
    )
    return landscape


def test_update_kb_counts_writes_and_is_idempotent(tmp_path, monkeypatch):
    landscape = _mk_counts_tree(tmp_path)
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)

    r1 = kb_sync.update_kb_counts(check=False)
    assert r1["ok"] is True
    assert r1["changed"] is True
    txt = landscape.read_text(encoding="utf-8")
    assert "STALE" not in txt
    assert "| Product | Routers" in txt
    assert "**Tables: 0**" in txt  # no migrations in temp tree
    agents_txt = (tmp_path / "KNOWLEDGE-BASE" / "CONTEXT" / "06-AGENTS.md").read_text()
    assert "**3 tools total**" in agents_txt

    # Second run = no change (byte-stable / idempotent).
    snapshot = landscape.read_text(encoding="utf-8")
    r2 = kb_sync.update_kb_counts(check=False)
    assert r2["changed"] is False
    assert landscape.read_text(encoding="utf-8") == snapshot


def test_update_kb_counts_check_reports_drift_without_writing(tmp_path, monkeypatch):
    landscape = _mk_counts_tree(tmp_path)
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    before = landscape.read_text(encoding="utf-8")

    r = kb_sync.update_kb_counts(check=True)
    assert r["drift"] is True
    assert r["ok"] is False
    assert r["changed"] is False
    assert landscape.read_text(encoding="utf-8") == before  # not written

    # After a real run, check reports no drift.
    kb_sync.update_kb_counts(check=False)
    r2 = kb_sync.update_kb_counts(check=True)
    assert r2["drift"] is False
    assert r2["ok"] is True


def test_update_kb_counts_marker_block_format_byte_stable(tmp_path, monkeypatch):
    landscape = _mk_counts_tree(tmp_path)
    monkeypatch.setattr(kb_sync, "REPO_ROOT", tmp_path)
    kb_sync.update_kb_counts(check=False)
    txt = landscape.read_text(encoding="utf-8")
    # Exact open-marker\n<body>\nclose-marker shape from _replace_region.
    assert "<!-- kb-counts:start:inventory -->\n| Product" in txt
    assert "|\n<!-- kb-counts:end:inventory -->" in txt


# ─── Stage-4 keeper: roster-vs-tree parity (2026-05-18) ──────────────
# Regression-test-the-detector for `roster_tree_parity_gaps` — the
# commit-blocking gate that guarantees the 02-LANDSCAPE `## Products`
# table can never silently omit a product on disk (social-wiring drift
# recurred 3× across clean-context self-tests → MUST formalize).

from tools.kb_sync import roster_tree_parity_gaps


def _mk_roster_tree(root, slugs_on_disk, slugs_in_table):
    for s in slugs_on_disk:
        p = root / "products" / s / "backend" / "app"
        p.mkdir(parents=True, exist_ok=True)
        (p / "main.py").write_text("create_product_app()\n")
    rows = "\n".join(
        f"| {s} | `products/{s}/` | d | 8000/9000 | `{s}` |"
        for s in slugs_in_table
    )
    land = root / "KNOWLEDGE-BASE" / "CONTEXT"
    land.mkdir(parents=True, exist_ok=True)
    (land / "02-LANDSCAPE.md").write_text(
        f"# 02\n\n## Products\n\n| P | Path | D | Ports | S |\n"
        f"|---|---|---|---|---|\n{rows}\n\n## Inventory\n\nx\n"
    )


def test_roster_parity_flags_product_missing_from_table(tmp_path):
    _mk_roster_tree(tmp_path, ["foo", "bar"], ["foo"])  # bar on disk, not in table
    assert roster_tree_parity_gaps(tmp_path) == ["bar"]


def test_roster_parity_clean_when_table_covers_tree(tmp_path):
    _mk_roster_tree(tmp_path, ["foo", "bar"], ["foo", "bar"])
    assert roster_tree_parity_gaps(tmp_path) == []


def test_roster_parity_no_landscape_is_empty(tmp_path):
    (tmp_path / "products" / "foo" / "backend" / "app").mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "products" / "foo" / "backend" / "app" / "main.py").write_text("x")
    assert roster_tree_parity_gaps(tmp_path) == []  # no doc → no false error


# ─── Stage-4 keeper: methodology doc-reference integrity (2026-05-25) ──
# Regression suite for ``methodology_reference_gaps`` — the pure predicate
# that closes the verify_kb_sync blind-spot on `KB §` shorthands,
# `.claude/agents/*.md`, and KB→KB cross-refs.
#
# Four coverage axes (spec §Tests):
#   (a) dangling ref in a fake agent file IS flagged
#   (b) placeholder refs (`<x>`, `X.md`) are NOT flagged
#   (c) valid suffix-resolvable ref is NOT flagged
#   (d) real repo exits clean — zero false-positives on the live tree

from tools.kb_sync import methodology_reference_gaps


def _mk_gap_tree(root: pathlib.Path) -> None:
    """Minimal synthetic tree for methodology_reference_gaps tests."""
    # KB: one real doc reachable via CONTEXT/PATTERNS/
    kb_ctx = root / "KNOWLEDGE-BASE" / "CONTEXT" / "PATTERNS"
    kb_ctx.mkdir(parents=True, exist_ok=True)
    (kb_ctx / "real.md").write_text("# Real doc\n")
    # .claude/agents/
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    # CLAUDE.md skeleton (must exist for the scanner)
    (root / "CLAUDE.md").write_text("# CLAUDE\n")


def test_methodology_gap_dangling_ref_in_agent_file(tmp_path):
    """(a) A dangling `KB § PATTERNS/nonexistent.md` in an agent file
    MUST be returned as a gap."""
    _mk_gap_tree(tmp_path)
    agent = tmp_path / ".claude" / "agents" / "my-agent.md"
    agent.write_text(
        "You are an engineer. See `KB § PATTERNS/nonexistent.md` for rules.\n"
    )
    gaps = methodology_reference_gaps(tmp_path)
    assert any("nonexistent.md" in g for g in gaps), (
        f"Expected a gap for nonexistent.md but got: {gaps}"
    )


def test_methodology_gap_placeholder_not_flagged(tmp_path):
    """(b) Placeholder refs (`<x>`, `X.md`, and glob forms like
    `KNOWLEDGE-BASE/**/*.md` — the literal form that tripped the old
    section-1 `{`-only skip) must NOT be flagged."""
    _mk_gap_tree(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "See `KB § INTEGRATIONS/<x>.md` and `KB § PATTERNS/X.md`; "
        "the gate scans `KNOWLEDGE-BASE/**/*.md` and `{a,b}.md`.\n"
    )
    gaps = methodology_reference_gaps(tmp_path)
    assert gaps == [], f"Expected no gaps but got: {gaps}"


def test_methodology_gap_suffix_resolvable_not_flagged(tmp_path):
    """(c) A ref that resolves via suffix-match (KB § PATTERNS/real.md,
    where CONTEXT/PATTERNS/real.md exists) must NOT be flagged."""
    _mk_gap_tree(tmp_path)
    agent = tmp_path / ".claude" / "agents" / "ok-agent.md"
    agent.write_text(
        "See `KB § PATTERNS/real.md` for the pattern.\n"
    )
    gaps = methodology_reference_gaps(tmp_path)
    assert gaps == [], f"Expected no gaps on suffix-resolvable ref but got: {gaps}"


def test_methodology_gap_real_repo_zero_gaps():
    """(d) The REAL repo tree must produce zero hard gaps (no false
    positives on the live methodology surfaces)."""
    import pathlib as _pl
    real_root = _pl.Path(__file__).resolve().parents[3]  # repo root
    gaps = methodology_reference_gaps(real_root)
    assert gaps == [], (
        f"methodology_reference_gaps found {len(gaps)} gap(s) on the "
        f"real tree — these must be fixed before committing:\n"
        + "\n".join(f"  {g}" for g in gaps)
    )
