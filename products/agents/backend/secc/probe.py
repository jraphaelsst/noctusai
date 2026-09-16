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

Modes, selected by argv (the wrapper passes the CLI's own argv through
unmodified; every mode below is contract §E.11 / roadmap D2's SEC-C
harness driving this same stand-in from a DIFFERENT slot uid than the
original single-slot design, so every mode is uid-agnostic — it always
reports ITS OWN identity, never assumes uid 1001):
  * default — dump identity/caps/env + run the "protect uvicorn from the
    CLI" access-check battery (unchanged from the original single-slot
    design: a compromised CLI subprocess, whichever slot it runs as, must
    still never reach uvicorn's own environ/mem/fd/cwd, and a writable
    scan must find only this uid's OWN slot tmpfs), print one JSON line
    prefixed ``SECC_PROBE_JSON:`` to stdout, exit 0.
  * ``--secc-sigterm-ignore`` — install SIG_IGN on SIGTERM, print the
    identity JSON immediately (so the caller has the pid before it starts
    ignoring signals), then sleep until killed. Used by the kill/reap
    check AND (contract §E.11 D2 check 4) as the long-lived TARGET another
    slot's cross-slot probe attacks.
  * ``--secc-cross-slot-probe <target_pid> <target_slot_dir>
    <target_handoff_dir> [<target_handoff_file>]`` — contract §E.11 D2
    check 4: this slot's OWN process (already uid/cap-stripped by the
    wrapper) runs the EACCES/EPERM access battery against ANOTHER slot's
    live process and filesystem paths, never uvicorn's.
  * ``--secc-read-handoff-copy <sid>`` — contract §E.11 D2 check 5: reads
    back ``$HOME/.claude/projects/-app/<sid>.jsonl`` (the file
    ``bin/julia-cli-slot`` copies FROM the handoff mount INTO this slot's
    own tmpfs at turn start) — proving the copy landed, from the one
    uid (this slot's own) that is SUPPOSED to be able to read it.
  * ``--secc-fill-quota`` — contract §E.11 D2 check 8: writes 1 MiB
    chunks into ``$HOME`` until ENOSPC (or a 256 MiB safety cap), proving
    this slot's own 40 MiB tmpfs quota is enforced.
  * ``--secc-write-test`` — contract §E.11 D2 check 8: a small write to
    ``$HOME``, proving a DIFFERENT slot's own tmpfs is unaffected by
    another slot hitting its own quota.
  * ``--secc-read-path <path>`` — contract §E.11 D2 check 5: a single
    EACCES/EPERM-classified read attempt against an arbitrary path
    (``secc/handoff_check_driver.py``'s "can slot 1 read slot 0's handoff
    SOURCE file directly" test).

Stdlib only (``os``/``sys``/``json``/``signal``/``subprocess``/``time``/
``ctypes``/``errno``) — this runs under the base image's system python3,
no pip install step.
"""
from __future__ import annotations

import ctypes
import errno as errno_module
import json
import os
import signal
import subprocess
import sys
import time

_CAP_LINES = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")

#: ``linux/ptrace.h`` — used ONLY to prove PTRACE_ATTACH across the slot
#: uid boundary is denied (contract §E.11 D2 check 4). Never actually
#: traces anything: a successful attach is immediately detached and, per
#: this module's "loud crash on an unexpected security success" pattern
#: (see ``_setpriv_to_1000`` below), raises rather than silently reports.
_PTRACE_ATTACH = 16
_PTRACE_DETACH = 17


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


def _ptrace_attach(pid: int) -> None:
    """Attempt ``PTRACE_ATTACH`` on ``pid`` via a raw ``ctypes`` syscall —
    there is no stdlib wrapper. A denied attach raises ``PermissionError``
    (the expected, isolating outcome, classified by ``_access_check``
    exactly like every other EACCES/EPERM probe below). An UNEXPECTEDLY
    successful attach is immediately detached and then raises
    ``RuntimeError`` — deliberately UNCAUGHT by ``_access_check`` (which
    only classifies ``PermissionError``/``OSError``), so a real isolation
    break crashes this probe loudly instead of being folded into any
    outcome bucket (mirrors ``_setpriv_to_1000``'s own "loud crash on an
    unexpected security success" rule a few lines above)."""
    libc = ctypes.CDLL(None, use_errno=True)
    ctypes.set_errno(0)
    result = libc.ptrace(ctypes.c_long(_PTRACE_ATTACH), ctypes.c_long(pid), 0, 0)
    if result == -1:
        err = ctypes.get_errno()
        raise PermissionError(err, os.strerror(err))
    libc.ptrace(ctypes.c_long(_PTRACE_DETACH), ctypes.c_long(pid), 0, 0)
    raise RuntimeError(f"ptrace(PTRACE_ATTACH, {pid}) UNEXPECTEDLY SUCCEEDED — isolation broken")


def _cross_slot_probe(
    target_pid: int,
    target_slot_dir: str,
    target_handoff_dir: str,
    target_handoff_file: str | None,
) -> dict[str, object]:
    """Contract §E.11 D2 check 4: this slot's own EACCES/EPERM battery
    against ANOTHER slot's live process and filesystem paths — the
    slot-vs-slot isolation property (I3), as opposed to ``_run_access_
    checks``'s slot-vs-uvicorn battery (protecting the app from any
    compromised CLI, the original SEC-C intent)."""
    checks: dict[str, object] = {
        "target_pid": target_pid,
        "target_slot_dir": target_slot_dir,
        "target_handoff_dir": target_handoff_dir,
    }
    checks["proc_environ"] = _access_check(lambda: open(f"/proc/{target_pid}/environ", "rb").read())
    checks["proc_mem"] = _access_check(lambda: open(f"/proc/{target_pid}/mem", "rb").read(1))
    checks["proc_fd"] = _access_check(lambda: os.listdir(f"/proc/{target_pid}/fd"))
    checks["proc_cwd"] = _access_check(lambda: os.readlink(f"/proc/{target_pid}/cwd"))
    checks["kill_minus_0"] = _access_check(lambda: os.kill(target_pid, 0))
    checks["sigterm"] = _access_check(lambda: os.kill(target_pid, signal.SIGTERM))
    checks["ptrace_attach"] = _access_check(lambda: _ptrace_attach(target_pid))
    checks["target_slot_dir_listing"] = _access_check(lambda: os.listdir(target_slot_dir))
    checks["target_handoff_dir_listing"] = _access_check(lambda: os.listdir(target_handoff_dir))
    if target_handoff_file:
        checks["target_handoff_file_read"] = _access_check(
            lambda: open(target_handoff_file, "rb").read()
        )
    return checks


def _read_handoff_copy(sid: str) -> dict[str, object]:
    """Contract §E.11 D2 check 5: reads back the file ``bin/julia-cli-
    slot`` copies FROM the handoff mount INTO this slot's own tmpfs at
    turn start (``$HOME/.claude/projects/-app/<sid>.jsonl``) — proving the
    copy landed, readable by the one uid (this slot's own) that is
    SUPPOSED to be able to read it."""
    home = os.environ.get("HOME", "")
    path = os.path.join(home, ".claude", "projects", "-app", f"{sid}.jsonl")
    try:
        content = open(path, "r", encoding="utf-8").read()
        return {"copy_path": path, "copy_exists": True, "copy_content": content}
    except OSError as exc:
        return {"copy_path": path, "copy_exists": False, "error": str(exc)}


def _fill_quota(cap_bytes: int = 256 * 1024 * 1024) -> dict[str, object]:
    """Contract §E.11 D2 check 8: writes 1 MiB chunks into ``$HOME`` until
    ENOSPC (the slot's own 40 MiB tmpfs quota) or ``cap_bytes`` (a safety
    ceiling — this must never spin forever if the mount is somehow NOT
    quota-limited, which would itself be the real defect this check looks
    for)."""
    home = os.environ.get("HOME", "/tmp")
    path = os.path.join(home, "quota-fill.bin")
    chunk = b"\0" * (1024 * 1024)
    written = 0
    hit_errno: int | None = None
    try:
        with open(path, "wb") as fh:
            while written < cap_bytes:
                fh.write(chunk)
                fh.flush()
                os.fsync(fh.fileno())
                written += len(chunk)
    except OSError as exc:
        hit_errno = exc.errno
    return {
        "written_bytes": written,
        "errno": hit_errno,
        "got_enospc": hit_errno == errno_module.ENOSPC,
        "hit_safety_cap": hit_errno is None and written >= cap_bytes,
    }


def _write_test() -> dict[str, object]:
    """Contract §E.11 D2 check 8: a small write to ``$HOME``, proving a
    DIFFERENT slot's own tmpfs is unaffected by another slot hitting ITS
    OWN quota (disjoint mounts — a per-slot cap, never a shared one)."""
    home = os.environ.get("HOME", "/tmp")
    path = os.path.join(home, "probe-write-test.bin")
    try:
        with open(path, "wb") as fh:
            fh.write(b"secc-write-test-ok")
        return {"ok": True, "path": path}
    except OSError as exc:
        return {"ok": False, "path": path, "errno": exc.errno, "detail": str(exc)}


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
    argv = sys.argv[1:]

    if "--secc-sigterm-ignore" in argv:
        payload = _identity()
        payload["mode"] = "sigterm-ignore"
        print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            time.sleep(1)

    if "--secc-cross-slot-probe" in argv:
        i = argv.index("--secc-cross-slot-probe")
        rest = argv[i + 1 :]
        target_pid = int(rest[0])
        target_slot_dir = rest[1]
        target_handoff_dir = rest[2]
        target_handoff_file = rest[3] if len(rest) > 3 else None
        payload = _identity()
        payload["mode"] = "cross-slot-probe"
        payload["cross_slot_checks"] = _cross_slot_probe(
            target_pid, target_slot_dir, target_handoff_dir, target_handoff_file
        )
        print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
        return 0

    if "--secc-read-handoff-copy" in argv:
        i = argv.index("--secc-read-handoff-copy")
        sid = argv[i + 1]
        payload = _identity()
        payload["mode"] = "read-handoff-copy"
        payload["handoff_copy"] = _read_handoff_copy(sid)
        print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
        return 0

    if "--secc-fill-quota" in argv:
        payload = _identity()
        payload["mode"] = "fill-quota"
        payload["quota"] = _fill_quota()
        print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
        return 0

    if "--secc-write-test" in argv:
        payload = _identity()
        payload["mode"] = "write-test"
        payload["write_test"] = _write_test()
        print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
        return 0

    if "--secc-read-path" in argv:
        i = argv.index("--secc-read-path")
        target_path = argv[i + 1]
        payload = _identity()
        payload["mode"] = "read-path"
        payload["read_path_check"] = _access_check(lambda: open(target_path, "rb").read())
        print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
        return 0

    payload = _identity()
    payload["mode"] = "default"
    payload["access_checks"] = _run_access_checks()
    print(f"SECC_PROBE_JSON:{json.dumps(payload)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
