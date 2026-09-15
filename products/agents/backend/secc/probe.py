#!/usr/bin/env python3
"""probe.py — SEC-C proof-only CLI stand-in (roadmap ``julia-agents-academia
-2026-09``, row SEC-C).

Baked into the ``secc-proof`` build stage ONLY (``products/agents/backend
/Dockerfile``), root:root, and pointed at by
``/usr/local/bin/claude-bundled`` INSTEAD of the real bundled CLI — the
wrapper (``bin/julia-cli-exec``) and entrypoint (``bin/entrypoint.sh``) are
byte-identical to the ``runtime`` target (asserted by ``run_proof.py`` via
sha256) and always exec whatever ``/usr/local/bin/claude-bundled`` resolves
to, so pointing that ONE symlink/file at this probe (rather than the real
~200MB Anthropic binary) is the only way to exercise the real spawn path
in CI without a real ``ANTHROPIC_API_KEY``.

🔴 NEVER TAGGED, PUSHED OR DEPLOYED. ``secc-proof`` is a `FROM runtime`
stage that exists ONLY for this proof harness — ``scripts/infra/build-and-
push.sh`` / ``.github/workflows/build-and-push.yml`` build+push
``--target runtime`` only (asserted statically by ``run_proof.py``'s
``check_build_and_push_never_builds_secc_proof``).

Whatever uid/gid/caps/env this process observes on ``os.getuid()`` /
``/proc/self/status`` / ``os.environ`` IS the real thing the julia CLI
would have run under for that same invocation — the wrapper has ALREADY
done its own uid switch + cap drop by the time this execs. That makes this
process the natural place to ALSO run the "as uid 1001" access-check
battery (EACCES/EPERM targets) the roadmap's SEC-C row calls for: no
separate ``docker exec -u 1001`` reproduction is needed (and, per the D1
retro's own methodology note, ``docker exec -u <user>`` does NOT reproduce
this state at all — it gets no ambient-cap inheritance from the
entrypoint's own ``setpriv`` chain).

Two modes, selected by argv[0] (the wrapper passes the CLI's own argv
through unmodified):
  * default — dump identity/caps/env + run the access-check battery, print
    one JSON line prefixed ``SECC_PROBE_JSON:`` to stdout, exit 0.
  * ``--secc-sigterm-ignore`` — install SIG_IGN on SIGTERM, print the
    identity JSON immediately (so the caller has the pid before it starts
    ignoring signals), then sleep until killed. Used by the kill/reap
    check (``run_proof.py``'s ``check_kill_and_reap``).

Stdlib only (``os``/``sys``/``json``/``signal``/``subprocess``/``time``) —
this runs under the base image's system python3, no pip install step.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

_CAP_LINES = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")


def _proc_self_status() -> dict[str, str]:
    fields: dict[str, str] = {}
    try:
        text = open("/proc/self/status", "r").read()
    except OSError as exc:
        return {"_error": f"/proc/self/status unreadable: {exc}"}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in _CAP_LINES or key == "NoNewPrivs":
            fields[key] = value.strip()
    return fields


def _find_uvicorn_pid() -> int | None:
    """Scan ``/proc/<pid>/cmdline`` for a process whose argv mentions
    ``uvicorn`` — ``cmdline`` is world-readable inside the container's
    procfs even when ``environ``/``mem``/``fd``/``cwd`` are not (that gap
    IS the isolation property under test)."""
    for entry in sorted(os.listdir("/proc")):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            cmdline = open(f"/proc/{pid}/cmdline", "rb").read()
        except OSError:
            continue
        if b"uvicorn" in cmdline:
            return pid
    return None


def _access_check(fn) -> dict[str, str]:
    """Run ``fn()`` and classify the outcome as ``denied`` (the expected,
    isolating outcome — PermissionError, i.e. EACCES/EPERM), ``allowed``
    (a real isolation failure), or ``error`` (something else went wrong —
    surfaced, never silently folded into either bucket)."""
    try:
        fn()
    except PermissionError as exc:
        return {"outcome": "denied", "errno": exc.errno, "detail": str(exc)}
    except OSError as exc:
        return {"outcome": "error", "errno": exc.errno, "detail": str(exc)}
    else:
        return {"outcome": "allowed", "detail": None}
    return {"outcome": "error", "detail": "unreachable"}


def _run_access_checks() -> dict[str, object]:
    target_pid = _find_uvicorn_pid()
    checks: dict[str, object] = {"target_uvicorn_pid": target_pid}
    if target_pid is None:
        checks["error"] = "no uvicorn process found via /proc/*/cmdline scan"
        return checks

    checks["proc_environ"] = _access_check(
        lambda: open(f"/proc/{target_pid}/environ", "rb").read()
    )
    checks["proc_mem"] = _access_check(
        lambda: open(f"/proc/{target_pid}/mem", "rb").read(1)
    )
    checks["proc_fd"] = _access_check(lambda: os.listdir(f"/proc/{target_pid}/fd"))
    checks["proc_cwd"] = _access_check(lambda: os.readlink(f"/proc/{target_pid}/cwd"))
    checks["kill_minus_0"] = _access_check(lambda: os.kill(target_pid, 0))

    # `noctus`'s /tmp is mode 1770 uid=0 gid=1000 — "other" (julia-cli,
    # groups cleared) has NO access at all, so even STATTING a path under
    # it fails at the directory-traversal level; no file needs to exist.
    checks["tmp_read"] = _access_check(lambda: os.listdir("/tmp"))

    def _setpriv_to_1000() -> None:
        result = subprocess.run(
            ["/usr/bin/setpriv", "--reuid=1000", "--", "/bin/true"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            raise RuntimeError("setpriv --reuid=1000 UNEXPECTEDLY SUCCEEDED")
        # setpriv itself reports EPERM via stderr + a nonzero exit — treat
        # that nonzero exit as the "denied" outcome directly, since it
        # never raises a Python OSError (it's a subprocess, not a syscall
        # in THIS process).
        raise PermissionError(f"setpriv exited {result.returncode}: {result.stderr!r}")

    checks["setpriv_reuid_1000"] = _access_check(_setpriv_to_1000)

    try:
        found = subprocess.run(
            ["find", "/", "-xdev", "-writable"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        writable = sorted(
            p for p in found.stdout.splitlines() if p and p != "/"
        )
        checks["writable_paths"] = writable
    except (OSError, subprocess.TimeoutExpired) as exc:
        checks["writable_paths"] = {"error": str(exc)}

    return checks


def _identity() -> dict[str, object]:
    return {
        "argv": sys.argv[1:],
        "uid": os.getuid(),
        "gid": os.getgid(),
        "groups": sorted(os.getgroups()),
        "env_keys": sorted(os.environ.keys()),
        "proc_status": _proc_self_status(),
        "pid": os.getpid(),
    }


def main() -> int:
    if "--secc-sigterm-ignore" in sys.argv[1:]:
        payload = _identity()
        payload["mode"] = "sigterm-ignore"
        print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            time.sleep(1)

    payload = _identity()
    payload["mode"] = "default"
    payload["access_checks"] = _run_access_checks()
    print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
