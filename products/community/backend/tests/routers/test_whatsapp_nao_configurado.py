"""WhatsApp NOT configured (no saved connection, no `community_waha_base_url`,
`whatsapp_allow_fake` off) — the honest-state contract (2026-10-01).

Prod had no WAHA connection and silently ran on `FakeWahaClient`: the
session read "Aguardando pareamento" and a broadcast flipped to "Enviada"
with nothing sent. Now `resolve_community_waha_client` returns ``None``;
these tests drive that ``None`` through the real dependency chain by
overriding `get_community_waha_client_optional` (the product's own DI seam
— `get_community_waha_client` depends on it, so the 503 guard itself runs).
"""
from app.dependencies import (
    WHATSAPP_NAO_CONECTADO_CODE,
    WHATSAPP_NAO_CONECTADO_DETAIL,
    get_community_waha_client_optional,
)
from tests.conftest import ORG_UUID, seed_community_role

GRUPO_1 = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"
TRANSMISSAO_1 = "22222222-2222-2222-2222-222222222222"
LOTE_1 = "33333333-3333-3333-3333-333333333333"


def _sem_whatsapp(client) -> None:
    client.raw().app.dependency_overrides[get_community_waha_client_optional] = lambda: None


def _assert_recusa(resp) -> None:
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"] == WHATSAPP_NAO_CONECTADO_DETAIL
    assert body["code"] == WHATSAPP_NAO_CONECTADO_CODE


class TestSessao:
    def test_sessao_reports_nao_configurado_200(self, client):
        _sem_whatsapp(client)
        resp = client.get("/api/whatsapp/sessao")
        assert resp.status_code == 200
        assert resp.json() == {"estado": "NAO_CONFIGURADO", "sessao": ""}

    def test_sessao_without_auth_401(self, client):
        _sem_whatsapp(client)
        assert client.raw().get("/api/whatsapp/sessao").status_code == 401


class TestRecusa503:
    def test_enviar_transmissao_503_and_never_enviada(self, client):
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        client.mock_supabase.set_table_data("grupos", [{
            "id": GRUPO_1, "org_id": ORG_UUID, "chat_id": CHAT_ID, "nome": "G", "ativo": True,
        }])
        client.mock_supabase.set_table_data("transmissoes", [{
            "id": TRANSMISSAO_1, "org_id": ORG_UUID, "titulo": "Aviso", "corpo": "Olá",
            "tipo": "anuncio", "estado": "rascunho", "agendada_para": None, "enviada_em": None,
        }])
        client.mock_supabase.set_table_data("transmissao_destinos", [{
            "id": "d1", "org_id": ORG_UUID, "transmissao_id": TRANSMISSAO_1,
            "grupo_id": GRUPO_1, "estado": "pendente",
        }])

        _assert_recusa(client.post(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}/enviar"))

        row = client.mock_supabase.table("transmissoes").select("*").eq(
            "id", TRANSMISSAO_1,
        ).execute().data[0]
        assert row["estado"] == "rascunho"
        assert row["enviada_em"] is None

    def test_criar_grupo_novo_503(self, client):
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        _assert_recusa(client.post("/api/whatsapp/grupos", json={"criar": True, "nome": "Novo"}))
        assert client.mock_supabase.table("grupos").select("*").execute().data == []

    def test_registrar_chat_id_existente_sem_whatsapp_201(self, client):
        """Registering an EXISTING chat_id is a pure DB write — allowed."""
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        resp = client.post("/api/whatsapp/grupos", json={"chat_id": CHAT_ID})
        assert resp.status_code == 201
        assert resp.json()["nome"] == CHAT_ID

    def test_sincronizar_roster_503(self, client):
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        _assert_recusa(client.post(f"/api/whatsapp/grupos/{GRUPO_1}/sincronizar-roster"))

    def test_convite_503(self, client):
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        _assert_recusa(client.get(f"/api/whatsapp/grupos/{GRUPO_1}/convite"))

    def test_revogar_convite_503(self, client):
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        _assert_recusa(client.post(f"/api/whatsapp/grupos/{GRUPO_1}/convite/revogar"))

    def test_aplicar_lote_503(self, client):
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        _assert_recusa(client.post(f"/api/whatsapp/lotes/{LOTE_1}/aplicar"))

    def test_convites_pendentes_503(self, client):
        seed_community_role(client, org_role="admin")
        _sem_whatsapp(client)
        _assert_recusa(client.get(f"/api/whatsapp/lotes/{LOTE_1}/convites-pendentes"))

    def test_enviar_without_auth_still_401(self, client):
        _sem_whatsapp(client)
        resp = client.raw().post(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}/enviar")
        assert resp.status_code == 401
