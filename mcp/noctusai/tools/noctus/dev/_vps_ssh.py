"""Shared throttled + circuit-broken SSH chokepoint for every ``noctus.*`` VPS tool.

WHY THIS EXISTS (the incident, 2026-06-30). A transient network/DNS blip made the
prod VPS briefly unreachable on SSH. The deploy tooling + diagnostics fired RAPID
REPEATED ``ssh noctus-vps …`` attempts — which is exactly what trips ``fail2ban``
on the VPS's sshd, banning our source IP and EXTENDING the outage (self-inflicted).
Before this module FIVE tools each spawned their own ``subprocess.run(["ssh", …])``
with NO shared chokepoint, so nothing could see the connection history or back off.

This module is the single chokepoint. Every VPS tool routes its real SSH through
``run_remote`` so the throttle + circuit-breaker apply ACROSS tools, processes, and
worktrees (fail2ban counts against the whole connection history, so the back-off
state must be shared too — it lives in the git-common cache dir).

Behaviour (all knobs env-overridable):
  • connection MULTIPLEXING (``ControlMaster``, on by default) — the PRIMARY
    defense: one persistent master connection is reused for every op, so a whole
    fleet deploy is ~1 real connection, not ~50 (see the 2026-07-14 incident at
    ``_multiplex_opts``). This is what actually keeps us under fail2ban's
    connection-RATE rule; the interval + circuit-breaker below are secondary.
  • min inter-attempt interval (``NOCTUS_SSH_MIN_INTERVAL``, default 3s) — never burst.
  • sliding-window rate cap (``NOCTUS_SSH_MAX_PER_WINDOW`` per ``NOCTUS_SSH_RATE_WINDOW``,
    default 10/60s) — PROACTIVELY sleeps to keep attempts under the cap, so a
    sustained burst (a fleet deploy) can't form and trip an upstream connection-rate
    limit (ISP outbound-22 throttle or fail2ban). Prevents, rather than reacts.
  • circuit-breaker: after N consecutive CONNECTION failures
    (``NOCTUS_SSH_CIRCUIT_FAILS``, default 2 → ≤4 real attempts escape, under the
    prod VPS sshd maxretry of 5) OPEN the circuit for a cooldown
    (``NOCTUS_SSH_CIRCUIT_COOLDOWN``, default 600s ≥ typical fail2ban bantime).
    While OPEN, return immediately WITHOUT connecting. A success closes it.
  • the read-modify-write of the shared state + the attempt itself run under an
    exclusive cross-process/worktree file lock (``_state_lock``) so concurrent
    tools SERIALIZE — no storm can form (measured: 8 concurrent tools escaped 48
    attempts unlocked vs 4 locked). Degrades to a warned no-op if flock is absent.
  • failure classification — only a genuine CONNECTION failure (ssh's own exit 255
    or a connection-error stderr) counts toward the streak. A remote command that
    RAN and returned nonzero (the edge is healthy) never trips the circuit.
  • one backed-off internal retry on a connection failure (≤2 attempts per call).
  • escape hatch — ``force=True`` / ``NOCTUS_SSH_FORCE=1`` bypasses an open circuit
    for one attempt; the open-circuit error surfaces the state-path to delete.

Methodology: memory feedback_dont_machinegun_prod_edge_with_probes +
feedback_external_api_hot_path_boundaries (bound timeouts, degrade gracefully).
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import logging
import os
import shlex
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Sequence

try:  # POSIX advisory file lock — degrade to a no-op lock on non-POSIX.
    import fcntl as _fcntl
except ImportError:  # pragma: no cover — Windows / no fcntl
    _fcntl = None  # type: ignore[assignment]

from .cache_backend import cache_dir

logger = logging.getLogger(__name__)

# ── tuning knobs (env-overridable) ──────────────────────────────────────────
_DEFAULT_MIN_INTERVAL = 3.0       # seconds between attempts to the same host
_DEFAULT_CIRCUIT_FAILS = 2        # consecutive conn failures before OPEN.
# WHY 2, not 3: each failing call makes up to 2 real ssh attempts (one backed-off
# retry), so N calls = 2N attempts escape before the circuit opens. The prod VPS
# sshd jail is maxretry=5 / findtime=600s (verified 2026-07-02). N=3 → 6 attempts
# > 5 = could self-trip the ban on a single storm; N=2 → 4 attempts ≤ 5 (margin 1).
_DEFAULT_CIRCUIT_COOLDOWN = 600.0  # seconds OPEN (≥ typical fail2ban bantime)
_DEFAULT_CONNECT_TIMEOUT = 10     # ssh -o ConnectTimeout=<n>
# Sliding-window rate cap — PROACTIVELY pace so a burst can never form (prevent,
# don't react). WHY (2026-07-14): a fleet deploy's sustained ~50 connections
# tripped an upstream connection-rate limit (ISP outbound-22 throttle — confirmed
# github:22 also blocked, so NOT the VPS/fail2ban) that the 3s interval +
# failure-only circuit couldn't stop. This caps real attempts per window and
# SLEEPS to stay under it. Multiplexing (above) makes this rarely bite; it's the
# hard guarantee for the non-multiplexed / worst case. safety > speed.
_DEFAULT_MAX_PER_WINDOW = 10      # max ssh attempts per window (0 = disabled)
_DEFAULT_RATE_WINDOW = 60.0       # seconds — the sliding window

_STATE_FILENAME = "vps-ssh-throttle.json"

# Substrings that mark a genuine TRANSPORT/CONNECTION failure (vs. a remote
# command that ran and exited nonzero). ssh's own exit 255 is the primary signal;
# these catch the cases where the exit code is forwarded but stderr is unambiguous.
_CONN_ERROR_MARKERS = (
    "operation timed out",
    "connection refused",
    "connection timed out",
    "connection closed",
    "connection reset",
    "no route to host",
    "could not resolve hostname",
    "name or service not known",
    "network is unreachable",
    "host is unreachable",
    "permission denied",        # key/agent failure = cannot establish session
    "port 22",
    "ssh: connect to host",
    "kex_exchange_identification",
)


# ── SSH connection multiplexing (ControlMaster) ─────────────────────────────
# WHY (2026-07-14 incident, distinct from the 2026-06-30 one above). A FLEET
# deploy opens ~50 SSH connections in a few minutes — 9 products × ~5-6 ops each
# (docker inspect/tag/compose pull/up + a health-probe loop + a tunnel restart),
# plus diagnostics. Every connection was a NEW TCP+auth handshake, and fail2ban
# bans an IP for connection RATE even when every connection SUCCEEDS. The
# circuit-breaker below only reacts to FAILURES, so it never fired — the ban
# landed mid-deploy, self-inflicting an SSH outage. The 3s min-interval bounds
# BURSTS but not sustained volume. Multiplexing is the STRUCTURAL fix: one
# persistent master connection is reused for every op within ControlPersist,
# collapsing ~50 connections → ~1, so the connection-rate rule cannot trip.
_CONTROL_DIR = Path("/tmp/noctus-ssh-cm")  # short, POSIX — socket paths are length-capped
_DEFAULT_CONTROL_PERSIST = "120"  # seconds the master lingers idle after the last op


def _multiplex_opts() -> list[str]:
    """``-o`` flags enabling SSH ControlMaster multiplexing, or ``[]`` when it's
    disabled/unsupported. Reuses ONE master connection across every
    ``run_remote`` call so a whole fleet deploy is ~1 real connection instead of
    ~50 — the structural guarantee against a fail2ban connection-rate ban.
    Toggle off with ``NOCTUS_SSH_MULTIPLEX=0``; tune persistence with
    ``NOCTUS_SSH_CONTROL_PERSIST`` (seconds)."""
    if os.name != "posix":
        return []  # ControlMaster is unsupported on Windows OpenSSH
    if os.environ.get("NOCTUS_SSH_MULTIPLEX", "1") != "1":
        return []
    try:
        _CONTROL_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:  # degrade to no-multiplex rather than break SSH
        logger.warning(
            "_vps_ssh: cannot create control dir %s (%s); multiplexing off", _CONTROL_DIR, exc
        )
        return []
    persist = os.environ.get("NOCTUS_SSH_CONTROL_PERSIST", _DEFAULT_CONTROL_PERSIST)
    return [
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={_CONTROL_DIR}/%C",
        "-o", f"ControlPersist={persist}",
    ]


# ── env helpers ─────────────────────────────────────────────────────────────
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("_vps_ssh: ignoring non-numeric %s=%r; using %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("_vps_ssh: ignoring non-integer %s=%r; using %s", name, raw, default)
        return default


def _force_enabled(force: bool) -> bool:
    return bool(force) or os.environ.get("NOCTUS_SSH_FORCE") == "1"


# ── state persistence (shared across processes/worktrees) ───────────────────
_STATE_PATH_CACHE: Path | None = None


def _default_state_path() -> Path:
    """Shared throttle-state path under the git-common cache dir (so ALL worktrees
    + processes share the back-off state — fail2ban counts the whole history).

    Memoized: ``cache_dir()`` shells out to git, and the throttle runs on every
    VPS SSH call — resolve it once. If resolution fails (git unavailable, or a
    test patching ``subprocess.run`` globally), degrade to a process-local temp
    path rather than ever crashing the underlying SSH op — the throttle is
    advisory infra, never worth failing a production deploy over."""
    global _STATE_PATH_CACHE
    if _STATE_PATH_CACHE is None:
        try:
            _STATE_PATH_CACHE = cache_dir() / _STATE_FILENAME
        except Exception as exc:  # noqa: BLE001 — never let state-dir resolution break SSH
            fallback = Path(tempfile.gettempdir()) / _STATE_FILENAME
            logger.warning(
                "_vps_ssh: could not resolve shared cache dir (%s); throttle state "
                "degraded to process-local %s", exc, fallback,
            )
            _STATE_PATH_CACHE = fallback
    return _STATE_PATH_CACHE


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        # Corrupt / unreadable throttle state must not block a deploy — reset it,
        # but say so (not a silent fallback).
        logger.warning("_vps_ssh: throttle state at %s unreadable (%s); resetting", state_path, exc)
        return {}


def _save_state(state_path: Path, state: dict) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        # Unique per writer (pid + thread) so concurrent writers in ONE process
        # never stamp on each other's temp file (pid alone collides across
        # threads → os.replace races to "No such file or directory").
        tmp = state_path.with_suffix(
            state_path.suffix + f".tmp.{os.getpid()}.{threading.get_ident()}"
        )
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        os.replace(tmp, state_path)  # atomic on POSIX
    except OSError as exc:
        logger.warning("_vps_ssh: could not persist throttle state to %s (%s)", state_path, exc)


@contextlib.contextmanager
def _state_lock(state_path: Path):
    """Exclusive cross-process/worktree lock held across the whole read-modify-
    write + attempt critical section.

    WHY (measured): fail2ban counts the WHOLE connection history, so the back-off
    state must be updated atomically across concurrent tools. Without this lock an
    unsynchronized read-modify-write of the failure counter loses increments and
    the un-gated attempts fire as a burst — a stress test of 8 concurrent tools
    let 48 real SSH attempts escape before lockout, vs a serial ceiling of 6.
    Holding the lock across the attempt SERIALIZES VPS SSH (one in flight at a
    time) so a storm can never form — which is the entire point of the throttle.

    Degrades to a no-op (with a warning) if flock is unavailable — advisory infra
    must never block a production deploy."""
    if _fcntl is None:
        yield
        return
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    fd = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        _fcntl.flock(fd, _fcntl.LOCK_EX)
    except OSError as exc:  # lock unavailable → proceed unsynchronized, but say so
        logger.warning("_vps_ssh: state lock unavailable (%s); proceeding unsynchronized", exc)
        if fd is not None:
            os.close(fd)
            fd = None
    try:
        yield
    finally:
        if fd is not None:
            try:
                _fcntl.flock(fd, _fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(fd)


def _host_entry(state: dict, ssh_host: str) -> dict:
    entry = state.get(ssh_host)
    if not isinstance(entry, dict):
        entry = {}
    raw_recents = entry.get("recent_attempt_ts") or []
    recents = [float(t) for t in raw_recents if isinstance(t, (int, float))]
    return {
        "last_attempt_ts": float(entry.get("last_attempt_ts") or 0.0),
        "consecutive_failure_count": int(entry.get("consecutive_failure_count") or 0),
        "circuit_open_until": float(entry.get("circuit_open_until") or 0.0),
        "recent_attempt_ts": recents,  # sliding-window rate-cap history
    }


# ── failure classification ──────────────────────────────────────────────────
def _is_connection_failure(rc: int, stderr: str) -> bool:
    """True only for a genuine transport/connection failure.

    ssh returns the remote command's exit code on a SUCCESSFUL connection; 255 is
    ssh's own connect/transport failure code. A nonzero rc that is NOT 255 and
    carries no connection-error marker means the edge is healthy and the REMOTE
    command failed — that must NOT trip the circuit.
    """
    if rc == 255:
        return True
    low = (stderr or "").lower()
    return any(marker in low for marker in _CONN_ERROR_MARKERS)


# ── the real ssh runner (the injectable seam for tests) ─────────────────────
def _real_ssh(
    ssh_host: str, remote_cmd: str, connect_timeout: int, timeout: float | None
) -> tuple[int, str, str]:
    args = [
        "ssh",
        "-o", f"ConnectTimeout={connect_timeout}",
        "-o", "BatchMode=yes",
        # Multiplex: reuse ONE master connection across all ops so a fleet
        # deploy is ~1 real connection, not ~50 (fail2ban rate-ban avoidance).
        *_multiplex_opts(),
        ssh_host,
        remote_cmd,
    ]
    kwargs: dict = {"capture_output": True, "text": True}
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        r = subprocess.run(args, **kwargs)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired:
        # A local wall-clock timeout is a connection-class failure.
        return 255, "", f"ssh local timeout after {timeout}s: Connection timed out"


def _iso(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()


def _normalize(argv: str | Sequence[str]) -> str:
    """The remote command as a single string. A list is shell-quoted + joined —
    matching what each tool's previous ``_run_remote_default`` did."""
    if isinstance(argv, str):
        return argv
    return " ".join(shlex.quote(c) for c in argv)


# ── the chokepoint ──────────────────────────────────────────────────────────
def run_remote(
    ssh_host: str,
    argv: str | Sequence[str],
    *,
    connect_timeout: int | None = None,
    timeout: float | None = None,
    force: bool = False,
    _now: Callable[[], float] | None = None,
    _sleep: Callable[[float], None] | None = None,
    _state_path: str | Path | None = None,
    _runner: Callable[[str, str, int, float | None], tuple[int, str, str]] | None = None,
) -> tuple[int, str, str]:
    """Run ``argv`` on ``ssh_host`` over SSH, throttled + circuit-broken.

    Returns ``(returncode, stdout, stderr)`` — the same shape every VPS tool's
    runner already expects. Never raises on a back-off: an OPEN circuit returns a
    structured ``(255, "", <message>)`` so callers degrade gracefully.

    ``_now`` / ``_sleep`` / ``_state_path`` / ``_runner`` are test seams (inject to
    run with zero real SSH and zero real sleep).
    """
    now = _now or time.time
    sleep = _sleep or time.sleep
    runner = _runner or _real_ssh
    state_path = Path(_state_path) if _state_path is not None else _default_state_path()
    ctimeout = connect_timeout if connect_timeout is not None else _env_int(
        "NOCTUS_SSH_CONNECT_TIMEOUT", _DEFAULT_CONNECT_TIMEOUT
    )
    forced = _force_enabled(force)

    min_interval = _env_float("NOCTUS_SSH_MIN_INTERVAL", _DEFAULT_MIN_INTERVAL)
    circuit_fails = _env_int("NOCTUS_SSH_CIRCUIT_FAILS", _DEFAULT_CIRCUIT_FAILS)
    cooldown = _env_float("NOCTUS_SSH_CIRCUIT_COOLDOWN", _DEFAULT_CIRCUIT_COOLDOWN)
    max_per_window = _env_int("NOCTUS_SSH_MAX_PER_WINDOW", _DEFAULT_MAX_PER_WINDOW)
    rate_window = _env_float("NOCTUS_SSH_RATE_WINDOW", _DEFAULT_RATE_WINDOW)

    remote_cmd = _normalize(argv)

    # Hold the shared lock across the ENTIRE read-modify-write + attempt so that
    # concurrent tools/worktrees/processes serialize (one SSH in flight at a time)
    # and the failure counter can never lose an increment. State is (re-)read
    # INSIDE the lock so the decision is made on the current shared value.
    with _state_lock(state_path):
        state = _load_state(state_path)
        entry = _host_entry(state, ssh_host)

        # ── circuit OPEN? back off without connecting (unless forced) ──
        open_until = entry["circuit_open_until"]
        if open_until and now() < open_until and not forced:
            msg = (
                f"ssh circuit OPEN for {ssh_host}: {entry['consecutive_failure_count']} "
                f"consecutive connection failures; backing off until {_iso(open_until)} "
                f"to avoid tripping fail2ban. Pass force=True / set NOCTUS_SSH_FORCE=1 to "
                f"override, or delete {state_path}."
            )
            logger.warning("_vps_ssh: %s", msg)
            return 255, "", msg

        # ── min inter-attempt interval — sleep the remainder, never burst ──
        last = entry["last_attempt_ts"]
        if last:
            elapsed = now() - last
            remaining = min_interval - elapsed
            if remaining > 0:
                sleep(remaining)

        # ── sliding-window rate cap — PROACTIVELY pace, so a burst can't form ──
        # If ``max_per_window`` attempts already fall inside the trailing
        # ``rate_window``, sleep until the oldest that must expire drops out —
        # a single deterministic sleep that guarantees adding this attempt keeps
        # the window at ≤ max_per_window. This PREVENTS the burst up front rather
        # than reacting to a ban after it lands (2026-07-14 ISP-throttle lesson).
        if max_per_window > 0:
            recents = sorted(t for t in entry["recent_attempt_ts"] if now() - t < rate_window)
            if len(recents) >= max_per_window:
                must_expire = recents[len(recents) - max_per_window]
                wait = (must_expire + rate_window) - now()
                if wait > 0:
                    sleep(wait)

        # ── attempt (with ONE backed-off retry on a connection failure) ──
        rc, out, err = runner(ssh_host, remote_cmd, ctimeout, timeout)
        if _is_connection_failure(rc, err):
            sleep(min_interval)
            rc, out, err = runner(ssh_host, remote_cmd, ctimeout, timeout)

        # ── update shared state ──
        attempt_ts = now()
        entry["last_attempt_ts"] = attempt_ts
        # record this attempt + keep only the trailing window (bounds growth)
        entry["recent_attempt_ts"] = [
            t for t in entry["recent_attempt_ts"] if attempt_ts - t < rate_window
        ] + [attempt_ts]
        if _is_connection_failure(rc, err):
            entry["consecutive_failure_count"] += 1
            if entry["consecutive_failure_count"] >= circuit_fails:
                entry["circuit_open_until"] = now() + cooldown
                logger.warning(
                    "_vps_ssh: circuit OPENED for %s after %d consecutive connection "
                    "failures; backing off %.0fs until %s",
                    ssh_host, entry["consecutive_failure_count"], cooldown,
                    _iso(entry["circuit_open_until"]),
                )
        else:
            # Success OR remote-nonzero-but-connected → the edge is healthy; reset.
            entry["consecutive_failure_count"] = 0
            entry["circuit_open_until"] = 0.0

        state[ssh_host] = entry
        _save_state(state_path, state)
        return rc, out, err
