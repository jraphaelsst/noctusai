"""Seed async handlers keep sync PostgREST round trips off the event loop.

Real router, real FastAPI wiring, a fake admin client whose every `.table()` sleeps: N concurrent
requests must overlap (~SLEEP) instead of serializing on the loop (N * SLEEP).

KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from noctusai_lib.testing import MockSupabaseClient
from noctusai_seed.status_pagina_router import _create_status_pagina_router

SLEEP = 0.2


class SlowAdmin:
    def __init__(self):
        self._inner = MockSupabaseClient()
        self._inner.set_table_data(
            "status_pagina", [{"id": "1", "nome_pagina": "p", "status": "producao"}]
        )

    def table(self, name):
        time.sleep(SLEEP)
        return self._inner.table(name)


def test_status_pagina_listar_overlaps_concurrent_requests():
    admin = SlowAdmin()

    async def get_current_user(_authorization):
        return SimpleNamespace(id="u"), "tok"

    deps = SimpleNamespace(
        get_current_user=get_current_user,
        get_user_role=lambda _u: "owner",
        get_admin_client=lambda: admin,
    )
    app = FastAPI()
    app.include_router(_create_status_pagina_router(deps, SimpleNamespace(), "x"))

    async def run(n):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            t0 = time.perf_counter()
            rs = await asyncio.gather(*[c.get("/api/status-paginas") for _ in range(n)])
            return rs, time.perf_counter() - t0

    n = 5
    rs, elapsed = asyncio.run(run(n))
    assert [r.status_code for r in rs] == [200] * n
    assert elapsed < n * SLEEP * 0.6, elapsed
