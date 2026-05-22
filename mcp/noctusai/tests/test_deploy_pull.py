"""Colocated tests for noctus.dev.deploy_pull.

Zero real SSH — run_remote is injected (a FakeRemote that scripts the git
outputs). Covers: up_to_date / planned (dry-run) / blocked-non-FF /
blocked-overlap / deployed, the DERIVED rebuild decision, the safe-git
allowlist guard, and the load-bearing safety invariant: across a *confirmed*
deploy the tool NEVER emits a destructive command (reset/checkout/clean/push).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import deploy_pull as DP  # noqa: E402


def _now():
    return dt.datetime(2026, 5, 22, 12, 0, 0)


class FakeRemote:
    """Scripts remote git/shell IO. rev-parse HEAD returns the target sha once
    a merge has been issued (simulating the fast-forward)."""

    def __init__(self, head, target_sha, status="", log="", diff="",
                 is_ancestor=True, ls_glob=""):
        self.head = head
        self.target_sha = target_sha
        self.status = status
        self.log = log
        self.diff = diff
        self.is_ancestor = is_ancestor
        self.ls_glob = ls_glob
        self.calls: list[list[str]] = []
        self.merged = False

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:1] == ["git"]:
            sub = cmd[3] if len(cmd) > 3 else ""
            if sub == "rev-parse":
                ref = cmd[4]
                if ref == "HEAD":
                    return (0, (self.target_sha if self.merged else self.head) + "\n", "")
                return (0, self.target_sha + "\n", "")
            if sub == "status":
                return (0, self.status, "")
            if sub == "log":
                return (0, self.log, "")
            if sub == "diff":
                return (0, self.diff, "")
            if sub == "merge-base":
                return (0 if self.is_ancestor else 1, "", "")
            if sub == "merge":
                self.merged = True
                return (0, "Updating..\n", "")
            return (0, "", "")  # fetch, tag
        if cmd[:1] == ["sh"]:
            return (0, self.ls_glob, "")
        return (0, "", "")  # mkdir, tar

    def flat(self):
        return " ".join(" ".join(c) for c in self.calls)

    def merge_calls(self):
        return [c for c in self.calls if c[:1] == ["git"] and len(c) > 3 and c[3] == "merge"]


def _run(fake, **kw):
    return DP.deploy_pull(run_remote=fake, now=_now, **kw)


# ── status paths ─────────────────────────────────────────────────
def test_up_to_date():
    f = FakeRemote(head="abc", target_sha="abc")
    r = _run(f)
    assert r["status"] == "up_to_date" and r["exit_code"] == 0
    assert f.merge_calls() == []


def test_planned_dry_run_does_not_merge():
    f = FakeRemote(head="aaa", target_sha="bbb", log="bbb feat: x", diff="docs/x.md",
                   is_ancestor=True)
    r = _run(f, confirm=False)
    assert r["status"] == "planned" and r["exit_code"] == 0
    assert r["is_fast_forward"] is True and r["overlap"] == []
    assert f.merge_calls() == []  # dry-run never moves HEAD


def test_blocked_non_fast_forward():
    f = FakeRemote(head="aaa", target_sha="bbb", is_ancestor=False, diff="x.py")
    r = _run(f, confirm=True)  # even with confirm, a non-FF is refused
    assert r["status"] == "blocked" and r["exit_code"] == 1
    assert "non-fast-forward" in r["reason"]
    assert f.merge_calls() == []


def test_blocked_on_deploy_local_overlap():
    # status shows a deploy-local edit; the incoming diff touches the same file.
    f = FakeRemote(
        head="aaa", target_sha="bbb", is_ancestor=True,
        status=" M projects/x/deploy/tunnel/config.yml\n",
        diff="projects/x/deploy/tunnel/config.yml\nproducts/core/backend/app.py",
    )
    r = _run(f, confirm=True)
    assert r["status"] == "blocked" and r["exit_code"] == 1
    assert "overlap" in r["reason"]
    assert r["overlap"] == ["projects/x/deploy/tunnel/config.yml"]
    assert f.merge_calls() == []


def test_deployed_clean_ff_backs_up_and_verifies():
    f = FakeRemote(head="aaa", target_sha="bbb", is_ancestor=True,
                   log="bbb docs: y", diff="KNOWLEDGE-BASE/x.md")
    r = _run(f, confirm=True)
    assert r["status"] == "deployed" and r["exit_code"] == 0
    assert r["verified_head"] is True and r["new_sha"] == "bbb"
    assert r["backup_ref"] == "backup/predeploy-20260522-120000"
    assert len(f.merge_calls()) == 1
    # docs-only diff → no rebuild
    assert r["rebuild_required"] is False


# ── derived rebuild decision ─────────────────────────────────────
def test_rebuild_decision_product_runtime():
    d = DP._rebuild_decision(["products/core/backend/app.py", "docs/readme.md"])
    assert d["needed"] is True and d["products"] == ["core"]


def test_rebuild_decision_fleet_wide_on_compose():
    d = DP._rebuild_decision(["docker-compose.yml"])
    assert d["needed"] is True and d["fleet_wide"] is True


def test_rebuild_decision_docs_only_no_rebuild():
    d = DP._rebuild_decision(["KNOWLEDGE-BASE/x.md", "projects/y/PROJECT.md",
                              "mcp/noctusai/tools/noctus/dev/deploy_pull.py"])
    assert d["needed"] is False and d["products"] == []


# ── safety invariants ────────────────────────────────────────────
def test_never_emits_destructive_command_on_confirmed_deploy():
    f = FakeRemote(head="aaa", target_sha="bbb", is_ancestor=True,
                   log="bbb feat: z", diff="products/erp/frontend/x.tsx")
    _run(f, confirm=True)
    flat = f.flat()
    for banned in DP._BANNED_TOKENS:
        assert banned not in flat, f"deploy_pull emitted a banned token: {banned!r} in {flat!r}"


def test_git_allowlist_blocks_unsafe_subcommand():
    calls = []
    try:
        DP._git(lambda cmd: calls.append(cmd) or (0, "", ""), "/opt/x", "reset", "--hard")
        assert False, "expected ValueError for a non-allowlisted git subcommand"
    except ValueError as e:
        assert "allowlist" in str(e)
    assert calls == []  # nothing ran


def test_error_when_remote_head_unreadable():
    def bad(cmd):
        if cmd[:1] == ["git"] and len(cmd) > 3 and cmd[3] == "rev-parse":
            return (255, "", "ssh: connect to host: Connection refused")
        return (0, "", "")

    r = DP.deploy_pull(run_remote=bad, now=_now)
    assert r["status"] == "error" and r["exit_code"] == 1
    assert "cannot read remote HEAD" in r["error"]


def test_deploy_local_patterns_from_constant():
    pats = DP._deploy_local_patterns()
    assert ".env" in pats and any("tunnel" in p for p in pats)


def test_resolve_remote_files_passthrough_and_find():
    calls = []

    def runner(cmd):
        calls.append(cmd)
        if cmd[:1] == ["sh"]:
            return (0, "./projects/x/deploy/tunnel/abc.json\n", "")
        return (0, "", "")

    out = DP._resolve_remote_files(runner, "/opt/noctus/noctusai", [".env", "**/tunnel/*.json"])
    assert ".env" in out  # concrete root file passes through
    assert "projects/x/deploy/tunnel/abc.json" in out  # find-resolved, ./ stripped
    # the glob was resolved via `find -path`, NOT a globstar shell glob
    assert any(c[:1] == ["sh"] and "find" in c[2] for c in calls)


def test_tool_registers_with_dotted_name():
    captured = {}

    class _Srv:
        def tool(self, name, description):
            captured["name"] = name
            return lambda fn: fn

    DP.register(_Srv())
    assert captured["name"] == "noctus.dev.deploy_pull"
