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


class TestTheWireShape:
    """🔴 Numerics leave as STRINGS — the bug live-testing found.

    PostgREST returns `numeric` as a JSON number. The contract says string,
    the frontend calls `.trim()` on it, and re-opening a saved negociação
    threw `TypeError: e.trim is not a function`. Nothing caught it because
    every fixture was hand-written as strings, i.e. written against the
    declared type instead of the wire.
    """

    def test_stored_numerics_come_back_as_strings(self, client, scoped):
        cid, aid = _seed(scoped)
        client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"valor_negociado": "500000.00", "pct_comissao": "6"},
            headers=_auth(),
        )
        body = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        for campo in (
            "valor_negociado",
            "pct_comissao",
            "pct_parceria",
            "pct_agencia",
            "pct_agentes",
            "pct_captador",
        ):
            assert isinstance(body[campo], str), f"{campo} = {body[campo]!r}"

    def test_a_numeric_that_arrives_as_a_float_is_still_returned_as_a_string(
        self, client, scoped
    ):
        """The real PostgREST shape, seeded directly as floats."""
        cid, aid = _seed(scoped)
        scoped.set_table_data(
            "atendimento_negociacao",
            [
                {
                    "atendimento_id": aid,
                    "org_id": ORG_ID,
                    "imovel_codigo": None,
                    "valor_negociado": 500000.0,
                    "pct_comissao": 6.0,
                    "tem_parceria": False,
                    "pct_parceria": 50.0,
                    "pct_agencia": 50.0,
                    "pct_agentes": 45.0,
                    "pct_captador": 5.0,
                    "formas_pagamento": None,
                    "parcelas": None,
                    "financiamento": False,
                    "fgts": False,
                    "observacoes": None,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": None,
                }
            ],
        )
        body = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        assert isinstance(body["valor_negociado"], str)
        assert isinstance(body["pct_agencia"], str)
        # And the split is still exact off those floats.
        assert body["calculo"]["comissao_total"] == "30000.00"

    def test_absent_numerics_stay_null_rather_than_the_string_None(
        self, client, scoped
    ):
        """`str(None)` would ship the literal text "None" into a form field."""
        cid, aid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        assert body["valor_negociado"] is None
        assert body["pct_comissao"] is None


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


# ─── The deal's imóvel (and the lead's, which is NOT it) ──────────────────


def _registry(*codigos, ativo=True) -> list[dict]:
    return [
        {
            "id": str(uuid4()),
            "org_id": ORG_ID,
            "codigo_canonical": c,
            "codigo_display": c,
            "ativo_no_vista": ativo,
            "origem_descoberta": "vista_sync",
            "snap_titulo": None,
            "snap_bairro": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        for c in codigos
    ]


def _seed_imovel(scoped, *codigos, ativo=True, mirror=None):
    scoped.set_table_data("imovel_registry", _registry(*codigos, ativo=ativo))
    scoped.set_table_data("imoveis", mirror or [])


class TestOImovelDoNegocio:
    """🔴 `imovel_codigo` is FK'd to `imovel_registry (org_id,
    codigo_canonical)` — an uppercase-only column (062/076). Before this,
    `atualizar` neither canonicalised nor checked it, so a lowercase spelling
    and a typo were both handed straight to PostgREST and came back as a raw
    foreign-key violation: a 500 that named a constraint and not the código the
    operator had just typed. `roteiros_service._validar_codigos` had already
    made exactly this argument for `visitas`."""

    def test_a_lowercase_codigo_is_canonicalised(self, client, scoped):
        cid, _aid = _seed(scoped)
        _seed_imovel(scoped, "ONE4770")

        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": "  one4770 "},
            headers=_auth(),
        )

        assert r.status_code == 200, r.text
        assert r.json()["imovel_codigo"] == "ONE4770"

    def test_an_unknown_codigo_is_a_404_naming_it_not_a_500(self, client, scoped):
        cid, _aid = _seed(scoped)
        _seed_imovel(scoped, "ONE4770")

        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": "ONE4771"},
            headers=_auth(),
        )

        assert r.status_code == 404, r.text
        assert "ONE4771" in r.text

    def test_a_sold_imovel_is_accepted(self, client, scoped):
        """The whole point of keying to the registry: an imóvel leaves the
        Vista catalog BECAUSE it was sold, which is exactly when its
        negociação is being written."""
        cid, _aid = _seed(scoped)
        _seed_imovel(scoped, "ONE4770", ativo=False)

        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": "ONE4770"},
            headers=_auth(),
        )

        assert r.status_code == 200, r.text
        assert r.json()["imovel_codigo"] == "ONE4770"

    def test_it_can_be_cleared(self, client, scoped):
        cid, _aid = _seed(scoped)
        _seed_imovel(scoped, "ONE4770")
        client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": "ONE4770"},
            headers=_auth(),
        )

        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": None},
            headers=_auth(),
        )

        assert r.status_code == 200, r.text
        assert r.json()["imovel_codigo"] is None


class TestTheLeadOriginIsNeverTheDeal:
    """🔴 THE LOAD-BEARING DISTINCTION, and half of a pair — the other half is
    `test_visita_proposta.py::TestTheDealFollowsTheAcceptance`.

    `leads.codigo_imovel` is the ORIGIN: the listing the person enquired about.
    `atendimento_negociacao.imovel_codigo` is the DEAL: the property actually
    being sold. The owner: "not necessarily that ref is the one that will have
    the proposta."

    It CAN be the same property and often is — which is why the origin comes
    back, clearly labelled and separate, for the UI to offer as a one-click
    shortcut. What no code does is take it on the operator's behalf. A
    prefilled deal property is a claim nobody made and it is indistinguishable
    on screen from one somebody verified.
    """

    def _seed_com_lead(self, scoped, *, codigo_imovel="ONE10337"):
        cid, aid = str(uuid4()), str(uuid4())
        lead_id = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
        scoped.set_table_data(
            "atendimentos", [_atendimento(aid, cid, lead_id=lead_id)]
        )
        scoped.set_table_data(
            "leads",
            [{"id": lead_id, "org_id": ORG_ID, "codigo_imovel": codigo_imovel}],
        )
        scoped.set_table_data("cliente_membros", [])
        scoped.set_table_data("lead_corretores", [])
        scoped.set_table_data("atendimento_negociacao", [])
        scoped.set_table_data("negociacao_defaults", [])
        scoped.set_table_data("imovel_dados", [])
        _seed_imovel(scoped, "ONE10337", "ONE9002")
        return cid, aid

    def test_the_deal_starts_empty_even_when_the_lead_names_a_listing(
        self, client, scoped
    ):
        cid, _aid = self._seed_com_lead(scoped)

        neg = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()

        assert neg["imovel_codigo"] is None

    def test_the_origin_comes_back_under_its_own_key(self, client, scoped):
        cid, _aid = self._seed_com_lead(scoped)

        neg = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()

        assert neg["lead_imovel"]["codigo"] == "ONE10337"
        # Enriched through the same path the picker uses, so the UI can render
        # "veio do anúncio ONE10337 — ..." identically to a picked row.
        assert "ativo_no_vista" in neg["lead_imovel"]

    def test_setting_the_deal_to_something_else_does_not_disturb_the_origin(
        self, client, scoped
    ):
        cid, _aid = self._seed_com_lead(scoped)

        neg = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": "ONE9002"},
            headers=_auth(),
        ).json()

        assert neg["imovel_codigo"] == "ONE9002"
        assert neg["lead_imovel"]["codigo"] == "ONE10337"

    def test_a_card_with_no_lead_reports_no_origin(self, client, scoped):
        cid, _aid = _seed(scoped)
        _seed_imovel(scoped, "ONE9002")

        neg = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()

        assert neg["lead_imovel"] is None

    def test_a_lead_with_a_blank_codigo_reports_no_origin(self, client, scoped):
        """Renders nothing rather than an empty affordance."""
        cid, _aid = self._seed_com_lead(scoped, codigo_imovel="")

        neg = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()

        assert neg["lead_imovel"] is None
