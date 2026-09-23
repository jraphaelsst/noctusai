"""`carregador._endereco_manual` (migration 149, widened by 159) — the
manual address override winning per-field over the CRM/Vista mirror for
ALL 7 `Endereco` fields — not only the 4 `contrato_gerador.derivacao.
_imovel` gates the contract on.

Pure function, no DB: `catalogo` mimics `busca_service.enriquecer`'s row
shape, `dados` mimics `dados_service.obter`'s response shape.

🔴 2026-09-23 — `complemento`/`bairro`/`cep` became overridable (owner rule:
the property table, including a condo UNIT's own address, is the address of
record — a Vista row that mirrors only the building's GATE address needed a
way to carry the unit's own complemento/CEP too). The two tests that used
to pin these 3 fields as "mirror-only regardless" are updated here with that
proven reason, not silently dropped.
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
    "endereco_manual_complemento": None,
    "endereco_manual_bairro": None,
    "endereco_manual_cidade": None,
    "endereco_manual_uf": None,
    "endereco_manual_cep": None,
}


def test_no_override_falls_through_to_the_mirror_on_every_field():
    e = _endereco_manual(CATALOGO, DADOS_SEM_OVERRIDE)
    assert e.logradouro == "Rua Fictícia"
    assert e.numero == "100"
    assert e.cidade == "São Paulo"
    assert e.uf == "SP"
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


def test_migration_159_condo_internal_address_overrides_the_mirrors_gate_address():
    """The scenario the owner named explicitly: Vista mirrors ONE7515's GATE
    address ("Itália, 343, compl. 535"); the unit's real address is "Alameda
    Alemanha, nº 535". Setting the override on logradouro/numero/complemento
    resolves the UNIT's address, not the gate's — including complemento,
    which 149 shipped as mirror-only."""
    catalogo = {
        "logradouro": "Itália",
        "numero": "343",
        "complemento": "535",
        "bairro": "Alphaville",
        "cidade": "Barueri",
        "uf": "SP",
        "cep": "06454-000",
    }
    dados = {
        **DADOS_SEM_OVERRIDE,
        "endereco_manual_logradouro": "Alameda Alemanha",
        "endereco_manual_numero": "535",
        "endereco_manual_complemento": None,
        "endereco_manual_cep": "06355-465",
    }
    e = _endereco_manual(catalogo, dados)
    assert e.logradouro == "Alameda Alemanha"
    assert e.numero == "535"
    assert e.cep == "06355-465"
    # bairro/cidade/uf were left alone — still the mirror's.
    assert e.bairro == "Alphaville"
    assert e.cidade == "Barueri"


def test_an_off_market_imovel_with_no_mirror_row_at_all_resolves_purely_from_the_override():
    """The manual path's whole point: an imóvel the Vista mirror has never
    heard of (off-market, being tested end to end) still resolves a FULL
    address — from nothing but what a human typed, migration 159's whole
    reason: registration now requires every field but complemento."""
    e = _endereco_manual({}, {
        "endereco_manual_logradouro": "Rua Só Manual",
        "endereco_manual_numero": "1",
        "endereco_manual_complemento": None,
        "endereco_manual_bairro": "Centro",
        "endereco_manual_cidade": "Campinas",
        "endereco_manual_uf": "SP",
        "endereco_manual_cep": "13010-000",
    })
    assert e.logradouro == "Rua Só Manual"
    assert e.numero == "1"
    assert e.cidade == "Campinas"
    assert e.uf == "SP"
    assert e.bairro == "Centro"
    assert e.cep == "13010-000"
    assert e.complemento is None
