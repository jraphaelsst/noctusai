"""Tests for session_end_sweep's auto-delivery of trailing ledger churn.

The recurring `chore(cost-log)` commit (and any dirty append-only ledger row) is
FF-pushed to origin/dev at session close so a session ends local==remote — nothing
lingers looking like stale work. These tests pin the DISPATCH logic (clean → skip;
dirty → commit+push; clean-but-ahead → push existing) with the shared
`commit_and_ff_push_ledger` helper monkeypatched (it has its own coverage).

Zero real git — the git runner is injected.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import session_end_sweep as SES  # noqa: E402
from tools.noctus.dev import _ledger_push as LP  # noqa: E402


def _sub(cmd: list[str]) -> str:
    """The git subcommand from `["git", "-C", root, <sub>, ...]`."""
    return cmd[3] if len(cmd) > 3 and cmd[1] == "-C" else (cmd[1] if len(cmd) > 1 else "")


class FakeGit:
    """Scripts (rc, out, err) per git subcommand; records every call."""

    def __init__(self, scripts):
        self.scripts = scripts
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        sub = _sub(cmd)
        if sub == "symbolic-ref" and "symbolic-ref" not in self.scripts:
            return (0, "dev\n", "")  # default: primary is on dev (the normal state)
        return self.scripts.get(sub, (0, "", ""))


def test_clean_tree_no_ahead_is_a_noop(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(LP, "commit_and_ff_push_ledger", lambda **k: called.__setitem__("n", called["n"] + 1) or {})
    runner = FakeGit({"status": (0, "", ""), "rev-list": (0, "", "")})

    res = SES.deliver_trailing_ledgers(Path("/repo"), _runner=runner)
    assert res["status"] == "clean" and res["pushed"] is False
    assert called["n"] == 0  # helper never invoked — nothing to deliver


def test_dirty_ledger_commits_and_pushes(monkeypatch):
    seen = {}

    def fake_helper(**kw):
        seen.update(kw)
        return {"ok": True, "status": "pushed", "pushed": True}

    monkeypatch.setattr(LP, "commit_and_ff_push_ledger", fake_helper)
    runner = FakeGit({
        "status": (0, " M project-history/vector-costs.ndjson\n", ""),  # dirty
        "rev-list": (0, "", ""),
    })

    res = SES.deliver_trailing_ledgers(Path("/repo"), _runner=runner)
    assert res["pushed"] is True and res["status"] == "pushed"
    assert seen["already_committed"] is False           # dirty → commit path
    assert seen["commit_msg"] and "cost-log" in seen["commit_msg"]
    assert "project-history/vector-costs.ndjson" in seen["rel_paths"]


def test_clean_tree_but_trailing_commit_pushes_existing(monkeypatch):
    seen = {}

    def fake_helper(**kw):
        seen.update(kw)
        return {"ok": True, "status": "pushed", "pushed": True}

    monkeypatch.setattr(LP, "commit_and_ff_push_ledger", fake_helper)
    runner = FakeGit({
        "status": (0, "", ""),                 # clean tree
        "rev-list": (0, "abc123\n", ""),       # one trailing commit ahead of origin/dev
    })

    res = SES.deliver_trailing_ledgers(Path("/repo"), _runner=runner)
    assert res["pushed"] is True
    assert seen["already_committed"] is True   # push existing, don't re-commit
    assert seen["commit_msg"] is None


def test_delivery_never_raises_on_helper_error(monkeypatch):
    monkeypatch.setattr(LP, "commit_and_ff_push_ledger",
                        lambda **k: {"ok": False, "committed_locally": True, "error": "push failed"})
    runner = FakeGit({"status": (0, " M project-history/ledger.ndjson\n", ""), "rev-list": (0, "", "")})
    res = SES.deliver_trailing_ledgers(Path("/repo"), _runner=runner)
    assert res["pushed"] is False
    assert res["detail"]["error"] == "push failed"


def test_sweep_can_disable_delivery(monkeypatch):
    """deliver_ledgers=False → the survey runs but never pushes (the read-only mode)."""
    monkeypatch.setattr(SES, "deliver_trailing_ledgers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    # _worktree_branches / orphan scan / remote hygiene all tolerate a missing repo;
    # we only assert the delivery path is gated off.
    out = SES.sweep(repo_root=Path("/nonexistent-repo-xyz"), deliver_ledgers=False)
    assert out["ledger_delivery"]["status"] == "skipped"


def test_skips_when_primary_not_on_dev(monkeypatch):
    """If the primary checkout is on a feature branch, delivery must NOT rebase/push
    the wrong branch — it skips cleanly with a reason."""
    called = {"n": 0}
    monkeypatch.setattr(LP, "commit_and_ff_push_ledger", lambda **k: called.__setitem__("n", called["n"] + 1) or {})
    runner = FakeGit({
        "symbolic-ref": (0, "feat/something\n", ""),   # NOT on dev
        "status": (0, " M project-history/vector-costs.ndjson\n", ""),
    })
    res = SES.deliver_trailing_ledgers(Path("/repo"), _runner=runner)
    assert res["status"] == "skipped" and res["pushed"] is False
    assert "not on 'dev'" in res["reason"]
    assert called["n"] == 0  # never touched the helper
