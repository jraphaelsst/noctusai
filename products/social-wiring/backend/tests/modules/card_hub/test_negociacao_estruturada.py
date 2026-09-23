"""Negociação estruturada — parcelas, favorecidos, intermediários (108).

THE TWO CLAIMS WORTH DEFENDING
------------------------------
1. **`saldo_nao_alocado` and `completude` never block a save.** A parcela
   schedule that does not yet cover `valor_negociado` is reported, not
   refused — terms are drafted over several sittings.
2. **A favorecido must belong to the SAME atendimento as the parcela.** Cross-
   atendimento is a 404 naming the id, never a raw FK violation.

Auth is not re-tested here — `test_auth_boundary.py` (generic sweep) and
`test_auth_boundary_negociacao_estruturada.py` (this migration's routes)
both assert a strict 401 on every mounted route.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

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


def _seed(scoped, *, com_negociacao=False, negociacao_over=None, parcelas=None,
          favorecidos=None, intermediarios=None):
    """`com_negociacao=True` seeds `atendimento_negociacao` with
    `_negociacao_row(aid)` — `aid` cannot be known to the CALLER before this
    function generates it, so the row is built INSIDE, not passed in."""
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("cliente_membros", [])
    scoped.set_table_data("lead_corretores", [])
    negociacoes = (
        [_negociacao_row(aid, **(negociacao_over or {}))] if com_negociacao else []
    )
    scoped.set_table_data("atendimento_negociacao", negociacoes)
    scoped.set_table_data("negociacao_defaults", [])
    scoped.set_table_data("imovel_dados", [])
    scoped.set_table_data("atendimento_negociacao_parcelas", parcelas or [])
    scoped.set_table_data("atendimento_favorecidos", favorecidos or [])
    scoped.set_table_data("atendimento_intermediarios", intermediarios or [])
    return cid, aid


def _negociacao_row(aid: str, **over) -> dict:
    row = {
        "atendimento_id": aid,
        "org_id": ORG_ID,
        "imovel_codigo": None,
        "valor_negociado": "500000.00",
        "pct_comissao": "6",
        "tem_parceria": False,
        "pct_parceria": "50",
        "pct_agencia": "50",
        "pct_agentes": "45",
        "pct_captador": "5",
        "formas_pagamento": None,
        "parcelas": None,
        "financiamento": False,
        "fgts": False,
        "observacoes": None,
        "posse_data": None,
        "posse_condicoes": None,
        "permuta_ativo_id": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": None,
    }
    row.update(over)
    return row


class TestTheAggregateView:
    def test_a_deal_with_no_terms_reports_no_saldo_and_missing_valor(
        self, client, scoped
    ):
        cid, aid = _seed(scoped)
        r = client.get(
            f"/api/clientes/{cid}/negociacao/estruturada", headers=_auth()
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["saldo_nao_alocado"] is None
        assert body["parcelas"] == []
        assert "valor_negociado" in body["completude"]["faltando"]
        assert body["completude"]["completo"] is False

    def test_a_valor_with_no_parcelas_is_the_full_saldo_unallocated(
        self, client, scoped
    ):
        cid, aid = _seed(scoped, com_negociacao=True)
        body = client.get(
            f"/api/clientes/{cid}/negociacao/estruturada", headers=_auth()
        ).json()
        assert body["saldo_nao_alocado"] == "500000.00"
        assert "parcelas" in body["completude"]["faltando"]


class TestParcelasDoNotBlockAPartialSave:
    def test_a_single_parcela_short_of_the_total_reports_the_remainder(
        self, client, scoped
    ):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "sinal", "valor": "100000.00"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert len(body["parcelas"]) == 1
        assert body["saldo_nao_alocado"] == "400000.00"
        # Not refused — a partial schedule is a normal draft state.
        assert body["completude"]["completo"] is False
        assert "parcelas_nao_cobrem_valor_negociado" in body["completude"]["faltando"]

    def test_parcelas_covering_the_full_valor_are_complete_on_that_axis(
        self, client, scoped
    ):
        cid, aid = _seed(scoped, com_negociacao=True)
        client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "sinal", "valor": "200000.00"},
            headers=_auth(),
        )
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "saldo", "valor": "300000.00"},
            headers=_auth(),
        )
        body = r.json()
        assert body["saldo_nao_alocado"] == "0.00" or body["saldo_nao_alocado"] == "0"
        assert "parcelas_nao_cobrem_valor_negociado" not in body["completude"]["faltando"]

    def test_over_allocating_is_reported_not_refused(self, client, scoped):
        """🔴 `saldo_nao_alocado` can go negative — the service never blocks a
        write on it."""
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "direta", "valor": "600000.00"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        assert Decimal(r.json()["saldo_nao_alocado"]) == Decimal("-100000.00")

    def test_a_parcela_can_be_updated_and_removed(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        created = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "sinal", "valor": "100000.00"},
            headers=_auth(),
        ).json()
        parcela_id = created["parcelas"][0]["id"]

        patched = client.patch(
            f"/api/clientes/{cid}/negociacao/parcelas/{parcela_id}",
            json={"valor": "150000.00", "confissao_divida": True},
            headers=_auth(),
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["parcelas"][0]["valor"] == "150000.00"
        assert patched.json()["parcelas"][0]["confissao_divida"] is True

        removed = client.delete(
            f"/api/clientes/{cid}/negociacao/parcelas/{parcela_id}",
            headers=_auth(),
        )
        assert removed.status_code == 204
        depois = client.get(
            f"/api/clientes/{cid}/negociacao/estruturada", headers=_auth()
        ).json()
        assert depois["parcelas"] == []

    def test_an_unknown_parcela_is_a_404(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao/parcelas/{uuid4()}",
            json={"valor": "1.00"},
            headers=_auth(),
        )
        assert r.status_code == 404


class TestParcelaOrdemIsServerComputed:
    """`criar_parcela` used to write `ordem=0` for EVERY new parcela
    (`ParcelaCreateBody` never accepted the field from the client, and the
    service fell back to the schema default) — every parcela created through
    the single-create endpoint tied at `ordem=0`, so the printed contract
    numbering ("Parcela 01/02/03") + `VENCIMENTOS_FORA_DE_ORDEM` + the
    `posse_marco_parcela_id` marco all silently rested on `created_at`
    instead. `ordem` is now `max(existing) + 1`, same rule
    `dividir_saldo_em_parcelas` already used for its batch insert."""

    def test_three_sequential_creates_get_three_distinct_increasing_ordens(
        self, client, scoped
    ):
        cid, aid = _seed(scoped, com_negociacao=True)
        r1 = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "sinal", "valor": "100000.00"},
            headers=_auth(),
        )
        r2 = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "intermediaria", "valor": "190000.00"},
            headers=_auth(),
        )
        r3 = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "financiamento", "valor": "1160000.00"},
            headers=_auth(),
        )
        assert r1.status_code == r2.status_code == r3.status_code == 201

        parcelas = {p["tipo"]: p["ordem"] for p in r3.json()["parcelas"]}
        assert parcelas["sinal"] == 0
        assert parcelas["intermediaria"] == 1
        assert parcelas["financiamento"] == 2

    def test_a_client_supplied_ordem_on_create_is_ignored(self, client, scoped):
        """`ParcelaCreateBody` does not even accept `ordem` — `extra='forbid'`
        (`StrictHttpModel`) refuses it as an UNKNOWN field, same as any other
        field this endpoint does not own."""
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "sinal", "valor": "100000.00", "ordem": 7},
            headers=_auth(),
        )
        assert r.status_code == 422, r.text

    def test_ordem_still_increments_past_an_existing_gap(self, client, scoped):
        """A PATCH-reordered gap (e.g. ordem bumped to 5) must not be
        overwritten by the next create landing back at a low number."""
        cid, aid = _seed(scoped, com_negociacao=True)
        primeira = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "sinal", "valor": "50000.00"},
            headers=_auth(),
        ).json()["parcelas"][0]
        client.patch(
            f"/api/clientes/{cid}/negociacao/parcelas/{primeira['id']}",
            json={"ordem": 5},
            headers=_auth(),
        )

        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "saldo", "valor": "450000.00"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        nova = next(p for p in r.json()["parcelas"] if p["tipo"] == "saldo")
        assert nova["ordem"] == 6


class TestFavorecidoScoping:
    """🔴 A parcela's favorecido must belong to the SAME atendimento."""

    def test_creating_a_favorecido_and_pointing_a_parcela_at_it(
        self, client, scoped
    ):
        cid, aid = _seed(scoped, com_negociacao=True)
        fav = client.post(
            f"/api/clientes/{cid}/negociacao/favorecidos",
            json={"nome": "Maria Vendedora", "cpf_cnpj": "111.222.333-44",
                  "banco": "104", "agencia": "1234", "conta": "56789-0",
                  "pix": "maria@example.com"},
            headers=_auth(),
        )
        assert fav.status_code == 201, fav.text
        favorecido_id = fav.json()["favorecidos"][0]["id"]

        parcela = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "saldo", "valor": "500000.00",
                  "favorecido_id": favorecido_id},
            headers=_auth(),
        )
        assert parcela.status_code == 201, parcela.text
        assert parcela.json()["parcelas"][0]["favorecido_id"] == favorecido_id

    def test_a_favorecido_from_another_atendimento_is_a_404_not_a_500(
        self, client, scoped
    ):
        cid, aid = _seed(scoped, com_negociacao=True)
        outro_aid = str(uuid4())
        estranho_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_favorecidos",
            [{
                "id": estranho_id, "org_id": ORG_ID,
                "atendimento_id": outro_aid, "nome": "De outro card",
                "cpf_cnpj": None, "banco": None, "agencia": None,
                "conta": None, "pix": None,
                "created_at": "2026-01-01T00:00:00+00:00", "created_por": None,
                "updated_at": None, "updated_por": None,
            }],
        )

        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "saldo", "valor": "500000.00",
                  "favorecido_id": estranho_id},
            headers=_auth(),
        )
        assert r.status_code == 404, r.text

    def test_a_favorecido_can_be_updated_and_removed(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        fav = client.post(
            f"/api/clientes/{cid}/negociacao/favorecidos",
            json={"nome": "Maria"},
            headers=_auth(),
        ).json()
        favorecido_id = fav["favorecidos"][0]["id"]

        patched = client.patch(
            f"/api/clientes/{cid}/negociacao/favorecidos/{favorecido_id}",
            json={"pix": "novo-pix@example.com"},
            headers=_auth(),
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["favorecidos"][0]["pix"] == "novo-pix@example.com"

        removed = client.delete(
            f"/api/clientes/{cid}/negociacao/favorecidos/{favorecido_id}",
            headers=_auth(),
        )
        assert removed.status_code == 204


class TestIntermediarios:
    def test_a_percentual_intermediario_round_trips(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "Corretor Parceiro", "creci": "12345-F",
                  "tipo": "percentual", "valor": "10"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        item = r.json()["intermediarios"][0]
        assert item["nome"] == "Corretor Parceiro"
        assert item["valor"] == "10"

    def test_a_percentual_over_100_is_refused(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "X", "tipo": "percentual", "valor": "150"},
            headers=_auth(),
        )
        assert r.status_code == 400
        assert "0 e 100" in r.text

    def test_a_valor_fixo_intermediario_round_trips(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "X", "tipo": "valor_fixo", "valor": "5000.00"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["intermediarios"][0]["valor"] == "5000.00"

    def test_remover_an_intermediario(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        created = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "X"},
            headers=_auth(),
        ).json()
        iid = created["intermediarios"][0]["id"]
        removed = client.delete(
            f"/api/clientes/{cid}/negociacao/intermediarios/{iid}",
            headers=_auth(),
        )
        assert removed.status_code == 204


class TestIntermediarioNaturezaParceiroSemCreci:
    """Migration 162. `natureza='parceiro_split'` — a commission-split
    beneficiary the generated contract never qualifies as a contracted
    party (matches reference contract 08's own shape: its 3rd beneficiary
    appears only in the split-payment paragraph, never in "as empresas a
    seguir qualificadas"), and is therefore never required to carry a
    CRECI. Before 162, every `atendimento_intermediarios` row required one
    unconditionally — making it impossible to add this party at all without
    either fabricating a CRECI or leaving it out (the observed bug: a
    generated commission clause 2 recipients wide instead of 3)."""

    def test_natureza_defaults_to_intermediario(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "Corretor Parceiro", "creci": "12345-F"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["intermediarios"][0]["natureza"] == "intermediario"
        assert r.json()["intermediarios"][0]["papel"] is None

    def test_a_parceiro_sem_creci_round_trips_without_creci(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={
                "nome": "SBCM Parceiros Imobiliários LTDA",
                "natureza": "parceiro_split",
                "tipo": "percentual",
                "valor": "5",
                "pessoa_tipo": "pj",
                "documento": "45646535000172",
                "papel": "indicação",
            },
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        item = r.json()["intermediarios"][0]
        assert item["natureza"] == "parceiro_split"
        assert item["creci"] is None
        assert item["valor"] == "5"
        assert item["papel"] == "indicação"

    def test_natureza_invalida_is_refused(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "X", "natureza": "bogus"},
            headers=_auth(),
        )
        assert r.status_code == 422, r.text  # pydantic Literal rejects it first

    def test_parceiro_split_paired_with_corretor_id_is_refused(self, client, scoped):
        """A `corretor_id`-linked row IS one of the office's own qualified
        parties by definition (`contexto.py` qualifies `Imobiliaria`
        whenever any row carries a `corretor_id`) — pairing it with
        `parceiro_split` is a contradiction the service refuses with a
        named 400 (migration 162's DB CHECK is the backstop)."""
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={
                "nome": "Corretor da Casa",
                "corretor_id": str(uuid4()),
                "natureza": "parceiro_split",
            },
            headers=_auth(),
        )
        assert r.status_code == 400, r.text
        assert "parceiro_split" in r.text

    def test_patch_can_switch_natureza_to_parceiro_split(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        created = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "X", "creci": "12345-F"},
            headers=_auth(),
        ).json()
        iid = created["intermediarios"][0]["id"]
        patched = client.patch(
            f"/api/clientes/{cid}/negociacao/intermediarios/{iid}",
            json={"natureza": "parceiro_split", "papel": "indicação"},
            headers=_auth(),
        )
        assert patched.status_code == 200, patched.text
        item = patched.json()["intermediarios"][0]
        assert item["natureza"] == "parceiro_split"
        assert item["papel"] == "indicação"

    def test_patch_natureza_to_null_is_refused(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        created = client.post(
            f"/api/clientes/{cid}/negociacao/intermediarios",
            json={"nome": "X"},
            headers=_auth(),
        ).json()
        iid = created["intermediarios"][0]["id"]
        r = client.patch(
            f"/api/clientes/{cid}/negociacao/intermediarios/{iid}",
            json={"natureza": None},
            headers=_auth(),
        )
        assert r.status_code == 400, r.text


class TestDividirSaldo:
    """The pure split helper (`noctusai_lib.domain.real_estate.
    parcelamento`), wired into a convenience endpoint."""

    def test_divides_the_current_saldo_evenly_remainder_on_the_last(
        self, client, scoped
    ):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas/dividir-saldo",
            json={"num_parcelas": 3},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        valores = sorted(Decimal(p["valor"]) for p in body["parcelas"])
        assert sum(valores) == Decimal("500000.00")
        assert len(body["parcelas"]) == 3
        assert body["saldo_nao_alocado"] == "0.00" or Decimal(body["saldo_nao_alocado"]) == 0

    def test_dividing_with_no_valor_negociado_is_refused_by_name(
        self, client, scoped
    ):
        cid, aid = _seed(scoped)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas/dividir-saldo",
            json={"num_parcelas": 3},
            headers=_auth(),
        )
        assert r.status_code == 400
        assert "valor negociado" in r.text

    def test_dividing_with_no_remaining_saldo_is_refused(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        client.post(
            f"/api/clientes/{cid}/negociacao/parcelas",
            json={"tipo": "direta", "valor": "500000.00"},
            headers=_auth(),
        )
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas/dividir-saldo",
            json={"num_parcelas": 2},
            headers=_auth(),
        )
        assert r.status_code == 400

    def test_monthly_due_dates_when_a_starting_date_is_given(self, client, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"/api/clientes/{cid}/negociacao/parcelas/dividir-saldo",
            json={"num_parcelas": 3, "vencimento_inicial": "2026-01-31"},
            headers=_auth(),
        )
        vencimentos = sorted(p["vencimento"] for p in r.json()["parcelas"])
        assert vencimentos == ["2026-01-31", "2026-02-28", "2026-03-31"]


class TestPosseAndPermutaOnNegociacao:
    """migration 108's three new columns on `atendimento_negociacao` itself."""

    def test_posse_data_and_condicoes_round_trip(self, client, scoped):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"posse_data": "2026-06-01",
                  "posse_condicoes": "na assinatura"},
            headers=_auth(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["posse_data"] == "2026-06-01"
        assert r.json()["posse_condicoes"] == "na assinatura"

    def test_an_unknown_permuta_ativo_is_a_404_naming_it(self, client, scoped):
        cid, aid = _seed(scoped)
        scoped.set_table_data("permuta_ativos", [])
        estranho = str(uuid4())
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"permuta_ativo_id": estranho},
            headers=_auth(),
        )
        assert r.status_code == 404
        assert estranho in r.text

    def test_a_known_permuta_ativo_is_accepted(self, client, scoped):
        cid, aid = _seed(scoped)
        ativo_id = str(uuid4())
        scoped.set_table_data(
            "permuta_ativos",
            [{"id": ativo_id, "org_id": ORG_ID}],
        )
        r = client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"permuta_ativo_id": ativo_id},
            headers=_auth(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["permuta_ativo_id"] == ativo_id
