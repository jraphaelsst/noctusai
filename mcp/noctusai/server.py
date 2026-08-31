"""NoctusAI MCP Server — platform dev toolkit.

Builds a ``FastMCP`` instance, registers every tool under
``mcp/noctusai/tools/``, and runs over stdio.

Run: ``python mcp/noctusai/server.py`` (or ``python -m mcp.noctusai.server``).

Switch to HTTP/SSE transport later by replacing ``server.run("stdio")``
with the appropriate FastMCP transport call — no tool code changes needed.
"""

from __future__ import annotations

import functools
import inspect
import logging
import sys
from pathlib import Path

import anyio.to_thread

sys.path.insert(0, str(Path(__file__).parent))

# Configure platform-standard logging BEFORE importing any tools/* module.
# MCP server uses stdio: stdout is the JSON-RPC channel and any non-JSON
# byte corrupts it, so we route logs to stderr via `use_stderr=True`.
try:
    from noctusai_lib.logging_config import auto_configure_for_cli
    auto_configure_for_cli("noctusai-mcp-server", use_stderr=True)
except ImportError as exc:
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logging.getLogger(__name__).warning(
        "server: noctusai_lib not installed (%s); using basicConfig fallback. "
        "Run `pip install -e seed/lib/backend` from the repo root to fix.",
        exc,
    )

from mcp.server.fastmcp import FastMCP

from tools import register_all


def offload_blocking(fn):
    """Run a SYNCHRONOUS tool in a worker thread instead of on the event loop.

    🔴 WHY THE SERVER KEPT DYING MID-SESSION (root-caused 2026-08-28)
    ----------------------------------------------------------------
    FastMCP dispatches a tool like this
    (`mcp/server/fastmcp/utilities/func_metadata.py`)::

        if fn_is_async: return await fn(...)
        else:           return fn(...)      # ← INLINE, on the event loop

    A synchronous tool therefore blocks the asyncio loop for its ENTIRE
    duration, and this server speaks JSON-RPC over **stdio** on that same loop.
    While a sync tool runs, the server cannot read a request, answer a ping, or
    write a response — it is completely deaf, and indistinguishable from hung.

    173 of this toolkit's 185 tool modules are synchronous, and the worst
    offenders are exactly the ones a deploy session calls:

    * ``_vps_ssh.run_remote`` deliberately THROTTLES — a ≥3s minimum interval
      between attempts plus a proactive rate-limiter that *sleeps* to stay
      under 10 attempts/60s (fail2ban avoidance).
    * ``deploy_image`` then polls container health with ``health_timeout=120``
      and ``poll_interval=5`` — up to two minutes of ``time.sleep`` on top of
      one throttled SSH round-trip per poll.

    So one ``deploy_image`` holds the loop for MINUTES. Every call queued
    behind it never gets serviced, and the observed failure is exactly that:
    the long call eventually returns, while the calls waiting behind it die
    with "Connection closed" (2026-08-27: `vps_ps`, `deploy_verify` ×2,
    `spa_smoke` — all queued behind a running `deploy_image`).

    That is why this reproduces on DEPLOY sessions specifically and had
    recurred several times: those are the sessions that call the slow SSH
    tools. Nothing was wrong with the network or the VPS.

    🔴 A SECOND, DISTINCT MECHANISM (root-caused 2026-08-31) — THIS FIX DOES
    NOT COVER IT
    -------------------------------------------------------------------
    The server died again 2026-08-31 on a NON-deploy session: 8 concurrent
    subagents + the orchestrator, one of them mid-``task_branch
    action=integrate`` (whose ``cache_settle`` leg can trigger a noc-graph
    rebuild — 39,450 nodes / 62,815 edges, ~13-20s of pure-Python AST-walk +
    clustering), while several OTHER agents independently triggered cache
    refreshes in the same window.

    ``anyio.to_thread.run_sync`` moves a sync tool off the event-loop
    **thread**, which is exactly why it fixes the SSH/``time.sleep`` case
    above: a thread blocked on socket I/O or ``time.sleep`` releases
    CPython's GIL, so the event-loop thread runs freely while it waits. It
    does **NOT** fix a CPU-BOUND blocker: a pure-Python loop (AST walking,
    dict/string building, embedding math) holds the GIL for essentially its
    entire duration — released only at CPython's ~5ms switch-interval
    boundaries — and the event-loop thread is just one more contender for
    those brief windows. Under sustained concurrent CPU-bound load this is
    catastrophic, not marginal: measured via the real ``mcp.server.stdio``
    transport plumbing (which ALSO hops through ``anyio.to_thread.run_sync``
    for every stdin-readline / stdout-write / flush — see
    ``mcp/noctusai/tests/test_server_offloads_blocking_tools.py``), 6
    concurrent ~15s CPU-bound calls (the noc-graph-rebuild scale) pushed
    stdio round-trip latency to ~22s average / ~40s max (357/400 messages
    delayed >5s), while the IDENTICAL load shape with an I/O-bound blocker
    (``time.sleep``) stayed at ~0.3ms average / 2.3ms max. Same wrapper,
    same concurrency shape — the only variable is whether the blocking call
    holds the GIL. That is the "Connection closed" failure from a second,
    unrelated root cause: not one huge call queuing everyone else (the
    2026-08-27 shape, fixed above), but many GIL-holding calls simultaneously
    starving the loop's own ability to service stdio.

    THE FIX for the CPU-bound case does NOT live at this generic
    ``server.tool`` seam — a blanket "run every sync tool in a subprocess"
    would tax the ~170 genuinely I/O-bound / cheap tools with real process-
    spawn overhead for zero benefit. It is a TARGETED classification at the
    one identified genuinely-CPU-heavy operation: ``noc_graph_cache.refresh()``
    checks a module-level ``IN_MCP_SERVER`` flag (set below, in ``run()``)
    and, when a rebuild is actually needed, delegates to a subprocess
    (``_refresh_via_cli_subprocess``) instead of running ``build_graph`` in
    this process — see that function's docstring for the full mechanism.
    Classification lives at the ONE call that does the CPU-heavy work, not
    as a hand-maintained per-tool list: every current and future caller of
    ``noc_graph_cache.refresh()`` (task_branch's cache_settle,
    ``noctus.dev.refresh_all_caches``, ``noctus.dev.settle_structural_caches``,
    the lazy-on-read gate on every ``noctus.graph.*`` query) gets the
    isolation automatically, with no per-caller bookkeeping to drift.

    THE FIX, AND WHY IT LIVES HERE
    ------------------------------
    Wrapping at the single ``server.tool`` seam fixes all 185 tools at once,
    rather than asking every current and future tool author to remember to be
    async. It is the same seam the ``structured_output=False`` default already
    uses, for the same reason: a fleet-wide default belongs in one place.

    An already-async tool is passed through untouched — the 12 that exist keep
    their own concurrency.

    ``functools.wraps`` is load-bearing, not cosmetic: FastMCP builds each
    tool's argument schema with ``inspect.signature``, which follows
    ``__wrapped__``. Without it every tool would register with the signature
    ``(*args, **kwargs)`` and lose its parameters.
    """
    if inspect.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def _threaded(*args, **kwargs):
        return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))

    return _threaded


def build_server() -> FastMCP:
    server = FastMCP(
        name="noctusai",
        instructions=(
            "NoctusAI platform dev toolkit. Tools are namespaced "
            "<vendor_or_namespace>.<service>.<action> (e.g. `noctus.dev.validate`, "
            "`noctus.dev.review`). Legacy flat names (`noctusai_<action>`) are "
            "registered as aliases until consumers migrate. Call "
            "`noctus.dev.agent_context` first when starting a fresh session."
        ),
    )
    # Default structured_output=False fleet-wide. The toolkit's tools return
    # plain JSON (dicts / lists / unions), NOT pydantic BaseModels. Newer
    # mcp/pydantic builds a structured-output model FROM each tool's return
    # annotation and raises PydanticUserError on any non-BaseModel return
    # (`list[...]`, `dict | list`, …) — which aborts register_all and leaves the
    # ENTIRE server with zero tools. Disabling structured output makes the
    # return annotation informational (not a schema source) and restores the
    # pre-structured-output content contract. A tool that genuinely wants
    # structured output can still pass structured_output=True explicitly.
    _orig_tool = server.tool

    def _tool(*args, **kwargs):
        kwargs.setdefault("structured_output", False)
        deco = _orig_tool(*args, **kwargs)

        def register(fn):
            return deco(offload_blocking(fn))

        return register

    server.tool = _tool  # type: ignore[method-assign]
    register_all(server)
    return server


def run() -> None:
    # 🔴 GIL-starvation guard (2026-08-31) — flips noc_graph_cache.refresh()'s
    # rebuild branch to a subprocess for the lifetime of THIS process only.
    # See offload_blocking's docstring above + noc_graph_cache.refresh()'s
    # docstring for the mechanism. Set here (not at import time) so importing
    # server.py — e.g. `from server import offload_blocking` in tests — never
    # flips it; only actually running the stdio server does.
    from tools.noctus.dev import noc_graph_cache
    noc_graph_cache.IN_MCP_SERVER = True
    build_server().run("stdio")


if __name__ == "__main__":
    run()
