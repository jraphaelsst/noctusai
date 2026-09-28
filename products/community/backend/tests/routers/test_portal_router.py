"""Tests for `portal_router` — contract §Member portal, slice BE-A
(`GET /api/portal/minha-conta` only).
"""
from tests.conftest import ORG_UUID, TEST_USER_ID, seed_community_role

PLANO_1 = "11111111-1111-1111-1111-111111111111"
PLANO_2 = "44444444-4444-4444-4444-444444444444"
MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ASSINATURA_1 = "55555555-5555-5555-5555-555555555555"
ASSINATURA_2 = "66666666-6666-6666-6666-666666666666"


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana", "email": "ana@x.com",
        "telefone": "+5511999999999", "status": "ativo", "plano_id": PLANO_1,
        "origem": "cadastro", "tags": [], "user_id": TEST_USER_ID, "observacoes": None,
        "entrou_em": "2026-09-01T00:00:00+00:00",
        "created_at": "2026-09-01T00:00:00+00:00", "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _plano_row(**over) -> dict:
    base = {
        "id": PLANO_1, "org_id": ORG_UUID, "nome": "Ouvinte", "descricao": "desc",
        "preco_centavos": 700, "ciclo": "mensal",
        "entitlements": {"grupoterapia": "ouvir"}, "ativo": True, "ordem": 1,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _seed_membro(client, **over):
    seed_community_role(client, org_role="membro")
    client.mock_supabase.set_table_data("membros", [_membro_row(**over)])


class TestPortalAuthBoundary:
    def test_no_auth_401(self, client):
        assert client.raw().get("/api/portal/minha-conta").status_code == 401

    def test_staff_403(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/portal/minha-conta")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Área exclusiva para membros."

    def test_membro_without_linked_row_403(self, client):
        seed_community_role(client, org_role="membro")
        resp = client.get("/api/portal/minha-conta")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Cadastro de membro não encontrado."


class TestMinhaConta:
    def test_shape_with_plano_and_no_assinatura(self, client):
        _seed_membro(client)
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        resp = client.get("/api/portal/minha-conta")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"membro", "plano", "assinatura", "pagamentos", "planos_disponiveis"}
        assert body["membro"]["id"] == MEMBRO_1
        assert body["plano"]["nome"] == "Ouvinte"
        assert body["plano"]["nivel_grupoterapia"] == "ouvir"
        assert body["assinatura"] is None
        assert body["pagamentos"] == []

    def test_no_plano_is_null(self, client):
        _seed_membro(client, plano_id=None)
        resp = client.get("/api/portal/minha-conta")
        assert resp.status_code == 200
        assert resp.json()["plano"] is None

    def test_assinatura_is_the_most_recent_non_expirada(self, client):
        _seed_membro(client)
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        client.mock_supabase.set_table_data("assinaturas", [
            {"id": ASSINATURA_1, "org_id": ORG_UUID, "membro_id": MEMBRO_1,
             "plano_id": PLANO_1, "gateway": "asaas", "estado": "expirada",
             "metodo": "pix", "ciclo": "mensal",
             "created_at": "2026-08-01T00:00:00+00:00", "updated_at": "2026-08-01T00:00:00+00:00"},
            {"id": ASSINATURA_2, "org_id": ORG_UUID, "membro_id": MEMBRO_1,
             "plano_id": PLANO_1, "gateway": "asaas", "estado": "ativa",
             "metodo": "pix", "proxima_cobranca": "2026-10-01", "pago_ate": "2026-10-01T00:00:00+00:00",
             "ciclo": "mensal",
             "created_at": "2026-09-01T00:00:00+00:00", "updated_at": "2026-09-01T00:00:00+00:00"},
        ])
        resp = client.get("/api/portal/minha-conta")
        assert resp.status_code == 200
        assinatura = resp.json()["assinatura"]
        assert assinatura["id"] == ASSINATURA_2
        assert assinatura["estado"] == "ativa"
        assert assinatura["proxima_cobranca"] == "2026-10-01"

    def test_pagamentos_last_12_newest_first(self, client):
        _seed_membro(client)
        rows = [
            {"id": f"99999999-0000-0000-0000-{i:012d}", "org_id": ORG_UUID, "membro_id": MEMBRO_1,
             "assinatura_id": None, "gateway": "asaas", "cobranca_externa_id": f"c{i}",
             "valor_centavos": 700, "metodo": "pix", "estado": "pago",
             "vencimento": None, "pago_em": None, "url_fatura": None,
             "created_at": f"2026-01-{i:02d}T00:00:00+00:00"}
            for i in range(1, 14)
        ]
        client.mock_supabase.set_table_data("pagamentos", rows)
        resp = client.get("/api/portal/minha-conta")
        assert resp.status_code == 200
        pagamentos = resp.json()["pagamentos"]
        assert len(pagamentos) == 12
        assert pagamentos[0]["id"] == "99999999-0000-0000-0000-000000000013"  # newest first

    def test_planos_disponiveis_only_ativos_ordered(self, client):
        _seed_membro(client)
        client.mock_supabase.set_table_data("planos", [
            _plano_row(id=PLANO_1, nome="Ouvinte", ordem=1),
            _plano_row(id=PLANO_2, nome="Premium", ordem=2,
                       entitlements={"grupoterapia": "falar"}),
            _plano_row(id="77777777-7777-7777-7777-777777777777", nome="Descontinuado",
                       ativo=False, ordem=0),
        ])
        resp = client.get("/api/portal/minha-conta")
        assert resp.status_code == 200
        disponiveis = resp.json()["planos_disponiveis"]
        assert [p["nome"] for p in disponiveis] == ["Ouvinte", "Premium"]
