"""Canonical adapter tests for `noctusai_lib.integrations.cnpj_registry`.

Zero network: the Fake covers the Protocol contract, the Real adapter is
exercised via `httpx.MockTransport` (same convention
`tests/integrations/turnstile/test_turnstile.py` and `tests/integrations/
documents/test_cartao_cnpj.py` already use). Async methods are driven via
`asyncio.run(...)` inside plain `def test_...()` — no `pytest-asyncio`
plugin in this repo.

Every CNPJ used below is a SYNTHETIC, arithmetically-valid mod-11 number
(`11.222.333/0001-81`, the same one `documents.cartao_cnpj`'s own Fake and
`documents.serasa_crednet.FakeCrednetExtractor` already use) — never a real
company's registration number.
"""
from __future__ import annotations

import asyncio
from datetime import date

import httpx

from noctusai_lib.integrations.cnpj_registry import (
    CnpjNotFoundError,
    CnpjRegistryError,
    CnpjRegistryFields,
    CnpjRegistryLookup,
    CnpjRegistryUpstreamError,
    FakeCnpjRegistryLookup,
    RealCnpjRegistryLookup,
    make_cnpj_registry_lookup,
)

CNPJ_SINTETICO = "11.222.333/0001-81"
CNPJ_SINTETICO_NORM = "11222333000181"


# ── factory ──────────────────────────────────────────────────────────────


def test_factory_defaults_to_fake():
    lookup = make_cnpj_registry_lookup()
    assert isinstance(lookup, FakeCnpjRegistryLookup)


def test_factory_real_true_returns_real():
    lookup = make_cnpj_registry_lookup(real=True)
    assert isinstance(lookup, RealCnpjRegistryLookup)


def test_fake_satisfies_protocol():
    assert isinstance(FakeCnpjRegistryLookup(), CnpjRegistryLookup)


def test_real_satisfies_protocol():
    assert isinstance(RealCnpjRegistryLookup(), CnpjRegistryLookup)


# ── Fake ─────────────────────────────────────────────────────────────────


def test_fake_unscripted_cnpj_resolves_to_synthetic_ativa():
    fake = FakeCnpjRegistryLookup()
    fields = asyncio.run(fake.lookup(CNPJ_SINTETICO))
    assert fields.cnpj == CNPJ_SINTETICO_NORM
    assert fields.situacao_cadastral == "ativa"
    assert fields.source == "fake"
    assert fake.chamadas == [CNPJ_SINTETICO_NORM]


def test_fake_registrar_scripts_a_specific_cnpj():
    fake = FakeCnpjRegistryLookup()
    baixada = CnpjRegistryFields(
        cnpj=CNPJ_SINTETICO_NORM,
        razao_social="EMPRESA BAIXADA SINTETICA LTDA",
        situacao_cadastral="baixada",
        situacao_cadastral_bruta="BAIXADA",
        data_situacao_cadastral=date(2020, 1, 1),
        source="fake",
        raw={},
    )
    fake.registrar(CNPJ_SINTETICO, baixada)
    fields = asyncio.run(fake.lookup(CNPJ_SINTETICO))
    assert fields.situacao_cadastral == "baixada"
    assert fields.data_situacao_cadastral == date(2020, 1, 1)


def test_fake_erro_raises_the_scripted_exception():
    fake = FakeCnpjRegistryLookup(erro=CnpjNotFoundError(CNPJ_SINTETICO_NORM, source="brasilapi"))
    try:
        asyncio.run(fake.lookup(CNPJ_SINTETICO))
        raise AssertionError("expected CnpjNotFoundError")
    except CnpjNotFoundError:
        pass


# ── Real (httpx.MockTransport, zero network) ──────────────────────────────


def test_real_brasilapi_success_never_calls_receitaws():
    def handler(request: httpx.Request) -> httpx.Response:
        if "receitaws" in str(request.url):
            raise AssertionError("must not fall back when brasilapi succeeds")
        return httpx.Response(
            200,
            json={
                "cnpj": CNPJ_SINTETICO_NORM,
                "razao_social": "ACME SINTETICA LTDA",
                "descricao_situacao_cadastral": "ATIVA",
                "data_situacao_cadastral": "2010-03-15",
            },
        )

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    fields = asyncio.run(lookup.lookup(CNPJ_SINTETICO))
    assert fields.source == "brasilapi"
    assert fields.situacao_cadastral == "ativa"
    assert fields.razao_social == "ACME SINTETICA LTDA"
    assert fields.data_situacao_cadastral == date(2010, 3, 15)


def test_real_falls_back_to_receitaws_on_brasilapi_404():
    def handler(request: httpx.Request) -> httpx.Response:
        if "brasilapi" in str(request.url):
            return httpx.Response(404, json={"message": "CNPJ não encontrado"})
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "nome": "ACME SINTETICA LTDA",
                "situacao": "ATIVA",
                "data_situacao": "15/03/2010",
            },
        )

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    fields = asyncio.run(lookup.lookup(CNPJ_SINTETICO))
    assert fields.source == "receitaws"
    assert fields.situacao_cadastral == "ativa"
    # ReceitaWS's own DD/MM/YYYY order, parsed correctly (not swapped).
    assert fields.data_situacao_cadastral == date(2010, 3, 15)


def test_real_falls_back_to_receitaws_on_brasilapi_upstream_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if "brasilapi" in str(request.url):
            return httpx.Response(500, text="internal error")
        return httpx.Response(
            200, json={"status": "OK", "nome": "ACME LTDA", "situacao": "BAIXADA",
                       "data_situacao": "01/01/2020"},
        )

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    fields = asyncio.run(lookup.lookup(CNPJ_SINTETICO))
    assert fields.source == "receitaws"
    assert fields.situacao_cadastral == "baixada"


def test_real_both_sources_fail_raises_upstream_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    try:
        asyncio.run(lookup.lookup(CNPJ_SINTETICO))
        raise AssertionError("expected CnpjRegistryUpstreamError")
    except CnpjRegistryUpstreamError:
        pass


def test_real_both_sources_confirm_not_found_raises_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        if "brasilapi" in str(request.url):
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(200, json={"status": "ERROR", "message": "CNPJ inválido"})

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    try:
        asyncio.run(lookup.lookup(CNPJ_SINTETICO))
        raise AssertionError("expected CnpjNotFoundError")
    except CnpjNotFoundError:
        pass


def test_real_not_found_preferred_over_upstream_when_receitaws_also_fails():
    """brasilapi confirms not-found; receitaws then fails with a generic
    500 (inconclusive) — the DEFINITIVE not-found verdict wins (see
    `real.py`'s fallback-resolution note)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "brasilapi" in str(request.url):
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(500, text="boom")

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    try:
        asyncio.run(lookup.lookup(CNPJ_SINTETICO))
        raise AssertionError("expected CnpjNotFoundError")
    except CnpjNotFoundError:
        pass
    except CnpjRegistryUpstreamError:
        raise AssertionError("a confirmed not-found must win over an inconclusive upstream error")


def test_real_transport_error_falls_back_and_then_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    try:
        asyncio.run(lookup.lookup(CNPJ_SINTETICO))
        raise AssertionError("expected CnpjRegistryError")
    except CnpjRegistryError:
        pass


def test_real_unrecognized_situacao_text_normalizes_to_none_but_keeps_raw():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "cnpj": CNPJ_SINTETICO_NORM,
                "razao_social": "ACME LTDA",
                "descricao_situacao_cadastral": "algo desconhecido",
                "data_situacao_cadastral": None,
            },
        )

    lookup = RealCnpjRegistryLookup(transport=httpx.MockTransport(handler))
    fields = asyncio.run(lookup.lookup(CNPJ_SINTETICO))
    assert fields.situacao_cadastral is None
    assert fields.situacao_cadastral_bruta == "algo desconhecido"
