"""`carregador._endereco_manual` (migration 147) — the manual address
override winning per-field over the CRM/Vista mirror for the 4 fields
`contrato_gerador.derivacao._imovel` gates on.

Pure function, no DB: `catalogo` mimics `busca_service.enriquecer`'s row
shape, `dados` mimics `dados_service.obter`'s response shape.
"""
from __future__ import annotations

from app.modules.card_hub.contrato_gerador.carregador import _endereco_manual

CATALOGO = {
    "logradouro": "Rua Fictícia",
    "numero": "100",
    "complemento": "Apto 11",
    "bairro": "Bairro Modelo",
    "cidade": "São Paulo",
    "uf": "SP",
    "cep": "01000-000",
}

DADOS_SEM_OVERRIDE = {
    "endereco_manual_logradouro": None,
    "endereco_manual_numero": None,
    "endereco_manual_cidade": None,
    "endereco_manual_uf": None,
}


def test_no_override_falls_through_to_the_mirror_on_every_field():
    e = _endereco_manual(CATALOGO, DADOS_SEM_OVERRIDE)
    assert e.logradouro == "Rua Fictícia"
    assert e.numero == "100"
    assert e.cidade == "São Paulo"
    assert e.uf == "SP"
    # Not gate-relevant, never overridable — mirror-only regardless.
    assert e.complemento == "Apto 11"
    assert e.bairro == "Bairro Modelo"
    assert e.cep == "01000-000"


def test_override_wins_per_field_leaving_the_rest_on_the_mirror():
    dados = {
        **DADOS_SEM_OVERRIDE,
        "endereco_manual_logradouro": "Alameda Fictícia",
        "endereco_manual_numero": "535",
    }
    e = _endereco_manual(CATALOGO, dados)
    assert e.logradouro == "Alameda Fictícia"
    assert e.numero == "535"
    # untouched fields still read off the mirror
    assert e.cidade == "São Paulo"
    assert e.uf == "SP"
    assert e.bairro == "Bairro Modelo"


def test_an_off_market_imovel_with_no_mirror_row_at_all_resolves_purely_from_the_override():
    """The manual path's whole point: an imóvel the Vista mirror has never
    heard of (off-market, being tested end to end) still resolves an
    address — from nothing but what a human typed."""
    e = _endereco_manual({}, {
        "endereco_manual_logradouro": "Rua Só Manual",
        "endereco_manual_numero": "1",
        "endereco_manual_cidade": "Campinas",
        "endereco_manual_uf": "SP",
    })
    assert e.logradouro == "Rua Só Manual"
    assert e.numero == "1"
    assert e.cidade == "Campinas"
    assert e.uf == "SP"
    assert e.complemento is None
    assert e.bairro is None
    assert e.cep is None
