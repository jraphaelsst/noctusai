"""task_branch integrate refuses an engineer slice with no slice-scores row."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_task_branch import FakeGit, FakePointerOps, _anc_pairs  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402


def _fake():
    return FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"}, anc=_anc_pairs([]),
                   logs={"d0..b0": "c1 x", "b0..d0": ""}, head_sha="b0")


def _ops(agent):
    return FakePointerOps(latest={"feat/x": {"status": "on_going", "commit": "p", "agent": agent}})


def test_engineer_slice_without_score_is_refused_with_exact_call():
    fake = _fake()
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake,
                        pointer_ops=_ops("backend-engineer"), slice_scores_reader=lambda: [])
    assert res["refused"] == "slice_unscored" and res["status"] == "blocked"
    assert res["unscored"] == [{"slug": "x", "agent": "backend-engineer"}]
    assert "dispatch_log_completion(slug='x'" in res["log_completion_calls"][0]
    assert fake.pushes() == []


def test_scored_engineer_slice_integrates():
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=_fake(),
                        pointer_ops=_ops("backend-engineer"),
                        slice_scores_reader=lambda: [{"slug": "x"}])
    assert res["status"] == "integrated"


def test_inline_tech_lead_branch_is_exempt():
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=_fake(),
                        pointer_ops=_ops("tech-lead"), slice_scores_reader=lambda: [])
    assert res["status"] == "integrated"


def test_missing_pointer_is_not_an_exemption():
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=_fake(),
                        pointer_ops=FakePointerOps(), slice_scores_reader=lambda: [])
    assert res["refused"] == "slice_unscored"


def test_accept_unscored_needs_a_real_reason_and_is_recorded():
    kw = dict(action="integrate", slug="x", confirm=False, pointer_ops=_ops("frontend-engineer"),
              slice_scores_reader=lambda: [])
    assert T.task_branch(run=_fake(), accept_unscored="short", **kw)["refused"] == "slice_unscored"
    res = T.task_branch(run=_fake(), accept_unscored="engineer died before returning", **kw)
    assert res["status"] == "planned"
    assert res["accepted_unscored"]["slugs"] == ["x"]


def test_unreadable_ledger_blocks():
    def boom():
        raise RuntimeError("store down")
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=_fake(),
                        pointer_ops=_ops("backend-engineer"), slice_scores_reader=boom)
    assert res["refused"] == "slice_scores_unreadable"


def test_train_checks_each_rider():
    ops = FakePointerOps(latest={
        "feat/a": {"agent": "backend-engineer"}, "feat/b": {"agent": "backend-engineer"}})
    missing = T.slice_unscored_riders(
        ["a", "b"], ops=ops, branch_prefix="feat/", reader=lambda: [{"slug": "a"}])
    assert missing == [{"slug": "b", "agent": "backend-engineer"}]


def test_no_pointer_ops_skips_gate():
    assert T.slice_unscored_riders(["a"], ops=None, branch_prefix="feat/", reader=lambda: []) == []
