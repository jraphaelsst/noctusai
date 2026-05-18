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
    assert "1 broken pointer(s)" in r["stderr"]


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
    # Minimal server.py so _count_mcp_tools has something to count.
    srv = root / "mcp" / "noctusai" / "server.py"
    srv.parent.mkdir(parents=True, exist_ok=True)
    srv.write_text("    _tool(a)\n    _tool(b)\n    _tool(c)\n", encoding="utf-8")
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
