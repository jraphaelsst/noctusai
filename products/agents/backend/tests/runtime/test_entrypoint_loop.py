"""The container must run uvicorn on the stdlib asyncio loop.

uvloop (installed by ``uvicorn[standard]``) rejects ``user=`` in
``subprocess_exec``; the slot sweeper and the Agent SDK's CLI spawn both pass
it for per-conversation uid isolation (§E.11). Under ``--loop auto`` every slot
was quarantined at startup (found 2026-09-21 booting the prod image locally).
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[2] / "bin" / "entrypoint.sh"


def test_entrypoint_pins_the_asyncio_loop():
    exec_line = next(l for l in ENTRYPOINT.read_text().splitlines() if l.strip().startswith("uvicorn "))
    assert "--loop asyncio" in exec_line


def test_stdlib_asyncio_subprocess_accepts_user():
    # The capability the pin exists for: the stdlib loop spawns with `user=`
    # (own uid → no privilege needed). Under uvloop this raises ValueError.
    import os
    import sys

    async def spawn() -> int:
        proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass", user=os.getuid())
        return await proc.wait()

    assert asyncio.run(spawn()) == 0
