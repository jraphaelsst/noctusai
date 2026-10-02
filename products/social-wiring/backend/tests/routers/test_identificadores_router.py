"""`GET /api/identificadores/nao-conformes` — the operators' queue over
`vw_identificadores_nao_conformes` (migration 187).

Pins: strict `== 401`; org scoping (the service client bypasses RLS, so the
`org_id` filter IS the boundary); a pt-BR reason per row; the correction target
(existing edit endpoints) — and that a certidão consulta is never edited in
place; `nao_cabe` by default, paging with a real total.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

from app.dependencies import coerce_org_uuid
from app.services import identificadores_revisao as revisao

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))
OUTRA_ORG = str(uuid4())
URL = "/api/identificadores/nao-conformes"
CLI = str(uuid4())
CLI2 = str(uuid4())
CONSULTA = str(uuid4())


def _linha(tabela, linha_id, campo, valor, situacao="nao_cabe", org=ORG_ID, canonico=None):
    return {"tabela": tabela, "org_id": org, "linha_id": linha_id, "campo": campo,
            "valor": valor, "canonico": canonico, "situacao": situacao}


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_RAW, org_role="owner"))
    )
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.dependencies import get_scoped_admin_client
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        scoped = get_scoped_admin_client("social_wiring")
        scoped.set_table_data(revisao.VIEW, [])
        scoped.set_table_data("clientes", [
            {"id": CLI, "org_id": ORG_ID, "nome": "Maria", "nome_oficial": "Maria da Silva", "rg_orgao_expedidor": "SSP/SP"},
            {"id": CLI2, "org_id": ORG_ID, "nome": "Joao", "nome_oficial": None, "rg_orgao_expedidor": None},
        ])
        scoped.set_table_data("certidao_consultas", [
            {"id": CONSULTA, "org_id": ORG_ID, "nome": "Maria da Silva", "tipo_documento": "cpf",
             "cliente_id": CLI, "empresa_id": None},
        ])
        tc = TestClient(app, raise_server_exceptions=True)
        tc.scoped = scoped
        yield tc


def _get(client, qs=""):
    return client.get(URL + qs, headers={"Authorization": "Bearer test-token"})


class TestAuth:
    def test_without_a_token_is_401(self, client):
        assert client.get(URL).status_code == 401


class TestListagem:
    def test_lista_com_motivo_pt_br_entidade_e_alvo_de_edicao(self, client):
        client.scoped.set_table_data(revisao.VIEW, [
            _linha("clientes", CLI, "cpf", "123.456.789-00"),  # DV invalid
            _linha("imovel_dados", "ONE9441", "numero_matricula", "12.3"),
        ])
        body = _get(client).json()
        assert body["total"] == 2
        por_campo = {i["campo"]: i for i in body["items"]}
        cpf = por_campo["cpf"]
        assert cpf["rotulo_campo"] == "CPF"
        assert cpf["entidade_nome"] == "Maria da Silva"
        assert cpf["valor"] == "123.456.789-00"
        assert "dígito verificador" in cpf["motivo"]
        assert cpf["link"] == {"tipo": "cliente", "id": CLI}
        assert cpf["edicao"] == {"tipo": "cliente", "id": CLI, "campo": "cpf"}
        mat = por_campo["numero_matricula"]
        assert mat["entidade_nome"] == "Imóvel ONE9441"
        assert mat["link"] == {"tipo": "imovel", "id": "ONE9441"}
        assert mat["edicao"]["tipo"] == "imovel"
        assert mat["motivo"]  # never blank

    def test_so_enxerga_a_propria_org(self, client):
        client.scoped.set_table_data(revisao.VIEW, [
            _linha("clientes", CLI, "cpf", "111"),
            _linha("clientes", CLI2, "cpf", "222", org=OUTRA_ORG),
        ])
        body = _get(client).json()
        assert body["total"] == 1
        assert [i["linha_id"] for i in body["items"]] == [CLI]

    def test_padrao_e_nao_cabe_e_canonizavel_sob_pedido(self, client):
        client.scoped.set_table_data(revisao.VIEW, [
            _linha("clientes", CLI, "cpf", "111"),
            _linha("clientes", CLI2, "cpf", "12345678909", situacao="canonizavel", canonico="123.456.789-09"),
        ])
        assert [i["situacao"] for i in _get(client).json()["items"]] == ["nao_cabe"]
        item = _get(client, "?situacao=canonizavel").json()["items"][0]
        assert item["situacao"] == "canonizavel" and "outra grafia" in item["motivo"]

    def test_consulta_de_certidao_nao_e_editada_no_lugar(self, client):
        client.scoped.set_table_data(revisao.VIEW, [
            _linha("certidao_consultas", CONSULTA, "documento", "123"),
        ])
        item = _get(client).json()["items"][0]
        assert item["edicao"] is None
        assert item["link"] == {"tipo": "cliente", "id": CLI}

    def test_paginacao_devolve_total_real(self, client):
        client.scoped.set_table_data(revisao.VIEW, [
            _linha("clientes", CLI, f"campo{i}", "x") for i in range(7)
        ])
        body = _get(client, "?page=2&page_size=3").json()
        assert body["total"] == 7 and body["page"] == 2 and len(body["items"]) == 3

    def test_situacao_invalida_e_422(self, client):
        assert _get(client, "?situacao=qualquer").status_code == 422


class TestMotivo:
    def test_cpf_no_campo_do_rg_diz_que_e_outro_tipo(self):
        m = revisao.motivo_pt("rg", "123.456.789-09", situacao="nao_cabe")
        assert "CPF" in m and "campo errado" in m

    def test_nunca_vazio_nem_codigo_cru(self):
        for tipo, valor in (("cep", "12"), ("matricula_imovel", "abc"), ("rg", "???"), (None, "x")):
            m = revisao.motivo_pt(tipo, valor, situacao="nao_cabe")
            assert m and "_" not in m
