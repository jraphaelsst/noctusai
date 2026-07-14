"""Tests for the shared throttled + circuit-broken SSH chokepoint (`_vps_ssh`).

Context (the incident, 2026-06-30): a transient SSH blip made the deploy tooling
fire rapid repeated `ssh noctus-vps …` attempts, which trips the VPS's fail2ban
and self-extends the outage. `_vps_ssh.run_remote` is the single client-side
throttle + circuit-breaker every VPS tool now routes through.

ZERO real SSH, ZERO real sleep, ZERO real cache-dir: `_now` / `_sleep` /
`_state_path` / `_runner` are all injected. See memory
feedback_dont_machinegun_prod_edge_with_probes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import _vps_ssh as VSS  # noqa: E402


class FakeRunner:
    """Scripts (rc, stdout, stderr) per ssh attempt + records every call."""

    def __init__(self, scripted: list[tuple[int, str, str]]):
        self.scripted = list(scripted)
        self.calls: list[tuple[str, str]] = []  # (ssh_host, remote_cmd)

    def __call__(self, ssh_host, remote_cmd, connect_timeout, timeout):
        self.calls.append((ssh_host, remote_cmd))
        if not self.scripted:
            return 0, "", ""
        return self.scripted.pop(0)


class Clock:
    """Monotonic, test-driven clock. Reading does NOT advance; tests call
    `advance` explicitly so behaviour is deterministic."""

    def __init__(self, start: float = 1000.0):
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


@pytest.fixture
def sleeps():
    captured: list[float] = []
    return captured, (lambda s: captured.append(s))


@pytest.fixture
def state_path(tmp_path):
    return tmp_path / "throttle.json"


HOST = "noctus-vps"
OK = (0, "out", "")
CONN_FAIL = (255, "", "ssh: connect to host noctus-vps port 22: Operation timed out")
REMOTE_FAIL = (1, "", "fatal: not a git repository")


def _run(runner, clock, sleep, state_path, **kw):
    return VSS.run_remote(
        HOST, "echo hi",
        _now=clock, _sleep=sleep, _state_path=state_path, _runner=runner, **kw,
    )


# ── min inter-attempt interval ──────────────────────────────────────────────
def test_min_interval_second_call_sleeps_remainder(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "3")
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([OK, OK])

    _run(runner, clock, sleep, state_path)          # first call: last_attempt=0 → no sleep
    assert captured == []

    clock.advance(1.0)                               # only 1s elapsed; min interval is 3s
    _run(runner, clock, sleep, state_path)
    # second call must sleep the remaining ~2s before connecting
    assert len(captured) == 1
    assert captured[0] == pytest.approx(2.0)
    assert len(runner.calls) == 2                    # both eventually connected


def test_min_interval_no_sleep_once_elapsed(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "3")
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([OK, OK])

    _run(runner, clock, sleep, state_path)
    clock.advance(5.0)                               # more than the interval
    _run(runner, clock, sleep, state_path)
    assert captured == []                            # no throttle sleep needed


# ── circuit-breaker ─────────────────────────────────────────────────────────
def test_circuit_opens_after_n_connection_failures(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")   # isolate circuit logic from throttle
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_FAILS", "3")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_COOLDOWN", "600")
    captured, sleep = sleeps
    clock = Clock()
    # Each call does up to 2 attempts (one backed-off retry) — all connection fails.
    runner = FakeRunner([CONN_FAIL] * 8)

    for _ in range(3):
        rc, _o, _e = _run(runner, clock, sleep, state_path)
        assert rc == 255
    calls_before = len(runner.calls)

    # circuit is now OPEN — next call must NOT invoke the runner at all
    rc, out, err = _run(runner, clock, sleep, state_path)
    assert rc == 255 and out == ""
    assert "circuit OPEN" in err
    assert str(state_path) in err                    # operator can clear it
    assert len(runner.calls) == calls_before         # zero new ssh attempts


def test_circuit_reopens_only_after_cooldown(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_FAILS", "3")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_COOLDOWN", "600")
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([CONN_FAIL] * 20)

    for _ in range(3):
        _run(runner, clock, sleep, state_path)
    calls_after_open = len(runner.calls)

    # still inside cooldown → blocked, runner untouched
    clock.advance(599.0)
    rc, _o, err = _run(runner, clock, sleep, state_path)
    assert rc == 255 and "circuit OPEN" in err
    assert len(runner.calls) == calls_after_open

    # cooldown elapsed → a probe is allowed again (runner invoked)
    clock.advance(2.0)
    _run(runner, clock, sleep, state_path)
    assert len(runner.calls) > calls_after_open


def test_success_resets_streak_and_closes_circuit(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_FAILS", "3")
    captured, sleep = sleeps
    clock = Clock()
    # two connection-failing calls (streak=2, below threshold), then a success
    runner = FakeRunner([CONN_FAIL, CONN_FAIL, CONN_FAIL, CONN_FAIL, OK])

    _run(runner, clock, sleep, state_path)
    _run(runner, clock, sleep, state_path)
    rc, _o, _e = _run(runner, clock, sleep, state_path)
    assert rc == 0                                   # the success

    import json
    entry = json.loads(state_path.read_text())[HOST]
    assert entry["consecutive_failure_count"] == 0
    assert entry["circuit_open_until"] == 0.0


# ── failure classification: remote-nonzero-but-connected must NOT trip ───────
def test_remote_nonzero_does_not_trip_circuit(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_FAILS", "3")
    captured, sleep = sleeps
    clock = Clock()
    # the edge is healthy; the REMOTE command exits nonzero every time
    runner = FakeRunner([REMOTE_FAIL] * 6)

    for _ in range(6):
        rc, _o, err = _run(runner, clock, sleep, state_path)
        assert rc == 1                               # forwarded remote exit code
        assert "circuit OPEN" not in err             # never blocked

    import json
    entry = json.loads(state_path.read_text())[HOST]
    assert entry["consecutive_failure_count"] == 0   # streak never advanced
    assert entry["circuit_open_until"] == 0.0
    assert len(runner.calls) == 6                     # every call genuinely connected


def test_connection_failure_does_one_backed_off_retry(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "3")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_FAILS", "99")  # don't open during this test
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([CONN_FAIL, OK])             # first attempt fails, retry succeeds

    rc, _o, _e = _run(runner, clock, sleep, state_path)
    assert rc == 0                                   # the retry's success is returned
    assert len(runner.calls) == 2                    # exactly two attempts (≤2 per call)
    # the retry slept the backoff interval once
    assert captured and captured[-1] == pytest.approx(3.0)


# ── force escape hatch ──────────────────────────────────────────────────────
def test_force_bypasses_open_circuit(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_FAILS", "3")
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([CONN_FAIL] * 6 + [OK])

    for _ in range(3):
        _run(runner, clock, sleep, state_path)       # open the circuit
    calls_after_open = len(runner.calls)

    # without force: blocked
    rc, _o, err = _run(runner, clock, sleep, state_path)
    assert "circuit OPEN" in err
    assert len(runner.calls) == calls_after_open

    # with force=True: bypasses the open circuit for one attempt
    rc, out, _e = _run(runner, clock, sleep, state_path, force=True)
    assert rc == 0 and out == "out"
    assert len(runner.calls) == calls_after_open + 1


def test_force_via_env(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_FAILS", "3")
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([CONN_FAIL] * 6 + [OK])
    for _ in range(3):
        _run(runner, clock, sleep, state_path)
    calls_after_open = len(runner.calls)

    monkeypatch.setenv("NOCTUS_SSH_FORCE", "1")
    rc, _o, _e = _run(runner, clock, sleep, state_path)
    assert rc == 0
    assert len(runner.calls) == calls_after_open + 1


# ── routed-tool end-to-end through the helper ───────────────────────────────
def test_routed_tool_deploy_pull_uses_helper(monkeypatch, tmp_path):
    """deploy_pull WITHOUT an injected run_remote routes its default runner
    through `_vps_ssh.run_remote` — proven by patching the helper's real ssh
    seam + state path so a full dry-run drill completes with zero real SSH."""
    from tools.noctus.dev import deploy_pull as DP

    state = tmp_path / "throttle.json"
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")

    # The fake ssh: scripts the git rev-parse / status / diff / merge-base the
    # deploy_pull drill issues. up_to_date path: HEAD == target → no merge.
    def fake_ssh(ssh_host, remote_cmd, connect_timeout, timeout):
        if "rev-parse" in remote_cmd:
            return 0, "abc123\n", ""
        return 0, "", ""

    # Route the helper's defaults to the fake + a tmp state path (no real SSH,
    # no real cache dir). deploy_pull's _default_run_remote calls run_remote()
    # with only (ssh_host, cmd), so we steer the DEFAULTS via the module globals.
    monkeypatch.setattr(VSS, "_real_ssh", fake_ssh)
    monkeypatch.setattr(VSS, "_STATE_PATH_CACHE", state, raising=False)

    # No run_remote= injected → exercises _default_run_remote → _throttled_ssh.
    r = DP.deploy_pull()
    assert r["status"] == "up_to_date"
    assert r["exit_code"] == 0


def test_routed_tool_vps_ps_uses_helper(monkeypatch, tmp_path):
    """vps.ps WITHOUT an injected run_remote routes through the throttle too."""
    from tools.noctus.dev import vps as V

    state = tmp_path / "throttle.json"
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    _PS = "noctus-core\tghcr.io/x/noctus-core:latest\tUp 2 hours (healthy)\n"

    def fake_ssh(ssh_host, remote_cmd, connect_timeout, timeout):
        return 0, _PS, ""

    monkeypatch.setattr(VSS, "_real_ssh", fake_ssh)
    monkeypatch.setattr(VSS, "_STATE_PATH_CACHE", state, raising=False)

    r = V.ps()
    assert r["ok"] is True
    assert any(c["name"] == "noctus-core" for c in r["containers"])


# ── connection multiplexing (2026-07-14 fleet-deploy volume ban) ─────────────
class TestMultiplexing:
    """ControlMaster multiplexing is the PRIMARY defense: it collapses a fleet
    deploy's ~50 SSH connections into ~1, so fail2ban's connection-RATE rule
    (which the failure-only circuit-breaker can't catch) never trips."""

    def test_multiplex_opts_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("NOCTUS_SSH_MULTIPLEX", raising=False)
        opts = VSS._multiplex_opts()
        if VSS.os.name != "posix":
            assert opts == []
            return
        assert "ControlMaster=auto" in opts
        assert any(o.startswith("ControlPath=") for o in opts)
        assert any(o.startswith("ControlPersist=") for o in opts)
        # the control socket dir is created (mode 0700) so the master can bind
        assert VSS._CONTROL_DIR.is_dir()

    def test_multiplex_opts_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_SSH_MULTIPLEX", "0")
        assert VSS._multiplex_opts() == []

    def test_real_ssh_passes_controlmaster_to_ssh(self, monkeypatch):
        """_real_ssh emits the ControlMaster flags so every op reuses one master."""
        if VSS.os.name != "posix":
            pytest.skip("multiplexing is POSIX-only")
        monkeypatch.delenv("NOCTUS_SSH_MULTIPLEX", raising=False)
        captured = {}

        class _R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_run(args, **kwargs):
            captured["args"] = args
            return _R()

        monkeypatch.setattr(VSS.subprocess, "run", fake_run)
        rc, out, err = VSS._real_ssh("noctus-vps", "echo hi", 8, 30.0)
        assert rc == 0
        args = captured["args"]
        assert "ControlMaster=auto" in args
        assert any(isinstance(a, str) and a.startswith("ControlPersist=") for a in args)


# ── sliding-window rate cap (2026-07-14: prevent the burst, don't react) ─────
def test_rate_cap_sleeps_when_window_full(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")   # isolate the rate cap
    monkeypatch.setenv("NOCTUS_SSH_MAX_PER_WINDOW", "2")
    monkeypatch.setenv("NOCTUS_SSH_RATE_WINDOW", "60")
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([OK, OK, OK])

    _run(runner, clock, sleep, state_path)   # t=1000, attempt 1
    clock.advance(1.0)
    _run(runner, clock, sleep, state_path)   # t=1001, attempt 2 → window now holds 2
    assert captured == []                    # still under cap: no rate sleep
    clock.advance(1.0)
    _run(runner, clock, sleep, state_path)   # t=1002, attempt 3 → wait for oldest(1000) to age out
    assert len(captured) == 1
    assert captured[0] == pytest.approx(58.0)  # 1000 + 60 - 1002
    assert len(runner.calls) == 3            # all three still connect (paced, not dropped)


def test_rate_cap_no_sleep_once_window_drains(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.setenv("NOCTUS_SSH_MAX_PER_WINDOW", "2")
    monkeypatch.setenv("NOCTUS_SSH_RATE_WINDOW", "60")
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([OK, OK, OK])

    _run(runner, clock, sleep, state_path)
    _run(runner, clock, sleep, state_path)
    clock.advance(61.0)                       # both prior attempts aged out of the window
    _run(runner, clock, sleep, state_path)
    assert captured == []                     # window empty → no rate sleep


def test_rate_cap_disabled_when_zero(monkeypatch, sleeps, state_path):
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.setenv("NOCTUS_SSH_MAX_PER_WINDOW", "0")   # 0 = disabled
    captured, sleep = sleeps
    clock = Clock()
    runner = FakeRunner([OK] * 5)

    for _ in range(5):
        _run(runner, clock, sleep, state_path)  # 5 rapid calls, same instant
    assert captured == []                        # cap disabled → never paces
