#!/usr/bin/env python3
"""uvicorn_credentials_driver.py — piped as ``stdin`` to ``python3 -`` INSIDE
the running container (roadmap ``julia-agents-academia-2026-09``, row
SEC-C; extended contract §E.11 / roadmap D2 to drive MULTIPLE per-
conversation slots instead of the old single shared uid).

WHY THIS SHAPE, NOT ``docker exec -u <julia-cli-uid>``: per the D1 retro's
own methodology note, ``docker exec -u <user>`` does NOT reproduce the
app's real spawn path for a NON-root uid — it gets no ambient-capability
inheritance from the entrypoint's own ``setpriv`` chain, so a wrapper
spawned from under it would fail the very uid switch it's supposed to
prove. Instead, ``run_proof.py`` execs THIS file via a FRESH ``setpriv``
invocation whose flags are EXTRACTED from ``bin/entrypoint.sh`` itself
(never hand-copied — see ``run_proof.py``'s ``_entrypoint_setpriv_
prefix``), landing THIS driver process at uid 1000 (``noctus``) with the
exact same ambient SETUID/SETGID/KILL uvicorn itself runs with. From
there, every ``subprocess.run(..., user="julia-cli-<K>")`` below mirrors
what a real ``app/runtime/claude_runtime.py`` turn does (``cli_path=
"/app/bin/julia-cli-exec"``, ``user="julia-cli-<K>"``, ``env={}``), and
the un-``user=`` call mirrors the SDK's own no-``user=`` version-check
spawn (``claude_agent_sdk/_internal/transport/subprocess_cli.py::
_check_claude_version`` — ``anyio.open_process([cli_path, "-v"], ...)``).

WHY ONE SCRIPT DOES SO MUCH: every step below needs the SAME ambient-cap
bootstrap (this driver's own uid 1000 + SETUID/SETGID/KILL), so bundling
them into one ``docker exec -i ... python3 -`` invocation avoids repeating
that bootstrap per check — ``run_proof.py`` then unpacks ONE returned JSON
blob into several independently-reported ``CheckResult`` rows.

Placeholders (substituted by ``run_proof.py`` via plain ``str.replace`` —
the SAME "one test seam: literal substitution, never a templating engine"
convention ``tests/runtime/test_wrapper.py``'s ``_copy_with_subs`` uses)::

    __SECC_APPEND_PATH__    /run/julia-handoff/0/append.md (the persona/
                             JULIA.md injection path — contract §E.11
                             "Launch options": `extra_args={"append-
                             system-prompt-file": ...}`, never on argv).
                             Note this is UNRELATED to the "durable
                             transcripts" handoff *.jsonl file — no slot
                             script logic ever touches append.md; the
                             real CLI (here: `secc/probe.py`) receives it
                             only as an argv flag.
    __SECC_SENTINEL__       a random marker string checked absent from
                             EVERY /proc/*/cmdline while a slot process
                             carrying `--append-system-prompt-file
                             __SECC_APPEND_PATH__` is alive

DELIBERATELY NOT the "durable transcripts" handoff *.jsonl file here: that
needs a specific, non-empty ``/run/julia-handoff/0/<sid>.jsonl`` to exist,
and ``julia-cli-slot``'s own handoff-copy step runs on EVERY invocation of
slot 0 (not just a dedicated one) — seeding it before THIS script's own
clean identity/caps/env spawns would contaminate them with whatever that
copy step does. ``run_proof.py``'s ``secc/handoff_check_driver.py`` is the
dedicated, LATER, separately-sequenced script for that (contract §E.11 D2
check 5) — see this project's delivery note for why the split matters
(a real D1 defect makes the handoff-copy step itself fail-closed).

Stdlib only — no pip install step, and no dependency on this repo's own
``secc`` package (it isn't baked into the image).
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time

_WRAPPER = "/app/bin/julia-cli-exec"
_PROBE_MARKER = "SECC_PROBE_JSON:"

_APPEND_PATH = "__SECC_APPEND_PATH__"
_SENTINEL = "__SECC_SENTINEL__"


def _parse_probe_json(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith(_PROBE_MARKER):
            return json.loads(line[len(_PROBE_MARKER) :])
    return None


def _config_dir_for(user: str) -> str:
    """``julia-cli-<K>`` -> ``/run/julia-<K>/home/.claude`` — the ONE env
    key ``ClaudeAgentOptions.env`` actually carries for a real turn
    (contract §E.11 "Launch options": ``env={"CLAUDE_CONFIG_DIR": ...}``).
    """
    k = user.rsplit("-", 1)[1]
    return f"/run/julia-{k}/home/.claude"


def _spawn(args: list[str], *, user: str | None = None, real_turn: bool = False, timeout: int = 40) -> dict:
    """One foreground wrapper invocation. ``real_turn=True`` passes
    ``env={"CLAUDE_CONFIG_DIR": ...}`` — the REAL spawn's exact shape
    (contract §E.11 "Launch options"; the wrapper's own ``env -i``
    strips everything else back down to the allowlist regardless).
    ``real_turn=False`` (the version-check path) inherits THIS process's
    full environment, exactly like the SDK's un-``user=`` spawn inherits
    uvicorn's."""
    kwargs: dict = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if user is not None:
        kwargs["user"] = user
    if real_turn:
        assert user is not None, "real_turn=True requires a slot user"
        kwargs["env"] = {"CLAUDE_CONFIG_DIR": _config_dir_for(user)}
    proc = subprocess.run([_WRAPPER, *args], **kwargs)
    return {
        "returncode": proc.returncode,
        "stderr": proc.stderr,
        "diag": _parse_probe_json(proc.stdout),
    }


def _spawn_background(args: list[str], *, user: str) -> tuple[subprocess.Popen, dict]:
    proc = subprocess.Popen(
        [_WRAPPER, *args],
        user=user,
        env={"CLAUDE_CONFIG_DIR": _config_dir_for(user)},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    first_line = proc.stdout.readline()
    diag = _parse_probe_json(first_line) or {}
    return proc, diag


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


def _kill_and_reap_once(*, user: str) -> dict:
    """Spawn a SIGTERM-ignoring probe through the REAL wrapper path, then
    replay the SDK's own escalation (``SubprocessCLITransport.close()``:
    SIGTERM, grace period, SIGKILL) — asserting liveness via ``os.kill``
    + ``/proc`` state, never ``Popen.terminate()``'s return value (that
    call can report success while leaving an un-reaped zombie behind)."""
    proc, diag = _spawn_background(["--secc-sigterm-ignore"], user=user)
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
        "user": user,
        "pid": pid,
        "diag": diag,
        "alive_before_term": alive_before_term,
        "survived_sigterm": survived_sigterm,
        "gone_after_kill": gone_after_kill,
        "proc_entry_removed": proc_entry_removed,
    }


def _scan_cmdlines_for(sentinel: str) -> list[int]:
    """``/proc/*/cmdline`` is world-readable regardless of uid — this
    driver (uid 1000) needs no special access to run this scan itself.
    Returns every pid whose argv contains ``sentinel`` (expected: none —
    contract §E.11's persona/JULIA.md text is injected via a FILE the
    real CLI reads, never via argv)."""
    hits: list[int] = []
    sentinel_bytes = sentinel.encode()
    for entry in sorted(os.listdir("/proc")):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            cmdline = open(f"/proc/{pid}/cmdline", "rb").read()
        except OSError:
            continue
        if sentinel_bytes in cmdline:
            hits.append(pid)
    return hits


def main() -> int:
    result: dict = {"driver_uid": os.getuid()}

    # -- version-check path: SDK's un-`user=` spawn, uid 1000 -----------
    result["version_spawn"] = _spawn(["-v"])

    # -- main turns for slot 0 and slot 1: a CLEAN identity/caps/env spawn
    #    each — no handoff *.jsonl file exists yet at this point (contract
    #    §E.11 D2 check 5's own dedicated, LATER, separately-sequenced
    #    driver — secc/handoff_check_driver.py — owns that; see this
    #    module's docstring for why). ------------------------------------
    result["main_spawns"] = {
        "0": _spawn(["--secc-proof-main-turn"], user="julia-cli-0", real_turn=True),
        "1": _spawn(["--secc-proof-main-turn"], user="julia-cli-1", real_turn=True),
    }

    # -- persona sentinel: slot 0 stays alive with the append-system-
    #    prompt-file argument on its OWN argv while every /proc/*/cmdline
    #    in the container is scanned for the sentinel TEXT (which lives
    #    only inside the file, never on any argv) ----------------------
    sentinel_proc, sentinel_diag = _spawn_background(
        ["--secc-sigterm-ignore", "--append-system-prompt-file", _APPEND_PATH],
        user="julia-cli-0",
    )
    result["sentinel_target_pid"] = sentinel_proc.pid
    result["sentinel_target_diag"] = sentinel_diag
    result["sentinel_scan_hits"] = _scan_cmdlines_for(_SENTINEL)

    # -- cross-slot probe: slot 1 attacks slot 0's live process + paths
    #    while it's still alive (contract §E.11 D2 check 4). The handoff
    #    DIRECTORY (empty, but existing — `run_proof.py` seeds it before
    #    this script runs) is listable-denial-tested here; the specific
    #    handoff FILE-read-denial is `handoff_check_driver.py`'s job. -----
    result["cross_slot_probe"] = _spawn(
        [
            "--secc-cross-slot-probe",
            str(sentinel_proc.pid),
            "/run/julia-0",
            "/run/julia-handoff/0",
        ],
        user="julia-cli-1",
        real_turn=True,
    )

    # -- clean up the sentinel target (best-effort; the dedicated
    #    kill_and_reap iterations below are the ASSERTED kill/reap
    #    proof, this is just teardown) ---------------------------------
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(sentinel_proc.pid, signal.SIGKILL)
    sentinel_proc.wait(timeout=5)

    # -- kill + reap, 3 fresh iterations, slot 0 ------------------------
    result["kill_and_reap"] = [_kill_and_reap_once(user="julia-cli-0") for _ in range(3)]

    # -- quota: slot 0 fills to ENOSPC, slot 1 still writes fine --------
    result["quota_fill"] = _spawn(["--secc-fill-quota"], user="julia-cli-0", real_turn=True)
    result["quota_other_write"] = _spawn(["--secc-write-test"], user="julia-cli-1", real_turn=True)

    print(f"SECC_DRIVER_JSON:{json.dumps(result)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
