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
  • min inter-attempt interval (``NOCTUS_SSH_MIN_INTERVAL``, default 3s) — never burst.
  • circuit-breaker: after N consecutive CONNECTION failures
    (``NOCTUS_SSH_CIRCUIT_FAILS``, default 3) OPEN the circuit for a cooldown
    (``NOCTUS_SSH_CIRCUIT_COOLDOWN``, default 600s ≥ typical fail2ban bantime).
    While OPEN, return immediately WITHOUT connecting. A success closes it.
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

import datetime as _dt
import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Sequence

from .cache_backend import cache_dir

logger = logging.getLogger(__name__)

# ── tuning knobs (env-overridable) ──────────────────────────────────────────
_DEFAULT_MIN_INTERVAL = 3.0       # seconds between attempts to the same host
_DEFAULT_CIRCUIT_FAILS = 3        # consecutive conn failures before OPEN
_DEFAULT_CIRCUIT_COOLDOWN = 600.0  # seconds OPEN (≥ typical fail2ban bantime)
_DEFAULT_CONNECT_TIMEOUT = 10     # ssh -o ConnectTimeout=<n>

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
        tmp = state_path.with_suffix(state_path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        os.replace(tmp, state_path)  # atomic on POSIX
    except OSError as exc:
        logger.warning("_vps_ssh: could not persist throttle state to %s (%s)", state_path, exc)


def _host_entry(state: dict, ssh_host: str) -> dict:
    entry = state.get(ssh_host)
    if not isinstance(entry, dict):
        entry = {}
    return {
        "last_attempt_ts": float(entry.get("last_attempt_ts") or 0.0),
        "consecutive_failure_count": int(entry.get("consecutive_failure_count") or 0),
        "circuit_open_until": float(entry.get("circuit_open_until") or 0.0),
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

    remote_cmd = _normalize(argv)
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

    # ── attempt (with ONE backed-off retry on a connection failure) ──
    rc, out, err = runner(ssh_host, remote_cmd, ctimeout, timeout)
    if _is_connection_failure(rc, err):
        sleep(min_interval)
        rc, out, err = runner(ssh_host, remote_cmd, ctimeout, timeout)

    # ── update shared state ──
    entry["last_attempt_ts"] = now()
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
