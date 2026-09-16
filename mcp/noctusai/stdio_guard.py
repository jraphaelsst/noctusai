"""stdio_guard — give the MCP JSON-RPC channel file descriptors no subprocess can reach.

🔴 WHY THE SERVER KEPT DYING MID-SESSION (root-caused 2026-09-16, third mechanism)
-------------------------------------------------------------------------------
Two earlier fixes (``server.offload_blocking`` 2026-08-28, the noc-graph
subprocess gate 2026-08-31) did not stop the "Connection closed" deaths. The
remaining mechanism is **stdin inheritance**:

* This server speaks JSON-RPC over fd 0 / fd 1. Every ``subprocess.run(...)``
  in the toolkit that does not pass ``stdin=`` (i.e. nearly all of them —
  ``capture_output=True`` only replaces stdout/stderr) hands the child the
  server's OWN stdin pipe.
* ``ssh`` (``_vps_ssh``, deploy/vps tools, git-over-ssh) and libuv/node
  children switch their inherited stdio to ``O_NONBLOCK``. File-status flags
  live on the shared *open file description*, so the SERVER's fd 0 becomes
  non-blocking for as long as the child runs.
* If a request arrives in that window (routine with parallel subagents), the
  transport reads it, and the next ``readline()`` hits ``EAGAIN`` →
  ``TextIOWrapper`` returns ``''`` → ``mcp.server.stdio.stdin_reader`` treats it
  as EOF → the server shuts down CLEANLY: no traceback, exit 0, every in-flight
  call fails at the same instant with "Connection closed".

Reproduced deterministically 2026-09-16 (idle open stdin pipe + ``ssh noctus-vps
'sleep 3'`` + one request mid-ssh ⇒ ``readline -> ''`` ⇒ exit; identical run
with ``stdin=DEVNULL`` survives). Matches every logged death: each had an
ssh/git/node-spawning tool (``deploy_image``, ``deploy_pull``, ``vps_logs``,
``task_branch``, ``vite_build``, ``pytest``) in flight, and no stderr.

THE FIX, AND WHY IT LIVES HERE
------------------------------
Per-call ``stdin=DEVNULL`` would need every current and future subprocess call
(and every grandchild a git hook spawns) to remember it. Instead, at the single
server entry point we move the channel onto private duplicated fds (non-
inheritable per PEP 446, so no child ever receives them) and repoint the
well-known fds: fd 0 → ``/dev/null``, fd 1 → stderr. Consequences:

* children inherit ``/dev/null`` as stdin — they can flip its flags harmlessly;
* a child (or an in-process ``print``) that writes to stdout lands on stderr
  instead of corrupting the JSON-RPC stream.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO


def isolate_stdio_channel() -> tuple[TextIO, TextIO]:
    """Detach the JSON-RPC channel from fds 0/1 and return (rpc_in, rpc_out).

    Must run before anything writes to the channel. Returns text streams on
    private fds for the stdio transport; afterwards fd 0 reads ``/dev/null``
    and fd 1 aliases fd 2 (stderr) for the rest of the process.
    """
    sys.stdout.flush()
    rpc_in_fd = os.dup(0)  # os.dup → non-inheritable (PEP 446)
    rpc_out_fd = os.dup(1)

    devnull = os.open(os.devnull, os.O_RDONLY)
    try:
        os.dup2(devnull, 0)
    finally:
        os.close(devnull)
    os.dup2(2, 1)

    rpc_in = open(rpc_in_fd, "r", encoding="utf-8", errors="replace")
    rpc_out = open(rpc_out_fd, "w", encoding="utf-8")
    return rpc_in, rpc_out
