"""STRESS / SAFETY evaluation for the shared SSH throttle (`_vps_ssh`).

The unit suite (`test_vps_ssh.py`) proves the circuit-breaker LOGIC single-threaded.
This module answers the operational question the 2026-06-30 ban raised:

  "Under a real storm — many tools firing at once, sharing ONE on-disk state
   file across processes/worktrees — how many real SSH attempts actually escape
   to the edge before the throttle locks everything out, and does the shared
   state stay correct under contention?"

That escape-count is the fail2ban exposure. ZERO real SSH / ZERO real sleep — the
runner + clock + sleep are injected; ONLY the state file is real (its concurrent
read-modify-write is exactly what we are stressing).
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import _vps_ssh as VSS  # noqa: E402

HOST = "noctus-vps"
CONN_FAIL = (255, "", "ssh: connect to host noctus-vps port 22: Operation timed out")


class CountingRunner:
    """Always a connection failure; counts every real ssh attempt, thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self.attempts = 0

    def __call__(self, ssh_host, remote_cmd, connect_timeout, timeout):
        with self._lock:
            self.attempts += 1
        return CONN_FAIL


def _fixed_clock(t=1000.0):
    return lambda: t


# ── 1. Edge-exposure bound: how many attempts escape in a serial storm? ──────
def test_serial_burst_escape_count_is_bounded(monkeypatch, tmp_path):
    """A tight burst of 50 failing calls must lock out after a SMALL, fixed number
    of real attempts. With CIRCUIT_FAILS=3 and one backed-off retry per call, the
    ceiling is 3 calls * 2 attempts = 6 — then the circuit is OPEN and every
    further call issues ZERO ssh. This 6 is the fail2ban exposure number."""
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.delenv("NOCTUS_SSH_CIRCUIT_FAILS", raising=False)  # exercise the SHIPPED default (2)
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_COOLDOWN", "600")
    state = tmp_path / "throttle.json"
    runner = CountingRunner()
    clock = _fixed_clock()

    blocked = 0
    for _ in range(50):
        rc, _o, err = VSS.run_remote(
            HOST, "echo hi", _now=clock, _sleep=lambda s: None,
            _state_path=state, _runner=runner,
        )
        assert rc == 255
        if "circuit OPEN" in err:
            blocked += 1

    print(f"\n[serial] real ssh attempts before lockout: {runner.attempts}")
    print(f"[serial] calls short-circuited (zero ssh): {blocked}/50")
    # ceiling = default CIRCUIT_FAILS(2) * 2 (retry) = 4, and 4 <= sshd maxretry(5).
    assert runner.attempts <= 4, f"escaped {runner.attempts} attempts — burst not bounded!"
    assert blocked >= 44, "circuit failed to short-circuit the tail of the burst"


# ── 2. Concurrency: shared state under a real multi-tool storm ───────────────
@pytest.mark.parametrize("n_threads,calls_each", [(8, 10)])
def test_concurrent_shared_state_bounds_escape(monkeypatch, tmp_path, n_threads, calls_each):
    """The real scenario: N tools/worktrees fire concurrently against ONE shared
    on-disk state file (no in-process lock — state is file-based). The read-
    modify-write of the failure counter is unsynchronized, so this measures
    whether concurrency lets EXTRA attempts escape before global lockout.

    A perfectly-serialized throttle would still escape only ~6. The gap between
    6 and the measured number is the concurrency-induced over-exposure."""
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.delenv("NOCTUS_SSH_CIRCUIT_FAILS", raising=False)  # SHIPPED default (2)
    monkeypatch.setenv("NOCTUS_SSH_CIRCUIT_COOLDOWN", "600")
    state = tmp_path / "throttle.json"
    runner = CountingRunner()
    clock = _fixed_clock()
    barrier = threading.Barrier(n_threads)

    def worker():
        barrier.wait()  # maximize contention — everyone starts together
        for _ in range(calls_each):
            VSS.run_remote(
                HOST, "echo hi", _now=clock, _sleep=lambda s: None,
                _state_path=state, _runner=runner,
            )

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_calls = n_threads * calls_each
    print(f"\n[concurrent] {n_threads} threads x {calls_each} calls = {total_calls} run_remote calls")
    print(f"[concurrent] real ssh attempts that escaped to the edge: {runner.attempts}")

    # State file must remain valid JSON (no torn write) and the circuit must be OPEN.
    entry = json.loads(state.read_text())[HOST]
    print(f"[concurrent] final state: {entry}")
    assert entry["circuit_open_until"] > 0, "circuit never opened under concurrency"

    # The safety property: even under maximal concurrency the escape count must
    # stay at the serial ceiling (default CIRCUIT_FAILS(2) * 2 = 4). The
    # `_state_lock` serializes the read-modify-write + attempt so no storm can
    # form. Before the lock this escaped 48; after it, 4 — and 4 <= maxretry(5).
    assert runner.attempts <= 4, (
        f"escaped {runner.attempts} attempts — concurrency let a storm through "
        f"(serial ceiling is 4); the shared-state lock is not serializing"
    )


# ── 3. fail2ban exposure evaluation (printed verdict, env-parametrized) ──────
def test_report_edge_exposure_vs_fail2ban(monkeypatch, tmp_path):
    """Not a pass/fail of the code — a printed EVALUATION of the escape count
    against a typical fail2ban sshd maxretry, so the operator sees the margin."""
    monkeypatch.setenv("NOCTUS_SSH_MIN_INTERVAL", "0")
    monkeypatch.delenv("NOCTUS_SSH_CIRCUIT_FAILS", raising=False)  # SHIPPED default (2)
    state = tmp_path / "throttle.json"
    runner = CountingRunner()
    clock = _fixed_clock()
    for _ in range(20):
        VSS.run_remote(HOST, "x", _now=clock, _sleep=lambda s: None,
                       _state_path=state, _runner=runner)

    escaped = runner.attempts
    vps_maxretry = 5  # verified on prod VPS 2026-07-02 (fail2ban get sshd maxretry)
    margin = vps_maxretry - escaped
    verdict = "SAFE" if escaped <= vps_maxretry else "AT RISK"
    print(f"\n[eval] escape count = {escaped}; prod VPS sshd maxretry = {vps_maxretry}")
    print(f"[eval] margin = {margin}  -> {verdict}")
    # The shipped default MUST keep the escape count at or below the ban threshold.
    assert escaped <= vps_maxretry, (
        f"escape count {escaped} exceeds sshd maxretry {vps_maxretry} — a single "
        f"storm could self-trip the ban; lower NOCTUS_SSH_CIRCUIT_FAILS default"
    )
    assert escaped == 4, "escape count changed — re-evaluate against fail2ban maxretry"
