"""F71: a saved contract matrícula selection whose imóvel documento was
soft-deleted is never quoted — the readiness gate blocks instead."""
from __future__ import annotations

from uuid import UUID

from app.modules.matriculas import estrutura_service as svc
from tests.modules.matriculas.conftest import (
    ORG_ID,
    contrato_row,
    documento_row,
    extracao_row,
    negociacao_row,
    seed,
)
from tests.modules.matriculas.test_estrutura_service_selecao_ruido import _selecionar

ORG = UUID(ORG_ID)


def _cenario(scoped, *, removido: bool):
    doc = documento_row()
    if removido:
        doc["deleted_at"] = "2026-10-22T10:00:00+00:00"
    ext = extracao_row(imovel_documento_id=doc["id"])
    contrato = contrato_row()
    seed(
        scoped, extracoes=[ext], documentos=[doc], contratos=[contrato],
        negociacoes=[negociacao_row(contrato["atendimento_id"])],
    )
    atos = svc.listar_atos(scoped, ORG, UUID(ext["id"]))["atos"]
    abertura = next(a for a in atos if a["kind"] == "abertura")
    scoped.set_table_data(
        "atendimento_contrato_matricula_atos", _selecionar(contrato["id"], ext["id"], [abertura])
    )
    return contrato


def test_a_selection_on_a_removed_documento_is_withheld_and_flagged(scoped):
    contrato = _cenario(scoped, removido=True)

    out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

    assert out["extracao_removida"] is True
    assert out["atos"] == [] and out["texto"] == "" and out["extracao_id"] is None


def test_a_selection_on_a_live_documento_is_quoted(scoped):
    contrato = _cenario(scoped, removido=False)

    out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

    assert out["extracao_removida"] is False and out["atos"] and out["texto"]


def test_the_readiness_gate_blocks_with_the_pt_br_message():
    from dataclasses import replace

    from app.modules.card_hub.contrato_gerador import derivacao
    from tests.modules.card_hub import contrato_gerador_fixtures as fx

    d = fx.base_v1()
    d = replace(d, matricula=replace(d.matricula, extracao_removida=True, num_atos=0, texto=""))
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA)

    bloqueios = {b["codigo"]: b for b in av.bloqueios}
    assert av.pronto is False
    assert "MATRICULA_REMOVIDA" in bloqueios
    assert "removida" in str(bloqueios["MATRICULA_REMOVIDA"]) and "escolha outra" in str(
        bloqueios["MATRICULA_REMOVIDA"]
    )
