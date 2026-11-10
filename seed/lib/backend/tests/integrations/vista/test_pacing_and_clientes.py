"""Vista client pacing + backoff (NOC-REMEDIATE[rate-limit] closed) and the `list_clientes` seam."""
from __future__ import annotations

import httpx
import pytest

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.vista import (
    FakeVistaAdapter,
    VistaClient,
    VistaRateLimited,
    VistaUpstreamError,
    get_vista_adapter_for_org,
)

KEY = "SECRETKEY-abcdef123456"


def _client(handler, **kw) -> tuple[VistaClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrap(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req, len(seen))

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrap))
    return VistaClient("https://x.vistahost.com.br", KEY, http_client=http, **kw), seen


@pytest.mark.asyncio
async def test_every_attempt_acquires_a_token(monkeypatch):
    calls: list[str] = []
    real = rate_limit.acquire_async

    async def spy(bucket, tokens=1.0):
        calls.append(bucket)
        return await real(bucket, tokens)

    monkeypatch.setattr(rate_limit, "acquire_async", spy)
    c, _ = _client(lambda r, n: httpx.Response(200, json={}))
    await c.listar_usuarios(fields=["Codigo"])
    await c.listar_usuarios(fields=["Codigo"])
    assert calls == ["vista", "vista"]


@pytest.mark.asyncio
async def test_429_with_retry_after_waits_then_retries():
    clock = rate_limit._default_clock
    c, seen = _client(lambda r, n: httpx.Response(429, headers={"Retry-After": "7"}, text="slow") if n == 1 else httpx.Response(200, json={"1": {"Codigo": "1"}}))
    t0 = clock.monotonic()
    res = await c.listar_usuarios(fields=["Codigo"])
    assert len(seen) == 2 and res.status == 200
    assert clock.monotonic() - t0 >= 7  # the vendor's hint was honoured (virtual time)


@pytest.mark.asyncio
async def test_backoff_is_bounded_and_gives_up():
    c, seen = _client(lambda r, n: httpx.Response(429, text="slow"))
    with pytest.raises(VistaRateLimited):
        await c.listar_usuarios(fields=["Codigo"])
    assert len(seen) == rate_limit._config_for("vista").max_retries + 1


@pytest.mark.asyncio
async def test_retry_after_past_the_inline_max_is_retry_later_not_a_sleep():
    c, seen = _client(lambda r, n: httpx.Response(429, headers={"Retry-After": "99999"}))
    with pytest.raises(rate_limit.RetryLater):
        await c.listar_usuarios(fields=["Codigo"])
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_5xx_retried_on_reads_never_on_writes():
    c, seen = _client(lambda r, n: httpx.Response(503, text="down") if n < 3 else httpx.Response(200, json={}))
    await c.listar_usuarios(fields=["Codigo"])
    assert len(seen) == 3
    w, wseen = _client(lambda r, n: httpx.Response(503, text="down"))
    with pytest.raises(VistaUpstreamError):
        await w._request("/clientes/cadastrar", method="POST", cadastro={"Nome": "x"})
    assert len(wseen) == 1  # outcome unknown -> no blind retry of a write


@pytest.mark.asyncio
async def test_no_key_in_any_error_text():
    c, _ = _client(lambda r, n: httpx.Response(401, text=f"bad key {KEY}"))
    with pytest.raises(Exception) as ei:
        await c.listar_usuarios(fields=["Codigo"])
    assert KEY not in str(ei.value) and KEY not in getattr(ei.value, "body", "")
    c2, _ = _client(lambda r, n: httpx.Response(429, text=f"slow {KEY}"))
    with pytest.raises(VistaRateLimited) as ei2:
        await c2.listar_usuarios(fields=["Codigo"])
    assert KEY not in str(ei2.value) and KEY not in ei2.value.body


def test_per_org_budget_and_bucket():
    class Res:
        def get(self, org_id):
            return "https://x.vistahost.com.br", KEY

    a = get_vista_adapter_for_org(Res(), "org-1", rate_per_sec=1.5, rate_burst=3)
    assert a._rate["rate_bucket"] == "vista:org-1"
    a._client()  # the budget is applied when the adapter builds its client
    cfg = rate_limit._config_for("vista:org-1")
    assert (cfg.rate_per_sec, cfg.burst) == (1.5, 3.0)
    assert rate_limit._config_for("vista:other").rate_per_sec == rate_limit._config_for("vista").rate_per_sec
    assert rate_limit.configure_bucket("vista:org-1", rate_per_sec=1.5, burst=3, like="vista") is False  # idempotent


@pytest.mark.asyncio
async def test_fake_list_clientes_paginates_and_projects():
    fake = FakeVistaAdapter(clientes=[{"Codigo": str(i), "Nome": f"N{i}", "SenhaWeb": "x"} for i in range(1, 8)])
    itens, pag = await fake.list_clientes(page=2, page_size=3, fields=["Codigo", "Nome"])
    assert [i["Codigo"] for i in itens] == ["4", "5", "6"] and pag["total"] == 7 and pag["paginas"] == 3
    assert "SenhaWeb" not in itens[0]
