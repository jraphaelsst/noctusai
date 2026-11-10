"""`list_changed_since` (the cheap change signal) on the Fake, and the pooled-client wiring of the per-org adapter."""
from __future__ import annotations

import asyncio
from datetime import date

from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations import http_pool
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.integrations.vista.adapter_factory import get_vista_adapter_for_org


def _fake():
    a = FakeVistaAdapter()
    a.add_imovel(Imovel(codigo="A1", data_atualizacao=date(2026, 11, 5)))
    a.add_imovel(Imovel(codigo="A2", data_atualizacao=date(2026, 10, 1)))
    a.add_imovel(Imovel(codigo="A3", data_atualizacao=date(2026, 11, 9), exibir_no_site=False))
    return a


def test_signal_returns_only_published_rows_at_or_after_the_watermark_newest_first():
    page = asyncio.run(_fake().list_changed_since(date(2026, 10, 1)))
    assert [i.codigo for i in page.items] == ["A1", "A2"] and page.total == 2
    assert [i.codigo for i in asyncio.run(_fake().list_changed_since(date(2026, 11, 6))).items] == []


def test_org_adapter_client_is_pooled_and_the_pool_is_one_client_per_loop():
    class _Creds:
        def get(self, org_id):
            return "https://vista.invalid", "k"

    assert get_vista_adapter_for_org(_Creds(), "o")._client()._pooled is True

    async def _two():
        return http_pool.shared_async_client(), http_pool.shared_async_client()

    a, b = asyncio.run(_two())
    assert a is b and a is not None
    assert http_pool.shared_async_client() is None  # no running loop => per-call client fallback
