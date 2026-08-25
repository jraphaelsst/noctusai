"""Negociação — the commercial terms of a deal, and who gets what (077).

THE TWO CLAIMS WORTH DEFENDING
------------------------------
1. **The parts always sum to the whole.** Three independent
   `round(total * pct / 100, 2)` calls do not add back up. On a real sale
   that is a few centavos and a real problem: the agency's total and the sum
   of its slices disagree and neither is obviously wrong.

2. **A past agreement is never rewritten.** The org's split rule is COPIED
   onto a negociação when it is created. Swapping the rule afterwards must
   leave every existing deal exactly as it was agreed — including ones
   already paid out.

Auth is not re-tested here — `test_auth_boundary.py` enumerates every mounted
card_hub route (both routers) and asserts a strict 401 on each.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.modules.card_hub import negociacao_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str, **over) -> dict:
    row = {
        "id": aid,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "status": "aberta",
        "substituida_por": None,
        "arquivado": False,
        "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
    }
    row.update(over)
    return row


def _seed(scoped, *, membros=None, corretores=None, negociacoes=None, defaults=None,
          imovel_dados=None):
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("cliente_membros", membros or [])
    scoped.set_table_data("lead_corretores", corretores or [])
    scoped.set_table_data("atendimento_negociacao", negociacoes or [])
    scoped.set_table_data("negociacao_defaults", defaults or [])
    scoped.set_table_data("imovel_dados", imovel_dados or [])
    return cid, aid


def _corretor(nome):
    cid = str(uuid4())
    return cid, {"id": cid, "org_id": ORG_ID, "nome": nome, "cor": "#fff", "ativo": True}


class TestTheSplitIsExact:
    """🔴 `sum(parts) == total`, by construction, on awkward numbers."""

    def test_a_three_way_split_of_an_odd_amount_loses_no_centavo(self):
        total = Decimal("30000.01")
        partes = svc._ratear(total, [Decimal("50"), Decimal("45"), Decimal("5")])
        assert sum(partes) == total

    def test_seven_agents_sharing_a_hundred_reais_lose_nothing(self):
        total = Decimal("100.00")
        partes = svc._ratear(total, [Decimal("1")] * 7)
        assert sum(partes) == total
        # Largest-remainder: some get a centavo more, nobody gets zero.
        assert all(p > 0 for p in partes)

    def test_ten_centavos_across_three_still_balances(self):
        total = Decimal("0.10")
        partes = svc._ratear(total, [Decimal("1")] * 3)
        assert sum(partes) == total

    def test_a_zero_total_is_all_zeroes_not_a_crash(self):
        partes = svc._ratear(Decimal("0"), [Decimal("50"), Decimal("50")])
        assert partes == [Decimal("0.00"), Decimal("0.00")]


class TestTheUsersOwnNumbers:
    def test_no_parceria_splits_the_whole_commission_in_house(self, client, scoped):
        a_id, a_row = _corretor("Bia")
        cid, aid = _seed(
            scoped,
            membros=[{"org_id": ORG_ID, "cliente_id": None, "lead_corretor_id": a_id}],
            corretores=[a_row],
        )
        scoped.set_table_data(
            "cliente_membros",
            [{"org_id": ORG_ID, "cliente_id": cid, "lead_corretor_id": a_id}],
        )
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"valor_negociado": "500000.00", "pct_comissao": "6"},
            headers=_auth(),
        )
        assert r.status_code == 200
        calc = r.json()["calculo"]
        # 6% of 500.000 = 30.000; no parceria, so all of it is ours.
        assert calc["comissao_total"] == "30000.00"
        assert calc["parceria"] == "0.00"
        assert calc["nossa_parte"] == "30000.00"
        assert calc["agencia"] == "15000.00"      # 50%
        assert calc["agentes_total"] == "13500.00"  # 45%
        assert calc["captador_total"] == "1500.00"  # 5%

    def test_parceria_takes_half_the_total_then_we_split_our_half(
        self, client, scoped
    ):
        """The user's correction: 50-50 of the TOTAL, our half split in-house."""
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={
                "valor_negociado": "500000.00",
                "pct_comissao": "6",
                "tem_parceria": True,
            },
            headers=_auth(),
        )
        calc = r.json()["calculo"]
        assert calc["comissao_total"] == "30000.00"
        assert calc["parceria"] == "15000.00"
        assert calc["nossa_parte"] == "15000.00"
        assert calc["agencia"] == "7500.00"
        assert calc["agentes_total"] == "6750.00"
        assert calc["captador_total"] == "750.00"

    def test_the_agents_slice_is_divided_among_the_card_membros(
        self, client, scoped
    ):
        a_id, a_row = _corretor("Bia")
        b_id, b_row = _corretor("Caio")
        cid, aid = _seed(scoped, corretores=[a_row, b_row])
        scoped.set_table_data(
            "cliente_membros",
            [
                {"org_id": ORG_ID, "cliente_id": cid, "lead_corretor_id": a_id},
                {"org_id": ORG_ID, "cliente_id": cid, "lead_corretor_id": b_id},
            ],
        )
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"valor_negociado": "500000.00", "pct_comissao": "6"},
            headers=_auth(),
        )
        calc = r.json()["calculo"]
        assert calc["agentes_total"] == "13500.00"
        valores = sorted(a["valor"] for a in calc["agentes"])
        assert valores == ["6750.00", "6750.00"]
        assert sum(Decimal(a["valor"]) for a in calc["agentes"]) == Decimal("13500.00")

    def test_with_no_membros_the_agents_slice_is_unallocated_not_reassigned(
        self, client, scoped
    ):
        """🔴 The money is owed to somebody not yet named.

        Folding it into the agency's share would silently pay the agency for
        work it did not do, and nothing downstream would ever show it.
        """
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"valor_negociado": "500000.00", "pct_comissao": "6"},
            headers=_auth(),
        )
        calc = r.json()["calculo"]
        assert calc["agentes"] == []
        assert calc["agentes_total"] == "13500.00"   # still owed
        assert calc["agencia"] == "15000.00"          # NOT inflated

    def test_a_captador_that_is_not_set_leaves_the_slice_unattributed(
        self, client, scoped
    ):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"valor_negociado": "500000.00", "pct_comissao": "6"},
            headers=_auth(),
        )
        calc = r.json()["calculo"]
        assert calc["captador"] is None
        assert calc["captador_total"] == "1500.00"


class TestPastAgreementsAreNeverRewritten:
    """🔴 The reason the percentages are columns and not a lookup."""

    def test_swapping_the_org_rule_leaves_an_existing_negociacao_alone(
        self, client, scoped
    ):
        cid, aid = _seed(scoped)
        client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"valor_negociado": "500000.00", "pct_comissao": "6"},
            headers=_auth(),
        )

        novo = client.patch(
            "/api/negociacao/defaults",
            json={"pct_agencia": "70", "pct_agentes": "25", "pct_captador": "5"},
            headers=_auth(),
        )
        assert novo.status_code == 200

        depois = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        # Still the split that was agreed, not the new house rule.
        assert depois["pct_agencia"] == "50"
        assert depois["calculo"]["agencia"] == "15000.00"

    def test_the_new_rule_applies_to_the_NEXT_deal(self, client, scoped):
        client.patch(
            "/api/negociacao/defaults",
            json={"pct_agencia": "70", "pct_agentes": "25", "pct_captador": "5"},
            headers=_auth(),
        )
        cid, aid = _seed(scoped)
        # Re-seed wipes the defaults table, so set it again for this card.
        scoped.set_table_data(
            "negociacao_defaults",
            [
                {
                    "org_id": ORG_ID,
                    "pct_comissao": None,
                    "pct_parceria": "50",
                    "pct_agencia": "70",
                    "pct_agentes": "25",
                    "pct_captador": "5",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"valor_negociado": "500000.00", "pct_comissao": "6"},
            headers=_auth(),
        )
        assert r.json()["pct_agencia"] == "70"
        assert r.json()["calculo"]["agencia"] == "21000.00"


class TestRefusals:
    def test_a_split_that_does_not_total_100_is_refused_by_name(
        self, client, scoped
    ):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"pct_agencia": "50", "pct_agentes": "40", "pct_captador": "5"},
            headers=_auth(),
        )
        assert r.status_code == 400
        assert "100%" in r.text

    def test_a_derived_amount_cannot_be_written(self, client, scoped):
        """The breakdown is computed, never stored — so it cannot drift from
        the inputs that produced it."""
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"comissao_total": "999.00"},
            headers=_auth(),
        )
        assert r.status_code == 422
        assert "comissao_total" in r.text

    def test_a_percentage_over_100_is_refused(self, client, scoped):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"pct_comissao": "150"},
            headers=_auth(),
        )
        assert r.status_code == 422


class TestTheEmptyState:
    def test_a_card_with_no_terms_reads_as_the_org_defaults(self, client, scoped):
        """Not a 404 and not `{}` — no terms recorded is the normal state of a
        new deal, and the percentages to start from are the house rule."""
        cid, aid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        assert body["existe"] is False
        assert body["pct_agencia"] == "50"
        assert body["pct_agentes"] == "45"
        assert body["pct_captador"] == "5"
        assert body["pct_parceria"] == "50"

    def test_without_a_valor_the_split_says_so_instead_of_showing_zeroes(
        self, client, scoped
    ):
        """🔴 Zeroes would claim a split was computed. Terms are routinely
        drafted before a price is agreed."""
        cid, aid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        assert body["calculo"]["calculavel"] is False
        assert body["calculo"]["comissao_total"] is None
        assert "valor negociado" in body["calculo"]["motivo"]

    def test_no_commission_rate_is_invented_by_default(self, client, scoped):
        """The user specified the SPLIT, never a commission RATE."""
        cid, aid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        assert body["pct_comissao"] is None


class TestFinanciamentoFlags:
    def test_financiamento_and_fgts_round_trip(self, client, scoped):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"financiamento": True, "fgts": True},
            headers=_auth(),
        )
        assert r.json()["financiamento"] is True
        assert r.json()["fgts"] is True

    def test_formas_de_pagamento_and_parcelas_are_free_text_for_now(
        self, client, scoped
    ):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={
                "formas_pagamento": "entrada 100k + financiamento",
                "parcelas": "36x via banco",
            },
            headers=_auth(),
        )
        assert r.json()["formas_pagamento"] == "entrada 100k + financiamento"
        assert r.json()["parcelas"] == "36x via banco"
