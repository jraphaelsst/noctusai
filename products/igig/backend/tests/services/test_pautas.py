"""Shared pauta generation (`app/services/pautas.py`) — achados 2 / 17 / comercial 1.

Exercised directly against the `igig` mock, independent of the HTTP routers:
this module is the ONE place both `orcamentos.aceitar` and
`comercial_funil._fechar` call, and the daily rolling-extension job.
"""
from datetime import timedelta

from app.dependencies import coerce_org_uuid
from app.services import pautas

ORG = str(coerce_org_uuid("test-org-123"))
OUTRA_ORG = str(coerce_org_uuid("outra-org-456"))
SEG, QUA, SEX = 1, 4, 16


def _item(igig_db, org_id, orcamento_id, *, dias=SEG | QUA | SEX, qtd=1, recorrente=True,
          secao="criacao_conteudo") -> dict:
    return igig_db.table("orcamento_item").insert({
        "org_id": org_id, "orcamento_id": orcamento_id, "produto_servico_id": None,
        "secao": secao, "descricao": "Post feed", "preco_unitario": 80,
        "recorrente": recorrente, "dias_semana": dias, "qtd_por_dia": qtd,
        "quantidade_mensal": 12, "subtotal": 960, "ordem": 0,
    }).execute().data[0]


class TestGerar:
    def test_only_recurring_criacao_items_generate_pautas(self, igig_db):
        from app.services.quadro_comum import hoje_local
        recorrente = _item(igig_db, ORG, "orc-1")
        nao_recorrente = _item(igig_db, ORG, "orc-1", secao="gestao_conta", recorrente=False)
        criadas = pautas.gerar(
            igig_db, ORG, itens=[recorrente, nao_recorrente], cliente_id="cliente-1",
            inicio=hoje_local(),
        )
        assert len(criadas) > 0
        assert all(p["orcamento_item_id"] == recorrente["id"] for p in criadas)

    def test_is_idempotent(self, igig_db):
        from app.services.quadro_comum import hoje_local
        item = _item(igig_db, ORG, "orc-2")
        primeira = pautas.gerar(igig_db, ORG, itens=[item], cliente_id="c", inicio=hoje_local())
        segunda = pautas.gerar(igig_db, ORG, itens=[item], cliente_id="c", inicio=hoje_local())
        assert len(segunda) == 0
        assert pautas.contar_geradas(igig_db, ORG, [item]) == len(primeira)


class TestEstender:
    def test_extends_past_the_original_window_without_duplicating(self, igig_db):
        from app.services.quadro_comum import hoje_local
        hoje = hoje_local()
        item = _item(igig_db, ORG, "orc-3")
        pautas.gerar(igig_db, ORG, itens=[item], cliente_id="c", inicio=hoje)
        total_30 = pautas.contar_geradas(igig_db, ORG, [item])

        # Re-running `estender` to the SAME horizon creates nothing new.
        pautas.estender(igig_db, ORG, itens=[item], cliente_id="c", ate=hoje + timedelta(days=29))
        assert pautas.contar_geradas(igig_db, ORG, [item]) == total_30

        # Pushing the horizon out (simulating the next day's job) adds more.
        pautas.estender(igig_db, ORG, itens=[item], cliente_id="c", ate=hoje + timedelta(days=40))
        assert pautas.contar_geradas(igig_db, ORG, [item]) > total_30


class TestEstenderPendentes:
    def _aceito(self, igig_db, org_id, *, contrato_status=None) -> dict:
        orc = igig_db.table("orcamento").insert({
            "org_id": org_id, "status": "aceito", "cliente_id": f"cliente-{org_id[:6]}",
        }).execute().data[0]
        _item(igig_db, org_id, orc["id"])
        if contrato_status is not None:
            igig_db.table("contrato").insert({
                "org_id": org_id, "orcamento_id": orc["id"], "status": contrato_status,
            }).execute()
        return orc

    def test_generates_for_accepted_deals_across_orgs(self, igig_db):
        self._aceito(igig_db, ORG)  # no contrato yet ⇒ eligible
        self._aceito(igig_db, OUTRA_ORG, contrato_status="ativo")  # contrato ativo ⇒ eligible
        resumo = pautas.estender_pendentes(igig_db)
        assert resumo["orcamentos"] == 2
        assert resumo["elegiveis"] == 2
        assert resumo["pautas_criadas"] > 0
        assert resumo["falhas"] == 0

    def test_skips_a_deal_whose_contract_is_not_live(self, igig_db):
        self._aceito(igig_db, ORG, contrato_status="aguardando_assinatura")
        resumo = pautas.estender_pendentes(igig_db)
        assert resumo["elegiveis"] == 0
        assert resumo["pautas_criadas"] == 0
