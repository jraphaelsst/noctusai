"""CLI/toolkit gaps closed 2026-11-05: merge-queue watch + error JSON, --tunnel-config,
render worktree-awareness, the staged ledger<->PROJECT-HISTORY.md gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cli  # noqa: E402
from tools.noctus.dev import merge_queue as mq  # noqa: E402
from tools.noctus.dev.history import check_project_history_staged, render_project_history  # noqa: E402


def _entry(slug, sha, state, desc="", url=""):
    return {"slug": slug, "ref": f"mq/{slug}--{sha[:7]}", "sha": sha,
            "verdict": {"state": state, "description": desc, "url": url}}


def _snap(*entries):
    return {"status": "ok", "dev": "d" * 40, "count": len(entries), "entries": list(entries)}


def _run_watch(seq, statuses, max_polls):
    """seq: list of snapshot dicts or Exceptions, one per list_fn call."""
    out, calls = [], iter(seq)

    def list_fn():
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    mq.watch(list_fn, lambda sha: statuses[sha], interval=1, sleep=lambda s: None,
             emit=out.append, max_polls=max_polls, attempts=1)
    return out


A, B = "a" * 40, "b" * 40


def test_watch_reports_state_change_and_leaving_entries():
    out = _run_watch(
        [_snap(_entry("a", A, "queued"), _entry("b", B, "queued")),
         _snap(_entry("a", A, "pending", "testing in batch", "http://u")),
         _snap()],
        {A: {"state": "landed", "dev_sha": "feedbeef1"}, B: {"state": "ejected", "description": "ejected (ci_red): x"}},
        3)
    assert "MQ a aaaaaaaaa -> pending: testing in batch http://u" in out
    assert "MQ-LEFT a aaaaaaaaa -> landed feedbeef1" in out
    assert any(l.startswith("MQ-LEFT b bbbbbbbbb -> ejected ejected (ci_red)") for l in out)
    # b left on poll 2 while a stayed
    assert out.count("MQ a aaaaaaaaa -> queued:") == 1


def test_watch_failing_read_between_snapshots_loses_no_transition():
    out = _run_watch(
        [_snap(_entry("a", A, "queued")),
         ValueError("substring not found"),
         {"status": "error", "error_type": "RuntimeError", "error": "git fetch failed"},
         _snap()],
        {A: {"state": "landed", "dev_sha": "cafe"}}, 4)
    errs = [l for l in out if l.startswith("MQ-WATCH-ERROR")]
    assert errs[0].startswith("MQ-WATCH-ERROR ValueError: substring not found")
    assert "RuntimeError" in errs[1]
    assert out[-1] == "MQ-LEFT a aaaaaaaaa -> landed cafe"


def test_watch_retries_a_not_yet_readable_final_verdict():
    out = _run_watch([_snap(_entry("a", A, "queued")), _snap(), _snap()],
                     {A: {"state": "unavailable"}}, 3)
    assert not any(l.startswith("MQ-LEFT") for l in out)  # still retrying, never dropped
    seen = {"n": 0}

    def st(sha):
        seen["n"] += 1
        return {"state": "landed", "dev_sha": "1"} if seen["n"] > 1 else {"state": "unavailable"}

    out2 = []
    calls = iter([_snap(_entry("a", A, "queued")), _snap(), _snap()])
    mq.watch(lambda: next(calls), st, interval=1, sleep=lambda s: None, emit=out2.append, max_polls=3)
    assert out2[-1] == "MQ-LEFT a aaaaaaaaa -> landed 1"


def test_watch_retries_transient_within_a_poll():
    calls = iter([OSError("flaky"), _snap(_entry("a", A, "queued"))])
    out, slept = [], []

    def list_fn():
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    mq.watch(list_fn, lambda s: {}, interval=60, sleep=slept.append, emit=out.append, max_polls=1, attempts=3)
    assert out == ["MQ a aaaaaaaaa -> queued:"] and slept == [1]


def _run_batches(batch_seq, polls):
    out, it = [], iter(batch_seq)

    def batches_fn():
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    mq.watch(lambda: _snap(), lambda s: {}, interval=1, sleep=lambda s: None, emit=out.append,
             max_polls=polls, attempts=1, batches_fn=batches_fn)
    return out


def _b(i, concl, branch="mq-candidate/9-1"):
    return {"id": i, "branch": branch, "conclusion": concl, "url": f"u{i}"}


def test_watch_reports_each_finished_batch_once_red_included_after_silent_baseline():
    out = _run_batches([[_b(1, "success")],
                        [_b(1, "success"), _b(2, "failure", "mq-candidate/9-2")],
                        [_b(1, "success"), _b(2, "failure", "mq-candidate/9-2"), _b(3, "cancelled", "mq-candidate/9-3")]],
                       polls=3)
    assert out == ["MQ-BATCH mq-candidate/9-2 -> failure u2", "MQ-BATCH mq-candidate/9-3 -> cancelled u3"]


def test_watch_batch_read_failure_is_reported_not_silent_and_keeps_the_baseline():
    out = _run_batches([[_b(1, "success")], RuntimeError("gh down"), [_b(1, "success"), _b(2, "failure")]], polls=3)
    assert out[0].startswith("MQ-WATCH-ERROR batches RuntimeError: gh down")
    assert out[1] == "MQ-BATCH mq-candidate/9-1 -> failure u2"


def test_completed_candidate_runs_filters_and_raises_on_failed_read():
    rows = [{"databaseId": 1, "headBranch": "mq-candidate/9-1", "status": "completed", "conclusion": "failure", "url": "u"},
            {"databaseId": 2, "headBranch": "mq-candidate/9-2", "status": "in_progress", "conclusion": "", "url": "v"},
            {"databaseId": 3, "headBranch": "dev", "status": "completed", "conclusion": "success", "url": "w"}]
    got = mq.completed_candidate_runs(run=lambda cmd, cwd=None: (0, json.dumps(rows), ""))
    assert got == [{"id": 1, "branch": "mq-candidate/9-1", "conclusion": "failure", "url": "u"}]
    try:
        mq.completed_candidate_runs(run=lambda cmd, cwd=None: (1, "", "HTTP 502"))
    except RuntimeError as exc:
        assert "HTTP 502" in str(exc)
    else:
        raise AssertionError("a failed gh read must raise, never read as an empty queue")


def test_queue_report_failure_is_a_json_error_object():
    def run(cmd, cwd=None, check=False):
        return 1, "", "fatal: could not read from remote"

    r = mq.queue_report("o/r", run=run, workdir=".")
    assert r["status"] == "error" and r["error_type"] == "RuntimeError"
    json.dumps(r)


def test_read_status_unparseable_gh_output_is_unavailable():
    r = mq.read_status("o/r", "a" * 40, run=lambda cmd, cwd=None: (0, "Welcome to gh\n{bad", ""))
    assert r["state"] == "unavailable"


def test_cli_flags_are_wired():
    p = cli.build_parser()
    a = p.parse_args(["--tunnel-config", "apply", "--tunnel-config-confirm"])
    assert a.tunnel_config == "apply" and a.tunnel_config_confirm is True
    assert p.parse_args(["--tunnel-config", "render"]).tunnel_config_confirm is False
    w = p.parse_args(["--merge-queue", "watch", "--merge-queue-interval", "5"])
    assert w.merge_queue == "watch" and w.merge_queue_interval == 5.0
    assert p.parse_args(["--check-project-history-staged"]).check_project_history_staged


def test_tunnel_config_cli_render_runs():
    r = subprocess.run([sys.executable, str(Path(cli.__file__)), "--tunnel-config", "render"],
                       capture_output=True, text=True, timeout=120, env={**__import__("os").environ, "NOCTUS_HOOK_QUIET": "1"})
    assert r.returncode == 0, r.stderr[-400:]
    assert json.loads(r.stdout)["ok"] is True


def _git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True).stdout


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "project-history").mkdir()
    return tmp_path


ROW = json.dumps({"slug": "s1", "status_at_close": "shipped", "short_summary": "x",
                  "dates": {"created": "2026-01-01", "closed": "2026-01-02"}, "token_count": {}})


def test_staged_gate_blocks_ledger_without_render_and_passes_with_it(tmp_path):
    repo = _repo(tmp_path)
    (repo / "project-history" / "ledger.ndjson").write_text(ROW + "\n")
    _git(repo, "add", "project-history/ledger.ndjson")
    r = check_project_history_staged(repo_root=repo)
    assert r["staged"] and r["drift"] and "render-project-history" in r["fix"]
    render_project_history(repo_root=repo)
    _git(repo, "add", "project-history/PROJECT-HISTORY.md")
    assert check_project_history_staged(repo_root=repo)["ok"]


def test_staged_gate_ignores_commits_not_staging_the_ledger(tmp_path):
    repo = _repo(tmp_path)
    (repo / "x.txt").write_text("x")
    _git(repo, "add", "x.txt")
    assert check_project_history_staged(repo_root=repo) == {"ok": True, "staged": False, "drift": False, "fix": ""}


def test_render_cli_defaults_to_invoking_worktree(tmp_path, monkeypatch):
    import settings
    from tools.noctus.dev import auto_improvement as ai
    monkeypatch.setattr(settings, "REPO_ROOT", tmp_path)
    assert ai.invoking_tree(None) == str(tmp_path)  # not the primary => the CLI passes it to render
    assert ai.invoking_tree("/explicit") == "/explicit"


def test_venv_reexec_decision(tmp_path):
    venv = tmp_path / "py"
    venv.write_text("")
    d = cli._venv_reexec_decision
    assert d(True, False, [venv]) == ("run", "")                      # deps importable: no reexec
    assert d(False, True, [venv]) == ("run", "")                      # loop guard
    assert d(False, False, [tmp_path / "none", venv]) == ("reexec", str(venv))  # falls to 2nd candidate
    action, msg = d(False, False, [tmp_path / "none"])
    assert action == "error" and str(tmp_path / "none") in msg and "pip install" in msg
