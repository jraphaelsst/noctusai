"""A stale MCP server must not judge deliveries with the code it loaded (2026-11-26).

The incident: the kb-counts item left the delivery contract on 2026-11-18 (adda0ba7d), yet every session whose MCP
server had started before that kept refusing `request`s on `derived_current: kb-counts` - 42 refusals across 6
sessions in 14 days, class `deliverable:derived_current:stale-or-unmeasured-at-the-head:-kb-counts`. The steward was
the one judging tool not behind `toolkit_freshness.refuse_gate`. These tests drive the REAL gate against a disposable
baseline file (same fixture shape as test_toolkit_freshness.py); only the subprocess launcher is injected.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cli  # noqa: E402
from tools.noctus.dev import release_steward as RS  # noqa: E402
from tools.noctus.dev import toolkit_freshness as TF  # noqa: E402


def _seed(tmp_path: Path, monkeypatch, *, stale: bool) -> None:
    f = tmp_path / "loaded_module.py"
    f.write_text("# v1\n")
    st = f.stat()
    monkeypatch.setattr(TF, "_baseline", {str(f): (st.st_mtime, st.st_size)})
    monkeypatch.setattr(TF, "_loaded_at", time.time())
    monkeypatch.setattr(TF, "_cached_verdict", None)
    monkeypatch.setattr(TF, "_cached_at", 0.0)
    if stale:
        f.write_text("# v2, changed on disk after the baseline\n")


class _Server:
    def __init__(self) -> None:
        self.fns: dict = {}

    def tool(self, name: str, **_kw):
        def deco(fn):
            self.fns[name] = fn
            return fn
        return deco


def _mcp_params() -> set[str]:
    srv = _Server()
    RS.register(srv)
    return set(inspect.signature(srv.fns["noctus.dev.release_steward"]).parameters)


def test_every_mcp_param_crosses_the_subprocess_hop():
    """A param with no CLI flag would be silently dropped on the fresh hop (F3) - the map must cover them all."""
    assert _mcp_params() == set(TF._MAPPED_PARAMS["release_steward"])
    assert set(inspect.signature(RS.steward_call).parameters) == _mcp_params()


def test_argv_parses_back_to_the_same_request():
    kw = {"action": "request", "slug": "x", "branch": "fix/x", "head_sha": "abc", "products": ["agents", "core"],
          "migrations": True, "notes": "n o t e s", "verdict_ref": "gh-run:1", "inline_reason": "owner_directed",
          "inline_note": "ten chars or more", "branches": ["fix/a", "fix/b"], "run_scoped": True,
          "since": "2026-11-01T00:00:00Z", "deadline_min": 5.0, "op": "clear", "role": "agents", "confirm": True}
    args = cli.build_parser().parse_args(TF._tool_cli_argv("release_steward", kw))
    assert args.release_steward == "request"
    assert (args.steward_slug, args.steward_branch, args.steward_head_sha) == ("x", "fix/x", "abc")
    assert args.steward_products == "agents,core" and args.steward_branches == "fix/a,fix/b"
    assert args.steward_migrations and args.steward_run_scoped and args.steward_confirm
    assert args.steward_notes == "n o t e s" and args.steward_verdict_ref == "gh-run:1"
    assert args.steward_since == "2026-11-01T00:00:00Z" and args.steward_deadline_min == 5.0
    assert (args.steward_role, args.steward_role_op) == ("agents", "clear")


def test_child_acts_as_the_same_claude_process():
    assert TF._tool_cli_env("release_steward") == {"CLAUDE_PID": str(os.getppid())}
    assert TF._tool_cli_env("task_branch") == {}


@pytest.mark.parametrize("action", ["request", "deliverable", "ack", "claim", "reconcile", "inbox", "mine"])
def test_stale_server_judges_on_fresh_code(tmp_path, monkeypatch, action):
    _seed(tmp_path, monkeypatch, stale=True)
    seen: list[list[str]] = []

    def fake_run(cmd):
        seen.append(cmd)
        return 3, json.dumps({"ok": False, "verdict": "needs_resync", "action": action}, indent=2), ""

    r = RS.gated_steward_call()(action=action, slug="x", subprocess_run=fake_run)
    assert seen and seen[0][1].endswith("cli.py") and f"--release-steward={action}" in seen[0]
    assert r["executed_via"] == "fresh_subprocess" and r["primary_toolkit_stale"] is True
    assert r["verdict"] == "needs_resync"  # the CHILD's verdict, verbatim


@pytest.mark.parametrize("action", sorted(RS.STALE_IN_PROCESS_ACTIONS))
def test_lease_reads_stay_in_process(action):
    assert RS.steward_call_is_write({"action": action}) is False


def test_fresh_server_never_launches_a_subprocess(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, stale=False)
    monkeypatch.setenv("NOCTUS_STEWARD_DIR", str(tmp_path / "steward"))  # role_touch writes here, never ~/.noctus
    monkeypatch.setenv(RS.SESSION_ENV, "test-session-fresh")

    def boom(cmd):
        raise AssertionError(f"a fresh server must not subprocess: {cmd}")

    # `bogus` is answered in-process by run_action (unknown action error)
    r = RS.gated_steward_call()(action="bogus", subprocess_run=boom)
    assert r.get("executed_via") != "fresh_subprocess" and not r.get("ok", True)
