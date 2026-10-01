"""A matrícula qualification must not displace a value still sustained by the
person's own identity document (live measured defect, prod 2026-10-01)."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import identidade_extracao_service as svc
from app.modules.matriculas.qualificacao_service import CAMPOS_QUALIFICACAO
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import _cenario, _cliente, _conflitos, _doc

ORG_UUID = UUID(ORG_ID)
ALTA = "alta"


def _lidos(nome, rg):
    return {
        "nome_oficial": (nome, ALTA, None, True),
        "rg": (rg, ALTA, None, True),
    }


def test_matricula_never_overwrites_a_value_the_live_cnh_still_asserts(client, scoped):
    cid = str(uuid4())
    cnh = _doc(cid, "cnh", extracao_nome="JOANA MARIA SOUZA LIMA", extracao_rg="12345678")
    _cenario(
        scoped,
        cliente_row(cid, nome_oficial="JOANA MARIA SOUZA LIMA", nome_oficial_origem="cnh",
                    nome_oficial_documento_id=cnh["id"],
                    rg="12345678", rg_origem="cnh", rg_documento_id=cnh["id"]),
        [cnh], [],
    )
    svc.aplicar_campos_ao_cliente(
        scoped, ORG_UUID, UUID(cid), "matricula",
        _lidos("JOANA SOUZA", "98765432"),
        campos=CAMPOS_QUALIFICACAO,
        documento_id=None, fonte_tabela="matricula_qualificacoes", fonte_id=str(uuid4()),
    )
    row = _cliente(scoped, cid)
    assert row["nome_oficial"] == "JOANA MARIA SOUZA LIMA"
    assert row["rg"] == "12345678"
    regras = [c.get("motivo_resolucao") or "" for c in _conflitos(scoped)]
    assert not any("retratado" in r for r in regras), regras


def test_a_matricula_never_outranks_an_identity_document_on_tier_alone():
    """Precedence pin: a matrícula is the registry's HISTORICAL record of the
    owner; for nome/rg/cpf it must never WIN on measured tier against the
    person's own identity document (cnh/rg), in either direction. Equal or
    unmeasured stays a human conflict."""
    from app.services import divergencia_resolucao as dr

    for campo in ("nome_oficial", "rg", "cpf"):
        for doc in ("cnh", "rg"):
            for atual, proposto in ((doc, "matricula"), ("matricula", doc)):
                d = dr.resolver_divergencia(
                    campo,
                    valor_atual="AAA 111", origem_atual=atual,
                    valor_proposto="BBB 222", origem_proposto=proposto,
                    mesmo_valor=lambda _c, a, b: a == b,
                )
                esperado = "atual" if atual == doc else "proposto"
                assert d.requer_humano or d.vencedor == esperado, (campo, atual, proposto, d)
