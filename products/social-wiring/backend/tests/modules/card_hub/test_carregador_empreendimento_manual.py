"""`carregador._empreendimento` (migration 158) — the authored override
winning over the CRM/Vista mirror's `empreendimento` for
`contrato_gerador.contexto.titulo_curto`.

Pure function, no DB: `catalogo` mimics `busca_service.enriquecer`'s row
shape, `dados` mimics `dados_service.obter`'s response shape — same
conventions as `test_carregador_endereco_manual.py` (149).

Measured live 2026-09-22 on RODRIGO MORASCHI ENRIQUEZ / EUROVILLE-535: a
hand-registered código (`POST /{codigo}/registrar`, migration 149) has no
Vista mirror row at all, so `catalogo` is `{}` and `empreendimento` was
unconditionally `None` — the title silently omitted "RESIDENCIAL EUROVILLE".
"""
from __future__ import annotations

from app.modules.card_hub.contrato_gerador.carregador import _empreendimento

CATALOGO_COM_EMPREENDIMENTO = {"empreendimento": "Edifício Exemplo"}


def test_authored_value_wins_over_the_mirror():
    e = _empreendimento(
        CATALOGO_COM_EMPREENDIMENTO,
        {"empreendimento_manual": "Residencial Euroville"},
    )
    assert e == "Residencial Euroville"


def test_falls_back_to_the_mirror_when_the_authored_value_is_empty():
    e = _empreendimento(CATALOGO_COM_EMPREENDIMENTO, {"empreendimento_manual": None})
    assert e == "Edifício Exemplo"


def test_a_manually_registered_imovel_with_no_mirror_row_resolves_purely_from_the_override():
    """The manual path's whole point: a código the Vista mirror has never
    heard of (`catalogo == {}`) still resolves an empreendimento — from
    nothing but what a human typed. This is the exact EUROVILLE-535 gap."""
    e = _empreendimento({}, {"empreendimento_manual": "Residencial Euroville"})
    assert e == "Residencial Euroville"


def test_both_empty_resolves_to_none():
    """No authored override AND no mirror value — `titulo_curto`
    (`contexto.py`) already falls through to the address-only shape when
    `empreendimento` is `None`, with no dangling separator
    (`test_contrato_gerador_endereco_registro.TestTituloCurtoUsaEnderecoDoRegistro
    .test_sem_empreendimento_o_titulo_usa_o_endereco_do_registro` pins that
    branch); this only has to prove the carregador feeds it `None`, not `""`."""
    e = _empreendimento({}, {"empreendimento_manual": None})
    assert e is None


def test_a_blank_mirror_value_also_falls_through_to_none():
    e = _empreendimento({"empreendimento": None}, {"empreendimento_manual": None})
    assert e is None
