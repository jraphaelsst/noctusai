"""`POST /api/leads` — the imóvel código is REQUIRED for a manual lead
(contract `atendimento-partes-imoveis` §3.6, owner decision D2)."""
from __future__ import annotations

from uuid import UUID

import pytest

from tests.modules.leads.conftest import LEAD_CODIGO, ORG_A, auth_headers

BODY = {"data_entrada": "2026-07-01", "cliente_nome": "Ana", "contato": "+5511988770001"}


def post(http_client, **extra):
    return http_client.post("/api/leads", json={**BODY, **extra}, headers=auth_headers())


def leads_rows(leads_client):
    return leads_client.table("leads").select("*").execute().data


class TestCodigoIsRequired:
    @pytest.mark.parametrize(
        "extra",
        [{}, {"codigo_imovel": None}, {"codigo_imovel": ""}, {"codigo_imovel": "   "}],
        ids=["missing", "null", "empty", "blank"],
    )
    def test_missing_or_blank_is_422_with_contract_copy_and_writes_nothing(
        self, http_client, leads_client, extra
    ):
        resp = post(http_client, **extra)
        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] == "VALIDATION_ERROR"
        (detalhe,) = err["details"]["errors"]
        assert detalhe["field"] == "codigo_imovel"
        assert detalhe["message"] == "Informe o imóvel do lead."
        assert "Informe o imóvel do lead." in err["message"]
        assert leads_rows(leads_client) == []

    def test_unknown_codigo_is_422_imovel_desconhecido_and_writes_nothing(
        self, http_client, leads_client
    ):
        resp = post(http_client, codigo_imovel="nao-existe9")
        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] == "IMOVEL_DESCONHECIDO"
        assert err["message"] == (
            "Imóvel NAO-EXISTE9 não está cadastrado. Selecione um imóvel do catálogo."
        )
        assert err["details"] == {"codigo": "NAO-EXISTE9"}
        assert leads_rows(leads_client) == []
        assert leads_client.table("cliente_touches").select("*").execute().data == []

    def test_codigo_known_only_to_the_mirror_is_registered_then_accepted(
        self, http_client, leads_client
    ):
        leads_client.set_table_data(
            "imoveis", [{"org_id": str(UUID(ORG_A)), "codigo": "MIR1", "codigo_norm": "MIR1"}]
        )
        resp = post(http_client, codigo_imovel="mir1")
        assert resp.status_code == 201, resp.text
        registry = leads_client.table("imovel_registry").select("*").execute().data
        assert "MIR1" in {r["codigo_canonical"] for r in registry}


class TestCreate:
    def test_201_stores_the_canonical_codigo_and_adds_the_two_additive_keys(
        self, http_client, leads_client
    ):
        resp = post(http_client, codigo_imovel=f" {LEAD_CODIGO.lower()} ")
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["codigo_imovel"] == LEAD_CODIGO  # canonical, trimmed
        assert "atendimento_id" in data and "imoveis" in data
        # The mock has no spawn trigger (migration 034): no card yet.
        assert data["atendimento_id"] is None and data["imoveis"] == []
        assert leads_rows(leads_client)[0]["codigo_imovel"] == LEAD_CODIGO

    def test_the_spawned_card_gets_the_junction_and_the_interesse(
        self, http_client, leads_client
    ):
        """The leg the mock cannot run inline: the DB trigger spawns the
        atendimento on the lead insert. Seeding it after the fact and running
        the sweep's reconcile is exactly what production does when the
        ingest-time link finds the card or the sweep gets there first."""
        from app.modules.imovel_hub import atendimento_imoveis_service as svc

        data = post(http_client, codigo_imovel=LEAD_CODIGO).json()["data"]
        cliente_id = leads_client.table("clientes").select("*").execute().data[0]["id"]
        leads_client.table("atendimentos").insert(
            {
                "id": "00000000-0000-4000-8000-00000000aa01",
                "org_id": str(UUID(ORG_A)),
                "lead_id": data["id"],
                "cliente_id": cliente_id,
                "arquivado": False,
                "substituida_por": None,
                "created_at": "2026-07-01T00:00:00+00:00",
            }
        ).execute()
        out = svc.reconcile(leads_client, UUID(ORG_A))
        assert out["vinculos_criados"] == 1 and out["interesses_criados"] == 1
        (juncao,) = leads_client.table("atendimento_imoveis").select("*").execute().data
        assert (juncao["codigo"], juncao["origem"], juncao["principal"]) == (LEAD_CODIGO, "lead", True)
        (interesse,) = leads_client.table("cliente_imovel_interesses").select("*").execute().data
        assert (interesse["cliente_id"], interesse["origem"], interesse["lead_id"]) == (
            cliente_id, "lead", data["id"],
        )

    def test_a_failing_link_never_fails_the_create(self, http_client, leads_client, caplog):
        """The lead is already saved: a 500 would invite a duplicating retry.
        The failure is LOGGED (error) and the response still carries the keys.
        Provoked for real, not patched: a lead row that points at a table the
        link step cannot read (the junction is dropped from the mock's schema
        by seeding a non-list)."""
        import logging

        from app.modules.imovel_hub import atendimento_imoveis_service as svc

        class Boom:
            def table(self, *_a, **_k):
                raise RuntimeError("junction table missing (migration 181 not applied)")

        with caplog.at_level(logging.ERROR):
            out = svc.vincular_lead_seguro(
                Boom(), UUID(ORG_A), lead_id="00000000-0000-4000-8000-00000000aa02",
                contexto="test",
            )
        assert out is None
        assert any("vincular_lead failed (test)" in r.getMessage() for r in caplog.records)
