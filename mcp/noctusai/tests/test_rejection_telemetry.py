"""Every rejection reaches the gate-event log (`gate_alignment.record_event`), so `walls` / `trend` can see it.

Owner ask 2026-11-14: "learn from the rejections ... lower the rejection numbers over time". The most expensive
rejections were never counted: a merge-queue ejection, a steward/enqueue refusal, a scoped verdict that is red or
UNMEASURED. These tests drive the REAL code paths (the watch loop, the real-git enqueue, the steward tool layer) and
read the shared event log back; nothing of ours is patched. `NOCTUS_GUARD_EVENT_LOG` is per-test (conftest).

Also the root-cause test for the `index.lock` the scoped deliverable used to leave in the primary checkout:
`deliverable` / `enqueue` must never write the index of the checkout they run from.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_guardian_pure_push_enqueue import World, item, sh  # noqa: E402
from tests.test_release_steward import PEER, STEWARD  # noqa: E402,F401
from tools.noctus.dev import gate_alignment as ga  # noqa: E402
from tools.noctus.dev import merge_queue as MQ  # noqa: E402
from tools.noctus.dev import release_steward as RS  # noqa: E402


def _rows(gate_prefix: str = "") -> list[dict]:
    return [r for r in ga.read_events() if r["gate"].startswith(gate_prefix)]


# ------------------------------------------------------------------------------ (a) merge-queue ejection
def _watch(final_state: dict, slug: str = "feat-x") -> None:
    polls = iter([
        {"status": "ok", "dev": "d", "count": 1, "entries": [{"slug": slug, "ref": "r", "sha": "a" * 40,
                                                              "verdict": {"state": "pending"}}]},
        {"status": "ok", "dev": "d", "count": 0, "entries": []},
    ])
    MQ.watch(lambda: next(polls), lambda sha: final_state, sleep=lambda s: None, emit=lambda line: None, max_polls=2)


def test_a_queue_ejection_seen_by_the_watch_is_one_mq_eject_deny_with_the_cause():
    cause = "ejected (ci_red): Tests & Build red: ['toolkit']"
    _watch({"state": "ejected", "description": cause})
    rows = _rows("mq:eject")
    assert [(r["outcome"], r["target"], r["reason"]) for r in rows] == [("deny", "feat-x", cause)]
    assert rows[0]["kind"] == "rejection"


def test_the_same_ejection_observed_again_is_not_counted_twice():
    cause = "ejected (conflict): conflicts with dev+queue ahead of it"
    _watch({"state": "ejected", "description": cause})
    MQ.record_ejection("feat-x", cause, source="task_branch.landed")  # `landed` observes the very same ejection
    assert len(_rows("mq:eject")) == 1


def test_landing_is_the_natural_pass_that_marks_the_earlier_ejection_fixed():
    MQ.record_ejection("feat-x", "ejected (ci_red): x")
    _watch({"state": "landed", "dev_sha": "abc1234"})
    st = ga.gate_stats(ga.read_events())["mq:eject"]
    assert (st["denies"], st["passes"], st["fixed"]) == (1, 1, 1)


# --------------------------------------------------------------- (b) steward / enqueue refusals (real git)
@pytest.fixture()
def world(tmp_path):
    return World(tmp_path)


def test_enqueue_needs_resync_is_counted_and_the_later_queued_enqueue_is_its_pass(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")  # NOT pushed -> item 1 fails
    res = world.enqueue()
    assert res["status"] == "needs_resync" and "head_pushed_clean" in res["failing"]
    rows = _rows("steward:enqueue:needs_resync")
    assert [(r["outcome"], r["target"], r["reason"]) for r in rows] == [("deny", "x", "head_pushed_clean")]
    world.push(wt, "feat/x")
    assert world.enqueue()["status"] == "queued"
    st = ga.gate_stats(ga.read_events())["steward:enqueue:needs_resync"]
    assert (st["denies"], st["fixed"]) == (1, 1)


def test_a_refusal_for_an_unscored_slice_is_counted_under_its_own_reason():
    from tests.test_task_branch import FakeGit, FakePointerOps, _anc_pairs
    from tools.noctus.dev import task_branch as T
    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"}, anc=_anc_pairs([]),
                   logs={"d0..b0": "c1 x", "b0..d0": ""}, head_sha="b0")
    ops = FakePointerOps(latest={"feat/x": {"status": "on_going", "commit": "p", "agent": "backend-engineer"}})
    res = T.task_branch(action="enqueue", slug="x", confirm=True, run=fake, pointer_ops=ops,
                        slice_scores_reader=lambda: [])
    assert res["refused"] == "slice_unscored"
    assert [(r["gate"], r["outcome"], r["target"]) for r in _rows("steward:enqueue:")] == \
        [("steward:enqueue:slice_unscored", "deny", "x")]


def test_the_steward_tool_layer_counts_a_stale_lease_refusal(tmp_path):
    from tests.test_release_steward import Clock
    clock = Clock()
    store = RS.StewardStore(tmp_path, clock=clock, pid_alive=lambda pid: True, resolve_head=lambda b: None,
                            default_ttl_s=60)
    store.claim(STEWARD, "noctusai-51", claude_pid=100)
    clock.t += 10_000  # past the TTL: the lease is stale
    r = RS.tool_refusal("noctus.dev.task_branch", {"action": "enqueue", "confirm": True}, store=store,
                        env={RS.SESSION_ENV: PEER})
    assert r["status"] == "refused_not_steward"
    rows = _rows("steward:enqueue:")
    assert [(x["gate"], x["outcome"], x["kind"]) for x in rows] == [("steward:enqueue:stale_lease", "deny", "rejection")]


# ------------------------------------------------------------------------------------ (c) scoped verdicts
_WORKFLOW = "name: t\njobs:\n  t:\n    steps:\n      - name: k\n        run: python mcp/noctusai/cli.py {flag}\n"


def _scoped_world(world, flag: str, cli_body: str):
    """A real repo whose head ships a one-keeper CI workflow + a `cli.py` the keeper run executes."""
    wt = world.worktree()
    (wt / ".github" / "workflows").mkdir(parents=True)
    (wt / ".github" / "workflows" / "test.yml").write_text(_WORKFLOW.format(flag=flag))
    (wt / "mcp" / "noctusai").mkdir(parents=True)
    (wt / "mcp" / "noctusai" / "cli.py").write_text(cli_body)
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    return world.commit(wt, "feat: scoped")


def _admit():
    import contextlib

    @contextlib.contextmanager
    def admit(job):
        yield type("A", (), {"admitted": True, "verdict": "ok"})()
    return admit


def test_a_scoped_stage_timeout_is_a_scoped_deny_naming_the_gate_and_never_a_pass(world):
    """The REAL `export_ci_parity_check` on a real repo; the only injections are the documented `admit=` /
    `timeout=` seams, and a keeper that really sleeps past the 1 s stage budget (and its x1.5 retry)."""
    head = _scoped_world(world, "--check-slow", "import time\ntime.sleep(60)\n")
    res = RS.export_ci_parity_check(world.repo, timeout=1, admit=_admit(), verdict_store=world.verdict_store)("feat/x", head)
    assert res["ok"] is False and "UNMEASURED" in res["detail"]
    rows = _rows("scoped:")
    assert [(r["gate"], r["outcome"], r["target"], r["kind"]) for r in rows] == \
        [("scoped:ci_parity:keeper:--check-slow", "deny", "feat/x", "rejection")]
    assert "timed out" in rows[0]["reason"]


def test_a_red_scoped_stage_is_a_deny_and_a_green_one_is_its_pass(world):
    head = _scoped_world(world, "--check-red", "import sys\nsys.exit(3)\n")
    res = RS.export_ci_parity_check(world.repo, timeout=60, admit=_admit(), verdict_store=world.verdict_store)("feat/x", head)
    assert res["ok"] is False and "RED" in res["detail"]
    assert [(r["gate"], r["outcome"]) for r in _rows("scoped:")] == [("scoped:ci_parity:keeper:--check-red", "deny")]
    assert "exit 3" in _rows("scoped:")[0]["reason"]


def test_a_green_scoped_stage_records_a_pass(world):
    head = _scoped_world(world, "--check-ok", "pass\n")
    res = RS.export_ci_parity_check(world.repo, timeout=60, admit=_admit(), verdict_store=world.verdict_store)("feat/x", head)
    assert res["ok"] is True, res
    assert [(r["gate"], r["outcome"]) for r in _rows("scoped:")] == [("scoped:ci_parity:keeper:--check-ok", "pass")]


def test_a_scoped_run_that_never_got_to_run_a_stage_is_still_counted_as_unmeasured(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    head = world.commit(wt, "feat: no workflow")  # the head has no test.yml: nothing to derive the CI set from
    res = RS.export_ci_parity_check(world.repo, timeout=60, admit=_admit(), verdict_store=world.verdict_store)("feat/x", head)
    assert res["ok"] is False and "UNMEASURED" in res["detail"]
    assert [(r["gate"], r["outcome"]) for r in _rows("scoped:")] == [("scoped:ci_parity:unmeasured", "deny")]


# ----------------------------------------------------- item 3: the primary index is never written (real git)
def _index_identity(repo: Path) -> tuple:
    idx = Path(sh(repo, "git", "rev-parse", "--path-format=absolute", "--git-path", "index"))
    st = idx.stat()
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def test_deliverable_and_enqueue_never_write_the_index_of_the_checkout_they_run_from(world):
    """`index.lock` left in the primary (2026-11-14, 3x): a plain `git status` refreshes (WRITES) the index under
    `index.lock`, and a git killed by a timeout/pkill mid-refresh leaves the lock behind. The deliverable path must not
    take that lock at all: with the primary's files stat-dirty (a refresh would have something to rewrite), run the
    contract and the enqueue and require the index to be byte-for-byte untouched and no lock to exist."""
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    primary_file = world.repo / "src" / "a.txt"
    os.utime(primary_file, (1_000_000_000, 1_000_000_000))  # stat-dirty, content unchanged: a refresh would rewrite the index
    before = _index_identity(world.repo)
    git_dir = Path(sh(world.repo, "git", "rev-parse", "--path-format=absolute", "--git-dir"))
    assert world.deliverable()["ok"]
    assert world.enqueue(confirm=False)["status"] == "planned"
    assert world.enqueue()["status"] == "queued"
    assert not (git_dir / "index.lock").exists()
    assert _index_identity(world.repo) == before


def test_every_status_in_the_deliverable_path_is_run_without_optional_locks():
    """The structural half: `status` through the read-only git seam must carry --no-optional-locks, or it is refused
    (a plain `git status` is a WRITE of the index; the allowlist alone let it through)."""
    seen: list[tuple] = []
    guarded = RS._ReadOnlyGit(lambda *a, cwd=None: seen.append(a) or (0, "", ""))
    with pytest.raises(ValueError, match="no-optional-locks"):
        guarded("status", "--porcelain")
    guarded("--no-optional-locks", "status", "--porcelain")
    assert seen == [("--no-optional-locks", "status", "--porcelain")]


def test_a_plain_git_status_really_does_rewrite_the_index_which_is_why(world):
    os.utime(world.repo / "src" / "a.txt", (1_000_000_000, 1_000_000_000))
    before = _index_identity(world.repo)
    subprocess.run(["git", "status", "--porcelain"], cwd=world.repo, check=True, capture_output=True)
    assert _index_identity(world.repo) != before  # the write the guard exists to prevent
    os.utime(world.repo / "src" / "a.txt", (1_000_000_001, 1_000_000_001))
    before = _index_identity(world.repo)
    subprocess.run(["git", "--no-optional-locks", "status", "--porcelain"], cwd=world.repo, check=True, capture_output=True)
    assert _index_identity(world.repo) == before


def test_the_export_repository_is_never_the_checkout_that_started_the_run(world, tmp_path, monkeypatch):
    """The only index-WRITING git call on the scoped path is `_git_init_export` (`git add -A` + `git commit` of the export).
    A process started from a hook/editor carries GIT_DIR / GIT_INDEX_FILE; with those inherited, `git add -A` (cwd = the
    export) stages the export into THE INHERITED repository's index and commits it there - the primary's `index.lock` and
    a stray commit. Run it with the primary's location variables set: the primary must be untouched, the export must get
    its own repository and its own single commit."""
    (world.repo / "src" / "keep.txt").write_text("k\n")  # a tracked, committed file so the primary has a real index
    world.commit(world.repo, "keep")
    exp = tmp_path / "export"
    (exp / "pkg").mkdir(parents=True)
    (exp / "pkg" / "m.py").write_text("x = 1\n")
    primary_git = Path(sh(world.repo, "git", "rev-parse", "--path-format=absolute", "--git-dir"))
    head_before = sh(world.repo, "git", "rev-parse", "HEAD")
    idx_before = _index_identity(world.repo)
    monkeypatch.setenv("GIT_DIR", str(primary_git))
    monkeypatch.setenv("GIT_INDEX_FILE", str(primary_git / "index"))
    monkeypatch.setenv("GIT_WORK_TREE", str(world.repo))
    assert RS._git_init_export(exp, "a" * 40) is None
    for k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        monkeypatch.delenv(k)
    assert not (primary_git / "index.lock").exists()
    assert _index_identity(world.repo) == idx_before
    assert sh(world.repo, "git", "rev-parse", "HEAD") == head_before
    assert sh(world.repo, "git", "status", "--porcelain") == ""  # nothing of the export leaked into the primary
    assert (exp / ".git").is_dir()
    assert sh(exp, "git", "rev-list", "--count", "HEAD") == "1"
    assert "pkg/m.py" in sh(exp, "git", "ls-files").splitlines()


# ------------------------------------------- budget overrides that silently did not take effect (2026-11-14)
def test_budget_helpers_say_when_an_override_is_clamped_or_matches_nothing(monkeypatch):
    from tools.noctus.dev import gate_budget as gb
    monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", '{"ci_parity:suite:seed": 5, "ci_parity:suite:product:sw": 3600, "ci_parity:suite:x/": 9}')
    ids = ["ci_parity:suite:seed:seed/lib/backend", "ci_parity:suite:product:sw", "ci_parity:suite:x/y"]
    assert gb.unknown_override_keys(ids) == ["ci_parity:suite:seed"]  # abbreviated id: no exact match, no `:`/`/` prefix
    note = gb.clamp_note("ci_parity:suite:product:sw")
    assert "3600" in note and str(gb.MAX_GATE_BUDGET_S) in note and "NOCTUS_GATE_MAX_BUDGET_S" in note
    assert gb.clamp_note("ci_parity:suite:x/y") is None  # honoured


def test_a_scoped_run_reports_unknown_and_clamped_budget_keys(world, monkeypatch):
    monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", '{"ci_parity:suite:seed": 5, "ci_parity:keeper:--check-ok": 99999}')
    head = _scoped_world(world, "--check-ok", "pass\n")
    res = RS.export_ci_parity_check(world.repo, admit=_admit(), verdict_store=world.verdict_store)("feat/x", head)
    assert res["ok"] is True, res
    joined = " ".join(res["budget_notes"])
    assert "`ci_parity:suite:seed` matches no stage" in joined and "ci_parity:keeper:--check-ok" in joined
    assert "clamped" in joined and "budget notes:" in res["detail"]
