"""uvicorn_credentials_driver.py — piped as ``stdin`` to ``python3 -`` INSIDE
the running container (roadmap ``julia-agents-academia-2026-09``, row
SEC-C; ``run_proof.py``'s ``check_real_code_path_spawn`` +
``check_kill_and_reap``).

WHY THIS SHAPE, NOT ``docker exec -u 1000``: per the D1 retro's own
methodology note, ``docker exec -u <user>`` does NOT reproduce the app's
spawn path — it gets no ambient-capability inheritance from the
entrypoint's own ``setpriv`` chain, so a wrapper spawned from under it
would fail the very uid switch it's supposed to prove. Instead,
``run_proof.py`` execs this file via a FRESH ``setpriv`` invocation whose
flags are EXTRACTED from ``bin/entrypoint.sh`` itself (never hand-copied —
see ``run_proof.py``'s ``_entrypoint_setpriv_prefix``), landing THIS
process at uid 1000 with the exact same ambient SETUID/SETGID/KILL
uvicorn itself runs with. From there, the two ``subprocess.Popen`` calls
below mirror ``app/runtime/claude_runtime.py`` (``cli_path=
"/app/bin/julia-cli-exec"``, ``user="julia-cli"``, ``env={}``) and the
SDK's own no-``user=`` version-check spawn
(``claude_agent_sdk/_internal/transport/subprocess_cli.py::
_check_claude_version`` — ``anyio.open_process([cli_path, "-v"], ...)``,
no ``user=``, no ``env=`` override) — see the task brief's "at minimum"
bar; a full ``claude_agent_sdk`` transport variant is a named follow-up
(see this project's delivery note).

Stdlib only — no pip install step, and no dependency on this repo's own
``secc`` package (it isn't baked into the image).
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time

_WRAPPER = "/app/bin/julia-cli-exec"
_PROBE_MARKER = "SECC_PROBE_JSON:"


def _parse_probe_json(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith(_PROBE_MARKER):
            return json.loads(line[len(_PROBE_MARKER) :])
    return None


def _spawn_main_path() -> dict:
    """``app/runtime/claude_runtime.py``'s shape: ``cli_path`` = the
    wrapper, ``user="julia-cli"``, ``env={}`` (the SDK then merges its own
    minimal env on top — irrelevant here, since the wrapper's own
    ``env -i`` strips everything back down to the allowlist regardless)."""
    proc = subprocess.run(
        [_WRAPPER, "--secc-proof-main-turn"],
        user="julia-cli",
        env={},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=40,
    )
    return {
        "returncode": proc.returncode,
        "stderr": proc.stderr,
        "diag": _parse_probe_json(proc.stdout),
    }


def _spawn_version_check_path() -> dict:
    """``_check_claude_version``'s exact shape: no ``user=``, no ``env=``
    override — the spawned process inherits THIS process's (uid 1000,
    ambient SETUID/SETGID/KILL) full environment, same as the SDK's
    version probe would from uvicorn."""
    proc = subprocess.run(
        [_WRAPPER, "-v"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=40,
    )
    return {
        "returncode": proc.returncode,
        "stderr": proc.stderr,
        "diag": _parse_probe_json(proc.stdout),
    }


def _proc_state(pid: int) -> str | None:
    try:
        text = open(f"/proc/{pid}/stat", "r").read()
    except OSError:
        return None
    match = re.search(r"\)\s+(\S)\s", text)
    return match.group(1) if match else None


def _still_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Can't happen for our own child, but never mis-report "gone".
        return True
    return True


def _kill_and_reap_once() -> dict:
    """Spawn a SIGTERM-ignoring probe through the REAL wrapper path, then
    replay the SDK's own escalation (``SubprocessCLITransport.close()``:
    SIGTERM, grace period, SIGKILL) — asserting liveness via ``os.kill``
    + ``/proc`` state, never ``Popen.terminate()``'s return value (that
    call can report success while leaving an un-reaped zombie behind)."""
    proc = subprocess.Popen(
        [_WRAPPER, "--secc-sigterm-ignore"],
        user="julia-cli",
        env={},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    first_line = proc.stdout.readline()
    diag = _parse_probe_json(first_line) or {}
    pid = proc.pid

    alive_before_term = _still_alive(pid)
    os.kill(pid, signal.SIGTERM)
    time.sleep(0.5)
    survived_sigterm = _still_alive(pid)  # expected True — SIG_IGN in effect
    os.kill(pid, signal.SIGKILL)
    proc.wait(timeout=5)  # the direct-parent reap
    time.sleep(0.2)
    gone_after_kill = not _still_alive(pid)
    proc_entry_removed = _proc_state(pid) is None

    return {
        "pid": pid,
        "diag": diag,
        "alive_before_term": alive_before_term,
        "survived_sigterm": survived_sigterm,
        "gone_after_kill": gone_after_kill,
        "proc_entry_removed": proc_entry_removed,
    }


def main() -> int:
    result = {
        "driver_uid": os.getuid(),
        "main_spawn": _spawn_main_path(),
        "version_spawn": _spawn_version_check_path(),
        "kill_and_reap": [_kill_and_reap_once() for _ in range(3)],
    }
    print(f"SECC_DRIVER_JSON:{json.dumps(result)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
