"""A toolkit tool's result is capped by construction: over the cap it is a compact summary + the path of the full
JSON under ~/.noctus (never a silent truncation), under it nothing changes. Real files in tmp dirs, a real FastMCP
server with `install_output_cap` on the real call path; `session_end_sweep.compact_sweep` shrinks the real sweep shape."""
from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tool_output_cap as toc  # noqa: E402
from tools.noctus.dev import session_end_sweep as ses  # noqa: E402


def _big(n: int = 3000) -> dict:
    return {"ok": True, "remote_branches": {"integrated_suggest_delete": [f"feat/some-long-branch-name-{i}" for i in range(n)]},
            "worktrees": [{"slug": f"s{i}", "classification": "safe-to-cleanup", "path": "/x" * 40} for i in range(n)]}


def test_under_the_cap_is_untouched(tmp_path):
    value = {"ok": True, "rows": [1, 2, 3]}
    assert toc.cap_value("noctus.dev.x", value, limit=10_000, out_dir=tmp_path) is value
    assert list(tmp_path.iterdir()) == []


def test_over_the_cap_returns_summary_and_writes_the_full_json(tmp_path):
    value = _big()
    out = toc.cap_value("noctus.dev.session_end_sweep", value, limit=50_000, out_dir=tmp_path)
    assert out["truncated"] is True and out["tool"] == "noctus.dev.session_end_sweep"
    assert len(json.dumps(out)) < 8_000
    path = Path(out["full_output_path"])
    assert path.parent == tmp_path and json.loads(path.read_text()) == value  # nothing lost
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert out["top_level"]["worktrees"] == "list[3000]"


def test_an_unwritable_dir_is_said_not_swallowed(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    out = toc.cap_value("noctus.dev.x", _big(), limit=1000, out_dir=blocker / "sub")
    assert out["truncated"] is True and out["full_output_path"] is None and "could not be saved" in out["error"]


def test_old_captures_are_pruned(tmp_path):
    for i in range(60):
        f = tmp_path / f"t-{i:03d}.json"
        f.write_text("{}")
        os.utime(f, (1000 + i, 1000 + i))
    toc.cap_value("t", _big(), limit=1000, out_dir=tmp_path, keep=10)
    assert len(list(tmp_path.glob("*.json"))) == 10


def test_env_overrides_the_limit(monkeypatch):
    monkeypatch.setenv(toc.CAP_ENV, "123")
    assert toc.cap_limit() == 123
    monkeypatch.setenv(toc.CAP_ENV, "nope")
    assert toc.cap_limit() == toc.DEFAULT_CAP_CHARS


def test_installed_on_a_real_server_the_wire_result_is_capped(tmp_path, monkeypatch):
    from mcp.server.fastmcp import FastMCP

    monkeypatch.setenv(toc.OUT_DIR_ENV, str(tmp_path))
    server = FastMCP(name="t")

    @server.tool(name="noctus.dev.big", structured_output=False)
    def big() -> dict:
        return _big()

    @server.tool(name="noctus.dev.small", structured_output=False)
    def small() -> dict:
        return {"ok": True}

    toc.install_output_cap(server)
    blocks = asyncio.run(server.call_tool("noctus.dev.big", {}))
    wire = json.loads(blocks[0].text)
    assert wire["truncated"] is True and Path(wire["full_output_path"]).exists()
    assert json.loads(asyncio.run(server.call_tool("noctus.dev.small", {}))[0].text) == {"ok": True}


def test_build_server_installs_the_cap():
    import server as srv

    assert getattr(srv.build_server()._tool_manager.call_tool, "_noc_output_cap", False)


def test_compact_sweep_keeps_the_decision_data_and_points_at_the_full_json(tmp_path):
    full = {
        "ok": True, "clean_wrap": True, "wrap_blockers": [], "sweep_ts": "t",
        "worktrees": [{"slug": f"s{i}", "branch": f"feat/s{i}", "path": "/p", "classification": "safe-to-cleanup",
                       "suggestion": "x", "ahead": 0, "behind": 1, "uncommitted": False} for i in range(500)]
                     + [{"slug": "dirty", "branch": "feat/d", "path": "/p", "classification": "uncommitted-work",
                         "suggestion": "commit", "ahead": 1, "behind": 0, "uncommitted": True}],
        "orphan_branches": {"ok": True, "branches": [{"branch": f"b{i}", "classification": "integrated"} for i in range(2000)]},
        "remote_branches": {"ok": True, "total": 3000, "integrated_count": 2999,
                            "integrated_suggest_delete": [f"b{i}" for i in range(2999)],
                            "unique_aged_count": 1, "unique_aged_suggest_salvage": [{"branch": "u", "age_days": 9}]},
        "pointer_heal": {"healed": [], "skipped_unproven": [], "errors": []},
        "ledger_delivery": {"status": "clean"}, "summary_log": {"ok": True}, "ledger_store_flush": {"ok": True},
        "background_processes": {"status": "ok", "clean_wrap": True, "processes": []},
    }
    out = ses.compact_sweep(full, out_dir=tmp_path)
    assert len(json.dumps(out)) < 20_000
    assert out["worktree_counts"] == {"safe-to-cleanup": 500, "uncommitted-work": 1}
    assert [w["slug"] for w in out["needs_attention"]] == ["dirty"]
    assert out["remote_branches"]["integrated_count"] == 2999 and len(out["remote_branches"]["integrated_suggest_delete"]) <= 10
    assert json.loads(Path(out["full_report"]).read_text()) == full
