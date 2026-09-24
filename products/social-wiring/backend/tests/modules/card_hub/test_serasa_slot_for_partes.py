"""P1 (folder 883, 2026-09-24) — the `serasa_crednet` checklist slot, and
every other card-tab keyed off `resolve_atendimento_id`, went blind for a
non-titular cliente.

THE LIVE BUG
------------
`documento_checklist_service._e_certificando` (and `empresas_service.
listar`, and `certidoes_matriz_service.resolver_colunas`) all resolved
"the" atendimento via `card_hub.services.resolve_atendimento_id`, which
only ever looks at `atendimentos.cliente_id` — the TITULAR column. A
vendedor is always an `atendimento_partes` row, never the titular, so the
lookup found zero rows, raised `AmbiguousAtendimento([])`, and every one of
these callers read that as "nothing to show" — hiding the Serasa slot,
the empresas panel, and the certidões matriz for every vendedor's own card.

THE FIX
-------
`services.atendimentos_abertos_certificaveis` /
`resolve_atendimento_id_incluindo_partes` also look at `atendimento_partes`
(either lado) and at a vendedor's registered cônjuge
(`clientes.conjuge_cliente_id`) with no `atendimento_partes` row of its
own. These tests pin the real shape from the live repro: a titular
comprador, a vendedora added via "Adicionar vendedor", and that vendedora's
cônjuge who is NOT a parte.
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub import certidoes_matriz_service as matriz_svc
from app.modules.card_hub import documento_checklist_service as checklist_svc
from app.modules.card_hub import empresas_service as empresas_svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _atendimento(aid: str, cliente_id: str, **over) -> dict:
    row = {
        "id": aid, "org_id": ORG_ID, "cliente_id": cliente_id,
        "lead_id": None, "meta_ads_lead_id": None, "status": "aberta",
        "substituida_por": None, "arquivado": False, "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }
    row.update(over)
    return row


def _parte(atendimento_id: str, cliente_id: str, *, lado: str, papel: str) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atendimento_id,
        "cliente_id": cliente_id, "lado": lado, "papel": papel, "ordem": 0,
        "observacao": None, "created_at": "2026-01-01T00:00:00+00:00",
        "created_by": None, "updated_at": None,
    }


def _seed_deal(scoped):
    """The live repro's shape: a titular comprador, a vendedora `parte`,
    and the vendedora's cônjuge who is NOT a parte — only registered via
    `clientes.conjuge_cliente_id`."""
    titular_id, vendedora_id, conjuge_id, aid = (
        str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    )
    for t in (
        "clientes", "atendimentos", "atendimento_partes", "cliente_documentos",
        "cliente_documento_checklist", "cliente_empresa_participacoes",
        "atendimento_negociacao_parcelas", "empresas", "certidao_consultas",
        "certidao_resultados", "empresa_documentos",
    ):
        scoped.set_table_data(t, [])
    # The registered marriage: the VENDEDORA's own `clientes` row points at
    # her cônjuge (`_e_certificando_no_atendimento`'s lookup reads
    # `clientes.conjuge_cliente_id == <person being checked>`, joined
    # against the vendedor `atendimento_partes` rows by THAT row's `id` —
    # so it is the vendedora's row, not the cônjuge's, that carries the
    # link).
    scoped.set_table_data("clientes", [
        cliente_row(titular_id, nome="Comprador Titular"),
        cliente_row(vendedora_id, nome="Vendedora", conjuge_cliente_id=conjuge_id),
        cliente_row(conjuge_id, nome="Conjuge Da Vendedora"),
    ])
    scoped.set_table_data("atendimentos", [_atendimento(aid, titular_id)])
    scoped.set_table_data("atendimento_partes", [
        _parte(aid, vendedora_id, lado="vendedor", papel="proprietario"),
    ])
    return titular_id, vendedora_id, conjuge_id, aid


class TestSerasaSlotForAParte:
    def test_a_vendedora_parte_keeps_her_serasa_slot(self, scoped):
        _titular_id, vendedora_id, _conjuge_id, _aid = _seed_deal(scoped)

        resultado = checklist_svc.listar(scoped, ORG_ID, vendedora_id)

        assert "serasa_crednet" in [i["key"] for i in resultado["items"]]

    def test_the_vendedoras_conjuge_without_a_parte_row_also_gets_it(self, scoped):
        _titular_id, _vendedora_id, conjuge_id, _aid = _seed_deal(scoped)

        resultado = checklist_svc.listar(scoped, ORG_ID, conjuge_id)

        assert "serasa_crednet" in [i["key"] for i in resultado["items"]]

    def test_a_pure_comprador_side_parte_still_does_not_get_it(self, scoped):
        """No regression: a comprador-side parte with no permuta is still
        not a certificando — the fix only stops a non-titular from being
        wrongly resolved to NO atendimento at all, it does not change WHO
        counts as certificando."""
        titular_id, _vendedora_id, _conjuge_id, aid = _seed_deal(scoped)
        outro_comprador = str(uuid4())
        scoped.set_table_data("clientes", [
            cliente_row(titular_id, nome="Comprador Titular"),
            cliente_row(outro_comprador, nome="Comprador Dois"),
        ])
        scoped.set_table_data("atendimento_partes", [
            _parte(aid, outro_comprador, lado="comprador", papel="comprador"),
        ])

        resultado = checklist_svc.listar(scoped, ORG_ID, outro_comprador)

        assert "serasa_crednet" not in [i["key"] for i in resultado["items"]]


class TestEmpresasListarForAParte:
    def test_a_vendedora_can_open_her_own_empresas_panel(self, scoped):
        _titular_id, vendedora_id, _conjuge_id, aid = _seed_deal(scoped)
        empresa = {
            "id": str(uuid4()), "org_id": ORG_ID, "cnpj": "11222333000181",
            "razao_social": "Empresa Da Vendedora LTDA", "nome_fantasia": None,
            "natureza_juridica": None, "data_abertura": None,
            "situacao_cadastral": "ativa", "data_situacao_cadastral": None,
            "motivo_situacao": None, "dados_origem": None, "dados_documento_id": None,
            "dados_em": None, "dados_confirmado_por": None, "dados_confirmado_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
        }
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": vendedora_id,
            "empresa_id": empresa["id"], "participacao_pct": "50.00", "desde": None,
            "fonte_documento_id": None, "origem": "manual",
            "confirmado_por": None, "confirmado_em": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }])

        do_titular = empresas_svc.listar(scoped, ORG_ID, _titular_id)
        da_vendedora = empresas_svc.listar(scoped, ORG_ID, vendedora_id)

        assert da_vendedora["atendimento_id"] == aid
        assert da_vendedora["atendimento_id"] == do_titular["atendimento_id"]
        assert len(da_vendedora["items"]) == 1


class TestCertidoesMatrizForAParte:
    def test_a_vendedora_can_open_her_own_matriz_tab(self, scoped):
        _titular_id, vendedora_id, _conjuge_id, aid = _seed_deal(scoped)

        atendimento_id, colunas = matriz_svc.resolver_colunas(scoped, ORG_ID, vendedora_id)

        assert atendimento_id == aid
        assert any(c.get("kind") == "pessoa" and c.get("id") == vendedora_id for c in colunas)
