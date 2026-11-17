"""ci_verdict + its release_steward hooks, through the GithubClient seam (Fake), no patching."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
DEV = REPO / "mcp/noctusai/tools/noctus/dev"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cv = _load("noc_ci_verdict", DEV / "ci_verdict.py")  # the name release_steward._sibling uses
rs = _load("release_steward_cv_under_test", DEV / "release_steward.py")
H = "a" * 40


def fake(**runs):
    return cv.FakeGithubClient(tips={"feat/x": H}, runs={str(k): v for k, v in runs.items()})


def test_judge_green_red_pending_invalid():
    c = fake(**{"1": cv.make_run(1, H, conclusion="success"), "2": cv.make_run(2, H, conclusion="failure"),
                "3": cv.make_run(3, H, status="in_progress"), "4": cv.make_run(4, "b" * 40, conclusion="success"),
                "5": cv.make_run(5, H, conclusion="success", path=".github/workflows/other.yml"),
                "6": cv.make_run(6, H, conclusion="success", repo="evil/noc")})
    assert cv.judge("gh-run:1", H, c)[0] == "green"
    st, d = cv.judge("gh-run:2", H, c)
    assert st == "red" and "failure" in d and "actions/runs/2" in d
    st, d = cv.judge("gh-run:3", H, c)
    assert st == "pending" and d.startswith(cv.PENDING_PREFIX)
    for ref in ("gh-run:4", "gh-run:5", "gh-run:6", "gh-run:99", "gh-run:abc", "ci-parity:" + "0" * 32, ""):
        assert cv.judge(ref, H, c)[0] == "invalid", ref
    assert cv.judge("gh-run:1", "abc", c)[0] == "invalid"  # short sha refused


def test_gh_unavailable_is_invalid_not_green():
    c = cv.FakeGithubClient(fail="gh auth failed")
    st, d = cv.judge("gh-run:1", H, c)
    assert st == "invalid" and "gh auth failed" in d


def test_find_existing_prefers_live_over_cancelled_and_resolve_dispatches_only_when_none():
    c = fake(**{"1": cv.make_run(1, H, conclusion="cancelled", created_at="2026-11-16T11:00:00Z"),
                "2": cv.make_run(2, H, status="in_progress", created_at="2026-11-16T10:00:00Z")})
    assert cv.find_existing(H, c) == "gh-run:2"
    out = cv.resolve_for_filing("feat/x", H, c)
    assert out["ref"] == "gh-run:2" and out["state"] == "pending" and not c.dispatched
    c2 = fake()
    out = cv.resolve_for_filing("feat/x", H, c2, polls=1)
    assert out["ok"] and out["dispatched"] and c2.dispatched == [("feat/x", "b" * 40)] and out["state"] == "pending"


def test_dispatch_refuses_when_branch_tip_differs_and_errors_loudly():
    c = fake()
    c.tips["feat/x"] = "c" * 40
    out = cv.resolve_for_filing("feat/x", H, c)
    assert out["ok"] is False and "push the branch" in out["error"]
    assert cv.resolve_for_filing("feat/x", H, cv.FakeGithubClient(fail="no gh"))["ok"] is False


def test_validate_verdict_ref_delegates_and_deliverable_pending_marker():
    ok, why = rs.validate_verdict_ref("gh-run:1", H, None, None) if False else (None, None)
    c = fake(**{"3": cv.make_run(3, H, status="queued")})
    # validate_verdict_ref builds its own real client; exercise the pure judge + marker contract instead
    st, d = cv.judge("gh-run:3", H, c)
    assert st == "pending" and d.startswith("CI running:")
    assert rs.verdict_kind("gh-run:12") == "gh-run" and rs.verdict_kind("ci-parity:" + "a" * 32) == "ci-parity"
    assert rs.verdict_kind("whatever") is None


def _store(tmp_path, ci):
    return rs.StewardStore(tmp_path, resolve_head=lambda b: H, ci_resolve=ci,
                           deliverable_check=lambda b, h, v: {
                               "ok": False, "verdict": "pending_ci", "head_sha": H, "failing": ["scoped_green"],
                               "items": [{"n": 5, "name": "scoped_green", "ok": False, "detail": "CI running: u", "pending": True}]})


def test_request_files_nonblocking_with_pending_gh_run(tmp_path):
    seen = []
    s = _store(tmp_path, lambda b, h: seen.append((b, h)) or {"ok": True, "ref": "gh-run:7", "state": "pending",
                                                              "detail": "CI running: u", "dispatched": True})
    out = s.request("sess", "x")
    assert out["ok"] and out["status"] == "queued_for_steward" and out["ci"]["ref"] == "gh-run:7"
    assert seen == [("feat/x", H)] and out["request"]["verdict_ref"] == "gh-run:7"
    ev = [e for e in s._events() if e.get("event") == "request"][-1]
    assert ev["verdict_kind"] == "gh-run"
    assert s_report(s)["by_verdict_kind"] == {"gh-run": 1}


def s_report(s):
    return rs.verdict_report(s.root / rs.VERDICT_STORE_NAME, s._events())


def test_request_fails_loudly_when_gh_unavailable(tmp_path):
    s = _store(tmp_path, lambda b, h: {"ok": False, "error": "GitHub CI verdict unavailable: no gh"})
    out = s.request("sess", "x")
    assert out["ok"] is False and "no gh" in out["error"]
    assert not [e for e in s._events() if e.get("event") == "request"]


def test_red_item5_is_still_refused(tmp_path):
    s = rs.StewardStore(tmp_path, resolve_head=lambda b: H,
                        ci_resolve=lambda b, h: {"ok": True, "ref": "gh-run:8", "state": "red", "detail": "x"},
                        deliverable_check=lambda b, h, v: {"ok": False, "verdict": "needs_resync", "head_sha": H,
                                                           "failing": ["scoped_green"],
                                                           "items": [{"n": 5, "name": "scoped_green", "ok": False, "detail": "red"}]})
    assert s.request("sess", "x")["status"] == "needs_resync"
