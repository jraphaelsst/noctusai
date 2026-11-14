"""Steward enqueue: recurrence andon (warn-first, then refuse) + executor/advisor role aliases."""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_task_branch import FakeGit, FakePointerOps, _anc_pairs  # noqa: E402
from tools.noctus.dev import branch_pointer as BP  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402

WARN_DAY = dt.date(2026, 11, 15)
REFUSE_DAY = dt.date(2026, 11, 21)


def _rows(*rs):
    return lambda keys, *, window_days=14: list(rs)


def _row(cls, n=3, fix=None, sessions=2):
    return {"class": cls, "n_14d": n, "sessions": sessions, "open_fix": fix}


def _git(ct=None):
    def git(*a, **k):
        return (0, f"{ct}\n", "") if ct is not None and a[:2] == ("log", "-1") else (1, "", "")
    return git


def test_quiet_when_below_threshold_or_owned_or_machinery_absent():
    g = _git()
    assert T._recurrence_andon(g, recurrence_fn=_rows(_row("a", n=2)), today=WARN_DAY) is None
    assert T._recurrence_andon(g, recurrence_fn=_rows(_row("a", fix="accepted: rationale")), today=WARN_DAY) is None
    assert T._recurrence_andon(g, recurrence_fn=lambda *a, **k: [], today=WARN_DAY) is None


def test_unowned_class_warns_before_the_deadline_and_refuses_after():
    r = _rows(_row("deliverable:derived_current:kb-counts", n=5))
    warn = T._recurrence_andon(_git(), recurrence_fn=r, today=WARN_DAY)
    assert warn["mode"] == "warn" and "kb-counts" in warn["message"] and "findings_ledger" in warn["message"]
    assert T._recurrence_andon(_git(), recurrence_fn=r, today=REFUSE_DAY)["mode"] == "refuse"


def test_owner_branch_lapses_after_72h_without_commits():
    now = time.time()
    r = _rows(_row("c", fix="feat/fixer"))
    assert T._recurrence_andon(_git(int(now - 3600)), recurrence_fn=r, today=WARN_DAY, now=now) is None
    lapsed = T._recurrence_andon(_git(int(now - 80 * 3600)), recurrence_fn=r, today=WARN_DAY, now=now)
    assert lapsed["classes"][0]["lapsed_owner"] == "feat/fixer"


def test_a_failing_recurrence_read_is_not_a_refusal():
    def boom(*a, **k):
        raise RuntimeError("ledger unreadable")
    assert T._recurrence_andon(_git(), recurrence_fn=boom, today=REFUSE_DAY) is None


def _fake():
    return FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"}, anc=_anc_pairs([]),
                   logs={"d0..b0": "c1 x", "b0..d0": ""}, head_sha="b0")


def test_enqueue_refuses_after_the_deadline_and_pushes_nothing():
    fake = _fake()
    res = T.task_branch(action="enqueue", slug="x", confirm=True, run=fake,
                        pointer_ops=FakePointerOps(latest={"feat/x": {"status": "on_going", "commit": "p", "agent": "tech-lead"}}),
                        slice_scores_reader=lambda: [], recurrence_fn=_rows(_row("k", n=4)))
    # (clock-dependent only through the deadline constant: assert both outcomes are the andon's)
    if dt.date.today() >= T.ANDON_ENFORCE_FROM:
        assert res["refused"] == "refusal_recurrence" and fake.pushes() == []
    else:
        assert res.get("recurrence_andon", {}).get("mode") == "warn" or res.get("deliverable")


def test_executor_and_advisor_are_accepted_as_pointer_roles():
    assert BP.ROLE_ALIASES["executor"] == "engineer" and BP.ROLE_ALIASES["advisor"] in BP.ROLES
