#!/usr/bin/env python3
"""handoff_check_driver.py — piped as ``stdin`` to ``python3 -`` INSIDE the
running container, via the SAME ambient-cap ``setpriv`` bootstrap
``uvicorn_credentials_driver.py`` uses (contract §E.11, roadmap D2 SEC-C
harness check 5).

Deliberately SEPARATE from ``uvicorn_credentials_driver.py`` and run
LATER, AFTER that script's clean identity/caps/env spawns have already
completed: ``bin/julia-cli-slot``'s handoff-copy step runs on EVERY
invocation of a slot (not a dedicated mode), so seeding the handoff
``*.jsonl`` file before those clean spawns would contaminate them with
whatever that copy step does — including, per this project's delivery
note, a REAL D1 defect (``useradd --user-group`` does not pin the slot
group's gid to the uid) that makes the copy step itself exit non-zero
(fail-closed) before ever reaching the CLI stand-in.

``run_proof.py`` seeds ``/run/julia-handoff/0/<sid>.jsonl`` (as ``noctus``,
chgrp'd to the group's ACTUAL current gid via ``getent`` — never a
hand-copied "2000+K" literal, so THIS harness doesn't independently
reproduce the same assumption the defect breaks) immediately before
running this script.

Two things checked, in order:
  * ``handoff_turn`` — slot 0's real turn (``julia-cli-exec`` ->
    ``julia-cli-slot``): does the handoff-copy step succeed, and does a
    FOLLOW-UP slot-0 read of the copy see the sentinel content?
  * ``slot1_source_read`` — can slot 1 read the SOURCE file directly
    (contract §E.11: "unreadable from slot 1")? Expected ``denied``
    regardless of the D1 defect above (slot 1's gid never matched
    ``julia-cli-0``'s gid either way).

Placeholders (substituted by ``run_proof.py`` via plain ``str.replace``)::

    __SECC_SID__            the UUID naming the seeded handoff transcript
    __SECC_HANDOFF_FILE__   /run/julia-handoff/0/<sid>.jsonl

Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_WRAPPER = "/app/bin/julia-cli-exec"
_PROBE_MARKER = "SECC_PROBE_JSON:"

_SID = "__SECC_SID__"
_HANDOFF_FILE = "__SECC_HANDOFF_FILE__"


def _parse_probe_json(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith(_PROBE_MARKER):
            return json.loads(line[len(_PROBE_MARKER) :])
    return None


def _config_dir_for(user: str) -> str:
    k = user.rsplit("-", 1)[1]
    return f"/run/julia-{k}/home/.claude"


def _spawn(args: list[str], *, user: str, timeout: int = 40) -> dict:
    proc = subprocess.run(
        [_WRAPPER, *args],
        user=user,
        env={"CLAUDE_CONFIG_DIR": _config_dir_for(user)},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": proc.returncode,
        "stderr": proc.stderr,
        "diag": _parse_probe_json(proc.stdout),
    }


def main() -> int:
    result: dict = {"driver_uid": os.getuid()}

    result["handoff_turn"] = _spawn(["--secc-proof-main-turn"], user="julia-cli-0")
    result["read_back"] = _spawn(["--secc-read-handoff-copy", _SID], user="julia-cli-0")
    result["slot1_source_read"] = _spawn(["--secc-read-path", _HANDOFF_FILE], user="julia-cli-1")

    print(f"SECC_HANDOFF_DRIVER_JSON:{json.dumps(result)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
