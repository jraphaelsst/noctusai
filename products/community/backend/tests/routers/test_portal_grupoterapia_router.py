"""Tests for `portal_grupoterapia_router` — contract §Grupoterapia, member
side. Exercises the security boundary end-to-end over HTTP: `nenhum` never
receives a `link_sala`, `ouvir` gets one but 403s on reserve, `falar`
reserves, `lotada`/`indisponivel` map to 409.
"""
from tests.conftest import ORG_UUID, TEST_USER_ID, seed_community_role

SESSAO_1 = "22222222-2222-2222-2222-222222222222"
MEMBRO_1 = "44444444-4444-4444-4444-444444444444"
PLANO_OUVINTE = "77777777-7777-7777-7777-777777777777"
PLANO_PREMIUM = "88888888-8888-8888-8888-888888888888"

_FUTURE = "2026-10-05T19:00:00+00:00"


def _sessao_row(**over) -> dict:
    base = {
        "id": SESSAO_1,
        "org_id": ORG_UUID,
        "titulo": "Roda de acolhimento",
        "descricao": None,
        "inicio": _FUTURE,
        "duracao_minutos": 90,
        "link_sala": "https://meet.example/roda",
        "vagas_fala": 8,
        "status": "agendada",
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _plano_row(plano_id, nivel) -> dict:
    return {
        "id": plano_id, "org_id": ORG_UUID, "nome": "Plano",
        "preco_centavos": 700, "ciclo": "mensal", "ativo": True, "ordem": 1,
        "entitlements": {"grupoterapia": nivel},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _seed_membro(client, *, plano_id=None) -> None:
    """A `membro`-role caller with a linked `community.membros` row."""
    seed_community_role(client, org_role="membro")
    client.mock_supabase.set_table_data("membros", [{
        "id": MEMBRO_1, "org_id": ORG_UUID, "user_id": TEST_USER_ID,
        "nome": "Ana", "email": "ana@x.com", "status": "ativo", "plano_id": plano_id,
    }])


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/portal/grupoterapia").status_code == 401

    def test_reservar_without_auth_401(self, client):
        resp = client.raw().post(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 401

    def test_cancelar_without_auth_401(self, client):
        resp = client.raw().delete(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 401

    def test_staff_role_403(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/portal/grupoterapia")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Área exclusiva para membros."

    def test_membro_role_without_membros_row_403(self, client):
        seed_community_role(client, org_role="membro")
        resp = client.get("/api/portal/grupoterapia")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Cadastro de membro não encontrado."


class TestNivelNenhum:
    def test_never_exposes_link_sala(self, client):
        _seed_membro(client, plano_id=None)
        client.mock_supabase.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        resp = client.get("/api/portal/grupoterapia")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nivel"] == "nenhum"
        assert len(body["items"]) >= 1
        for item in body["items"]:
            assert item["link_sala"] is None
            assert item["acesso"] == "bloqueado"

    def test_cannot_reserve(self, client):
        _seed_membro(client, plano_id=None)
        resp = client.post(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Seu plano não inclui a vez de fala."


class TestNivelOuvir:
    def test_gets_link_sala(self, client):
        _seed_membro(client, plano_id=PLANO_OUVINTE)
        client.mock_supabase.set_table_data("planos", [_plano_row(PLANO_OUVINTE, "ouvir")])
        client.mock_supabase.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        resp = client.get("/api/portal/grupoterapia")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nivel"] == "ouvir"
        assert body["items"][0]["link_sala"] == "https://meet.example/roda"
        assert body["items"][0]["acesso"] == "ouvir"

    def test_reservar_403(self, client):
        _seed_membro(client, plano_id=PLANO_OUVINTE)
        client.mock_supabase.set_table_data("planos", [_plano_row(PLANO_OUVINTE, "ouvir")])
        resp = client.post(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Seu plano não inclui a vez de fala."


class TestNivelFalar:
    def test_reservar_confirmada_200(self, client):
        _seed_membro(client, plano_id=PLANO_PREMIUM)
        client.mock_supabase.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        client.mock_supabase.set_rpc_data("reservar_vaga_fala", "confirmada")
        resp = client.post(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 200
        assert resp.json() == {"status": "confirmada"}
        eventos = client.mock_supabase.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "grupoterapia"

    def test_reservar_lotada_409(self, client):
        _seed_membro(client, plano_id=PLANO_PREMIUM)
        client.mock_supabase.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        client.mock_supabase.set_rpc_data("reservar_vaga_fala", "lotada")
        resp = client.post(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Não há mais vagas de fala nesta sessão."

    def test_reservar_indisponivel_409(self, client):
        _seed_membro(client, plano_id=PLANO_PREMIUM)
        client.mock_supabase.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        client.mock_supabase.set_rpc_data("reservar_vaga_fala", "indisponivel")
        resp = client.post(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Sessão indisponível para reservas."

    def test_cancelar_204(self, client):
        _seed_membro(client, plano_id=PLANO_PREMIUM)
        client.mock_supabase.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        client.mock_supabase.set_table_data("grupoterapia_reservas", [{
            "id": "r1", "org_id": ORG_UUID, "sessao_id": SESSAO_1,
            "membro_id": MEMBRO_1, "status": "confirmada",
        }])
        resp = client.delete(f"/api/portal/grupoterapia/{SESSAO_1}/reserva")
        assert resp.status_code == 204
        row = client.mock_supabase.table("grupoterapia_reservas").select("*").execute().data[0]
        assert row["status"] == "cancelada"
