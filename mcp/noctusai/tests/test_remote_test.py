"""remote_test: a heavy test run goes to GitHub by construction, with loud reasoned fallbacks.

Real git (a bare origin + a clone in tmp dirs); `gh` is a REAL recorder script on PATH (no monkeypatching of our code).
"""
from __future__ import annotations

import fcntl
import io
import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from tools.noctus.dev import ci_verdict as cv
from tools.noctus.dev import hw_admission as hw
from tools.noctus.dev import remote_test as rt

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github/workflows/remote-test.yml"
ACTION = REPO / ".github/actions/python-test-env/action.yml"
REPO_NAME = "acme/noc"

GH = textwrap.dedent('''\
    #!__PY__
    import json, os, sys
    st = os.environ["GH_STATE"]
    S = json.load(open(st))
    a = sys.argv[1:]
    S.setdefault("calls", []).append(a)
    def save(): json.dump(S, open(st, "w"))
    if a[:1] == ["api"]:
        path = [x for x in a[1:] if not x.startswith("-")][0]
        if path == "rate_limit":
            save(); print(json.dumps(S.get("rate", {"resources": {"core": {"remaining": 4000, "limit": 5000, "reset": 0}}}))); sys.exit(0)
        if path.endswith("/actions/workflows/remote-test.yml"):
            save()
            if S.get("workflow_exists", True):
                print("{}"); sys.exit(0)
            print("gh: Not Found (HTTP 404)", file=sys.stderr); sys.exit(1)
        if "/workflows/remote-test.yml/runs" in path:
            save(); print(json.dumps({"workflow_runs": S.get("runs", [])})); sys.exit(0)
        if "/actions/runs/" in path:
            rid = path.rsplit("/", 1)[1]
            run = [r for r in S.get("runs", []) if str(r["id"]) == rid][0]
            run = {**run, "status": "completed", "conclusion": S.get("conclusion", "success"),
                   "head_sha": S.get("final_head_sha", run["head_sha"])}
            save()
            if "-i" in a:
                if S.get("force_403"):
                    print("HTTP/2.0 403 Forbidden\\n\\n{}"); print("gh: API rate limit exceeded (HTTP 403)", file=sys.stderr); sys.exit(1)
                if any("If-None-Match" in x for x in a) and S.get("etag_304"):
                    print("HTTP/2.0 304 Not Modified\\n"); sys.exit(1)
                print('HTTP/2.0 200 OK\\nEtag: "e1"\\n'); print(json.dumps(run)); sys.exit(0)
            print(json.dumps(run)); sys.exit(0)
    if a[:2] == ["workflow", "run"]:
        inputs = {x.split("=", 1)[0]: x.split("=", 1)[1] for i, x in enumerate(a) if i and a[i - 1] == "-f"}
        S.setdefault("dispatches", []).append({"workflow": a[2], "ref": a[a.index("--ref") + 1], "inputs": inputs})
        S.setdefault("runs", []).append({"id": 5001, "head_sha": S["tip"], "event": "workflow_dispatch",
                                          "html_url": "https://github.com/acme/noc/actions/runs/5001"})
        save(); sys.exit(0)
    if a[:2] == ["run", "watch"]:
        save(); print("recorder: `gh run watch` must never be called", file=sys.stderr); sys.exit(3)
    if a[:2] == ["run", "view"]:
        save(); sys.stdout.write(S.get("log", "")); sys.exit(0)
    save(); print("recorder: unhandled " + " ".join(a), file=sys.stderr); sys.exit(2)
''')


def _git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


def _log(code, step="Run test command"):
    lines = ["collected 2 items", "FAILED tests/test_a.py::test_x - assert 1 == 2" if code else "2 passed in 0.1s",
             f"{rt.MARKER}{code}"]
    return "\n".join(f"Remote test\t{step}\t2026-11-16T10:00:0{i}Z {ln}" for i, ln in enumerate(lines))


class World:
    def __init__(self, work, head, state, client):
        self.dir, self.head, self.state, self.client = work, head, state, client
        self.rows: list[dict] = []
        self.err = io.StringIO()

    def set(self, **kw):
        self.state.write_text(json.dumps({**json.loads(self.state.read_text()), **kw}))

    def st(self):
        return json.loads(self.state.read_text())

    def run(self, argv=None, mode=None):
        argv = argv or ["bash", "-c", "cd sub && pytest t.py -q"]
        return rt.try_remote("pytest:sub", argv, cwd=str(self.dir), mode=mode, client=self.client, log=self.rows.append,
                             err=self.err, sleep=lambda _s: None)


@pytest.fixture()
def world(tmp_path, monkeypatch):
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "feat/x", str(bare))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(bare), str(work))
    _git(work, "checkout", "-q", "-b", "feat/x")
    (work / "sub").mkdir()
    (work / "sub" / "t.py").write_text("def test_a():\n    assert True\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "origin", "feat/x")
    head = _git(work, "rev-parse", "HEAD")
    binp = tmp_path / "bin"
    binp.mkdir()
    gh = binp / "gh"
    gh.write_text(GH.replace("__PY__", sys.executable))
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    state = tmp_path / "gh-state.json"
    state.write_text(json.dumps({"tip": head, "log": _log(0)}))
    monkeypatch.setenv("GH_STATE", str(state))
    monkeypatch.setenv("PATH", f"{binp}{os.pathsep}{os.environ['PATH']}")
    # a recorder that cannot run would silently fall through PATH to the REAL gh (and spend real quota): prove it runs
    probe = subprocess.run(["gh", "api", "rate_limit"], capture_output=True, text=True, check=False)
    assert probe.returncode == 0 and '"remaining": 4000' in probe.stdout, f"recorder gh is not the gh on PATH: {probe.stdout[:80]}"
    monkeypatch.delenv("NOCTUS_HW_SLOT_HELD", raising=False)
    monkeypatch.delenv(rt.ENV_BACKEND, raising=False)
    return World(work, head, state, cv.RealGithubClient(str(work), repo=REPO_NAME))


class TestRemoteRun:
    def test_pushed_clean_head_dispatches_exactly_the_command_and_returns_its_exit_code(self, world, capsys):
        world.set(log=_log(3))
        assert world.run() == 3
        assert world.st()["dispatches"] == [{"workflow": "remote-test.yml", "ref": "feat/x",
                                             "inputs": {"ref": "feat/x", "sha": world.head, "workdir": "sub",
                                                        "cmd": "pytest t.py -q"}}]
        assert "FAILED tests/test_a.py::test_x" in capsys.readouterr().out
        err = world.err.getvalue()
        assert "REMOTE-TEST START" in err and "actions/runs/5001" in err and "REMOTE-TEST ... run 5001: completed" in err
        row = world.rows[-1]
        assert (row["event"], row["backend"], row["run_id"], row["sha"], row["outcome"]["exit_code"]) == \
               ("remote_run", "remote", "5001", world.head, 3) and row["wall_s"] >= 0

    def test_green_is_exit_zero_and_repo_root_workdir_is_dot(self, world):
        assert world.run(["python", "-m", "pytest", "sub/t.py"]) == 0
        inputs = world.st()["dispatches"][0]["inputs"]
        assert inputs["workdir"] == "." and inputs["cmd"] == "python -m pytest sub/t.py"

    def test_absolute_path_under_the_worktree_is_made_relative_to_the_workdir(self, world):
        assert world.run(["bash", "-c", f"cd sub && pytest {world.dir}/sub/t.py"]) == 0
        assert world.st()["dispatches"][0]["inputs"]["cmd"] == "pytest t.py"

    def test_run_judged_at_another_sha_is_unmeasured_never_green(self, world):
        world.set(final_head_sha="f" * 40)
        assert world.run() == rt.EX_TEMPFAIL
        assert "judged ffffffff" in world.err.getvalue() and world.rows[-1]["outcome"]["conclusion"] == "sha_mismatch"

    def test_no_exit_marker_is_unmeasured(self, world):
        world.set(log=_log(0, step="Install dependencies"), conclusion="failure")
        assert world.run() == rt.EX_TEMPFAIL
        assert "UNMEASURED" in world.err.getvalue()


class TestLoudFallbacks:
    def _declined(self, world, part, argv=None):
        assert world.run(argv) is None
        assert "REMOTE-TEST FALLBACK: " in world.err.getvalue() and part in world.err.getvalue()
        assert world.rows[-1]["event"] == "remote_fallback" and part in world.rows[-1]["reason"]
        assert "dispatches" not in world.st()

    def test_unpushed_head(self, world):
        (world.dir / "sub" / "t.py").write_text("def test_a():\n    assert 1\n")
        _git(world.dir, "commit", "-qam", "more")
        self._declined(world, "HEAD not pushed")

    def test_uncommitted_changes(self, world):
        (world.dir / "sub" / "t.py").write_text("def test_a():\n    assert 2\n")
        self._declined(world, "uncommitted changes")

    def test_workflow_missing_on_github(self, world):
        world.set(workflow_exists=False)
        self._declined(world, "remote-test.yml is missing on GitHub")

    def test_gh_not_installed(self, world, monkeypatch):
        import shutil
        git_dir = str(Path(shutil.which("git")).parent)  # PATH that still finds git but not the recorder
        monkeypatch.setenv("PATH", git_dir)
        if shutil.which("gh"):
            pytest.skip("a real gh shares the directory with git")
        self._declined(world, "GitHub unavailable")

    def test_env_assignment_compound_and_detached(self, world):
        self._declined(world, "env assignment", ["bash", "-c", "FOO=1 pytest sub/t.py"])
        self._declined(world, "compound command", ["bash", "-c", "pytest sub/t.py && echo done"])
        _git(world.dir, "checkout", "-q", "--detach")
        self._declined(world, "detached HEAD")

    def test_disallowed_runner_is_declined_loudly(self, world):
        self._declined(world, "not an allowed test runner", ["bash", "-c", "uv run pytest sub/t.py"])

    def test_inherited_slot_stays_local(self, world, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_SLOT_HELD", "/outer")
        self._declined(world, "already holds a local slot")

    def test_build_is_local_by_design_and_silent(self, world):
        assert world.run(["bash", "-c", "cd sub && vite build"]) is None
        assert world.err.getvalue() == "" and world.rows == []

    def test_local_flag_and_env(self, world, monkeypatch):
        assert world.run(mode="local") is None and "local backend requested" in world.err.getvalue()
        monkeypatch.setenv(rt.ENV_BACKEND, "local")
        assert world.run() is None and "dispatches" not in world.st()

    def test_remote_mode_never_falls_back(self, world):
        world.set(workflow_exists=False)
        assert world.run(mode="remote") == rt.EX_TEMPFAIL
        assert "forbids a local fallback" in world.err.getvalue() and world.rows[-1]["backend"] == "refused"


class TestAllowlist:
    @pytest.mark.parametrize("argv", [["pytest", "-q"], ["python", "-m", "pytest", "x"], ["vitest", "run"],
                                      ["npx", "vitest", "run"], ["npm", "test"],
                                      ["npm", "run", "test", "--", "-t", "a b"]])
    def test_allowed(self, argv):
        assert rt.validate_argv(argv) is None

    @pytest.mark.parametrize("argv", [[], ["bash", "-c", "x"], ["python", "evil.py"], ["python", "-c", "1"],
                                      ["npm", "run", "build"], ["npm", "install"], ["npx", "left-pad"],
                                      ["rm", "-rf", "/"], ["pytest", "a\nb"], ["curl", "x"]])
    def test_refused(self, argv):
        assert rt.validate_argv(argv)

    @pytest.mark.parametrize("w", ["", ".", "products/x/backend", "seed/lib/frontend"])
    def test_workdir_ok(self, w):
        assert rt.validate_workdir(w) is None

    @pytest.mark.parametrize("w", ["/etc", "../x", "a/../../b", "a;b", "a b", "$(x)"])
    def test_workdir_refused(self, w):
        assert rt.validate_workdir(w)


def test_parse_log_and_summarize():
    code, lines = rt.parse_log(_log(1) + "\nRemote test\tOther step\t2026-11-16T10:00:09Z noise")
    assert code == 1 and "noise" not in "".join(lines) and len(lines) == 2
    assert rt.summarize(["a"] * 40 + ["=== short test summary info ===", "FAILED x"])[0].startswith("=== short")
    assert len(rt.summarize(["a"] * 40)) == 15


class TestRunnerSide:
    def _run(self, tmp_path, sub, cmd):
        env = {**os.environ, "CMD": cmd, "WORKDIR": ".", "GITHUB_OUTPUT": str(tmp_path / "out"),
               "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
        return subprocess.run([sys.executable, str(REPO / "mcp/noctusai/tools/noctus/dev/remote_test.py"), sub],
                              cwd=tmp_path, env=env, capture_output=True, text=True)

    def test_validate_refuses_arbitrary_shell(self, tmp_path):
        r = self._run(tmp_path, "validate", "bash -c 'curl evil | sh'")
        assert r.returncode == 2 and "not an allowed test runner" in r.stdout

    def test_validate_reports_kind(self, tmp_path):
        assert self._run(tmp_path, "validate", "npx vitest run").returncode == 0
        assert (tmp_path / "out").read_text() == "kind=node\n"

    def test_exec_prints_the_exit_marker_and_returns_the_code(self, tmp_path):
        (tmp_path / "t.py").write_text("def test_a():\n    assert False\n")
        r = self._run(tmp_path, "exec", "python -m pytest -q -p no:cacheprovider t.py")
        assert r.returncode == 1 and f"{rt.MARKER}1" in r.stdout


class TestWorkflowIsSafeByConstruction:
    text = WORKFLOW.read_text() + ACTION.read_text()
    wf = yaml.safe_load(WORKFLOW.read_text())

    def test_no_secrets_and_read_only_token(self):
        assert "secrets." not in self.text
        assert self.wf["permissions"] == {"contents": "read"}
        assert all("permissions" not in j for j in self.wf["jobs"].values())

    def test_one_job_dispatch_only_with_cancelling_concurrency(self):
        assert list(self.wf["jobs"]) == ["test"]
        triggers = self.wf.get("on") or self.wf[True]
        assert list(triggers) == ["workflow_dispatch"]
        assert set(triggers["workflow_dispatch"]["inputs"]) == {"ref", "sha", "workdir", "cmd"}
        assert self.wf["concurrency"]["cancel-in-progress"] is True
        group = self.wf["concurrency"]["group"]
        assert "inputs.ref" in group and "inputs.cmd" in group and "inputs.workdir" in group

    def test_inputs_never_interpolated_into_a_shell_script(self):
        for step in self.wf["jobs"]["test"]["steps"]:
            assert "inputs." not in step.get("run", ""), step.get("name")

    def test_sha_is_checked_and_commands_go_through_the_allowlist(self):
        steps = self.wf["jobs"]["test"]["steps"]
        names = [s.get("name", "") for s in steps]
        assert (names.index("Refuse a sha that is not the ref's head") < names.index("Validate the command (allowlist)")
                < names.index(rt.STEP_NAME))
        runs = " ".join(s.get("run", "") for s in steps)
        assert "remote_test.py validate" in runs and "remote_test.py exec" in runs


class TestSlotSweep:
    @pytest.fixture()
    def slots(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_SLOT_DIR", str(tmp_path / "slots"))
        d = tmp_path / "slots"
        d.mkdir()
        return d

    def test_unheld_lock_files_at_or_beyond_max_heavy_are_removed(self, slots):
        for i in range(4):
            (slots / f"slot-{i}.lock").write_text("{}")
        out = hw.sweep_excess_slots(2)
        assert sorted(out["swept"]) == ["slot-2.lock", "slot-3.lock"] and out["held_beyond_max"] == []
        assert sorted(p.name for p in slots.glob("slot-*.lock")) == ["slot-0.lock", "slot-1.lock"]

    def test_a_live_holder_beyond_max_is_reported_never_removed(self, slots):
        f = slots / "slot-2.lock"
        with f.open("a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out = hw.sweep_excess_slots(2)
        assert out == {"swept": [], "held_beyond_max": ["slot-2.lock"]} and f.exists()

    def test_taking_a_slot_sweeps(self, slots):
        (slots / "slot-5.lock").write_text("{}")
        got = hw._try_slot(1, "j")
        assert got is not None and not (slots / "slot-5.lock").exists()
        got[0].close()


class TestTelemetry:
    def test_report_counts_remote_vs_local_and_fallback_reasons(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_LOG", str(tmp_path / "log.ndjson"))
        hw._log({"event": "remote_run", "backend": "remote", "job": "pytest:x", "wall_s": 40.0, "outcome": {"exit_code": 0}})
        hw._log({"event": "remote_run", "backend": "remote", "job": "pytest:x", "wall_s": 20.0, "outcome": {"exit_code": 1}})
        hw._log({"event": "remote_fallback", "backend": "local", "job": "pytest:x", "reason": "HEAD not pushed"})
        b = hw.report()["backends"]
        assert (b["remote_runs"], b["remote_wall_s"], b["remote_failed"]) == (2, 60.0, 1)
        assert b["fallbacks"] == {"HEAD not pushed": 1} and b["local_runs"] == 0


class TestGithubQuota:
    """GitHub first; the local slot when GitHub is out of quota; never `gh run watch`, never stop work."""

    def test_remote_run_records_quota_telemetry_and_never_uses_gh_run_watch(self, world):
        assert world.run() == 0
        assert all(c[:2] != ["run", "watch"] for c in world.st()["calls"])
        row = world.rows[-1]
        assert row["rate_remaining_start"] == 4000 and row["api_calls"] >= 4 and "rate_remaining_end" in row

    def test_quota_below_the_floor_declines_to_the_local_slot_naming_remaining_and_reset(self, world):
        world.set(rate={"resources": {"core": {"remaining": 12, "limit": 5000, "reset": 1700000000}}})
        assert world.run() is None
        err = world.err.getvalue()
        assert "REMOTE-TEST FALLBACK: github-quota 12/5000 resets 22:13Z" in err and "local slot" in err
        assert "dispatches" not in world.st() and world.rows[-1]["event"] == "remote_fallback"

    def test_quota_below_the_floor_in_remote_mode_is_exit_75(self, world):
        world.set(rate={"resources": {"core": {"remaining": 0, "limit": 5000, "reset": 1700000000}}})
        assert world.run(mode="remote") == rt.EX_TEMPFAIL and "dispatches" not in world.st()

    def test_403_mid_watch_falls_back_locally_and_names_the_orphaned_run(self, world):
        world.set(force_403=True)
        assert world.run() is None
        err = world.err.getvalue()
        assert "github-quota-midwatch" in err and "actions/runs/5001" in err
        row = world.rows[-1]
        assert row["event"] == "remote_fallback" and row["reason"] == "github-quota-midwatch" and "5001" in row["orphaned_run_url"]

    def test_403_mid_watch_in_remote_mode_keeps_exit_75(self, world):
        world.set(force_403=True)
        assert world.run(mode="remote") == rt.EX_TEMPFAIL

    def test_unreadable_meter_does_not_block_work(self, world):
        world.set(rate="not json")
        assert world.run() == 0 and world.rows[-1]["rate_remaining_start"] is None


class TestWatchPolling:
    """`wait_for_run` through the real client with an injected clock: backoff, ETag, quota sleep. No live gh."""

    def _client(self, responses):
        calls = []

        def runner(args, cwd=None, timeout=60):
            calls.append(args)
            return responses(args)

        return cv.RealGithubClient("/x", runner=runner, repo="acme/noc"), calls

    def test_polls_one_endpoint_with_backoff_60_120_300_and_etag(self):
        n = {"i": 0}

        def resp(args):
            if args[:2] == ["gh", "api"] and "-i" in args:
                n["i"] += 1
                if n["i"] > 1:
                    assert "If-None-Match: \"e1\"" in args
                if n["i"] == 6:
                    return 0, 'HTTP/2.0 200 OK\nEtag: "e2"\n\n{"status":"completed","conclusion":"success"}', ""
                if n["i"] > 1:
                    return 1, "HTTP/2.0 304 Not Modified\n\n", ""
                return 0, 'HTTP/2.0 200 OK\nEtag: "e1"\n\n{"status":"in_progress"}', ""
            raise AssertionError(args)

        c, calls = self._client(resp)
        sleeps, lines, t = [], [], {"t": 0.0}
        done = c.watch("7", lines.append, 3600, sleep=lambda s: (sleeps.append(s), t.__setitem__("t", t["t"] + s)),
                       clock=lambda: t["t"])
        assert done and sleeps == [60.0, 120.0, 300.0, 300.0, 300.0]
        assert len(calls) == 6 and c.api_calls == 6 and lines == ["run 7: in_progress", "run 7: completed (success)"]

    def test_timeout_returns_false_without_polling_forever(self):
        c, calls = self._client(lambda a: (0, 'HTTP/2.0 200 OK\n\n{"status":"queued"}', ""))
        t = {"t": 0.0}
        assert c.watch("7", lambda _l: None, 100, sleep=lambda s: t.__setitem__("t", t["t"] + s), clock=lambda: t["t"]) is False
        assert len(calls) <= 3

    def test_rate_limit_sleeps_until_the_reset_loudly_then_resumes(self):
        state = {"i": 0}

        def resp(args):
            if args[2] == "rate_limit":
                return 0, '{"resources":{"core":{"remaining":0,"limit":5000,"reset":%d}}}' % int(__import__("time").time() + 120), ""
            state["i"] += 1
            if state["i"] == 1:
                return 1, "", "gh: API rate limit exceeded for user (HTTP 403)"
            return 0, 'HTTP/2.0 200 OK\n\n{"status":"completed","conclusion":"success"}', ""

        c, calls = self._client(resp)
        sleeps, lines = [], []
        assert c.watch("7", lines.append, 3600, sleep=sleeps.append, clock=lambda: 0.0)
        assert 100 < sleeps[0] < 130 and any(l.startswith("GITHUB QUOTA") and "sleeping" in l for l in lines)
        assert c.free_calls == 1

    def test_quota_pause_is_zero_when_healthy_or_unreadable(self):
        ok = lambda a, cwd=None: (0, '{"resources":{"core":{"remaining":900,"limit":5000,"reset":9}}}', "")
        low = lambda a, cwd=None: (0, '{"resources":{"core":{"remaining":3,"limit":5000,"reset":1000}}}', "")
        bad = lambda a, cwd=None: (1, "", "boom")
        assert cv.quota_pause_s(ok)[0] == 0.0 and cv.quota_pause_s(bad)[0] == 0.0
        assert cv.quota_pause_s(low, now=lambda: 400.0)[0] == 605.0


class TestGhCallsViaSeam:
    def _scan(self, tmp_path, src, name="mcp/x/tools/a.py"):
        from tools.noctus.dev.compliance import check_gh_calls_via_seam
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(src)
        return check_gh_calls_via_seam(repo_root=tmp_path)

    def test_gh_run_watch_is_forbidden_everywhere(self, tmp_path):
        out = self._scan(tmp_path, 'import subprocess\nsubprocess.run(["gh", "run", "watch", "1"])\n')
        assert any("gh run watch" in i["issue"] for i in out)

    def test_new_gh_argv_outside_the_seam_is_flagged_and_clean_code_is_not(self, tmp_path):
        assert self._scan(tmp_path, 'x = ["gh", "api", "rate_limit"]\n')[0]["severity"] == "high"
        assert self._scan(tmp_path, "x = ['git', 'status']\n", name="mcp/x/tools/b.py") != []  # a.py still dirty
        (tmp_path / "mcp/x/tools/a.py").unlink()
        assert self._scan(tmp_path, "x = ['git', 'status']\n", name="mcp/x/tools/b.py") == []

    def test_the_repo_is_clean(self):
        from tools.noctus.dev.compliance import check_gh_calls_via_seam
        assert [i for i in check_gh_calls_via_seam() if i["severity"] != "warning"] == []
