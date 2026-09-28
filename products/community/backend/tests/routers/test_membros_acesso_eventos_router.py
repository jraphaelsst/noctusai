"""Tests for `POST /api/membros/{id}/acesso` and `/eventos`, plus the
`/status` + `PATCH` eventing additions — contract §Identity, slice BE-A.
"""
from types import SimpleNamespace

from tests.conftest import ORG_UUID, TEST_USER_ID, seed_community_role

MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PLANO_1 = "11111111-1111-1111-1111-111111111111"
UNKNOWN_ID = "99999999-9999-9999-9999-999999999999"
NEW_USER_ID = "new-user-1"


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana", "email": "ana@x.com",
        "telefone": None, "status": "ativo", "plano_id": PLANO_1, "origem": "checkout",
        "tags": [], "user_id": None, "observacoes": None,
        "entrou_em": "2026-09-16T20:00:00+00:00",
        "created_at": "2026-09-16T20:00:00+00:00", "updated_at": "2026-09-16T20:00:00+00:00",
    }
    base.update(over)
    return base


def _seed_admin(client, *, membro_row=None, extra_noctus_users=None):
    rows = [{
        "id": TEST_USER_ID, "org_id": "test-org-123", "role": "user", "org_role": "admin",
    }]
    if extra_noctus_users:
        rows.extend(extra_noctus_users)
    client.mock_supabase.set_table_data("noctus_users", rows)
    client.mock_supabase.set_table_data("membros", [membro_row or _membro_row()])
    client.mock_supabase.auth.admin.list_users.return_value = []
    client.mock_supabase.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=NEW_USER_ID)
    )


class TestCriarAcessoAuthBoundary:
    def test_no_auth_401(self, client):
        assert client.raw().post(f"/api/membros/{MEMBRO_1}/acesso").status_code == 401

    def test_moderador_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/membros/{MEMBRO_1}/acesso")
        assert resp.status_code == 403
        assert resp.json()["detail"].startswith("Apenas administradores podem")


class TestCriarAcesso:
    def test_happy_path_201(self, client):
        _seed_admin(client)
        resp = client.post(f"/api/membros/{MEMBRO_1}/acesso")
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "ana@x.com"
        assert len(body["senha_temporaria"]) == 12

        row = client.mock_supabase.table("membros").select("*").execute().data[0]
        assert row["user_id"] == NEW_USER_ID

        eventos = client.mock_supabase.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "acesso"

    def test_already_has_access_409(self, client):
        _seed_admin(client, membro_row=_membro_row(user_id="existing-user"))
        resp = client.post(f"/api/membros/{MEMBRO_1}/acesso")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Este membro já tem acesso."
        client.mock_supabase.auth.admin.create_user.assert_not_called()

    def test_existing_identity_is_linked_and_409(self, client):
        _seed_admin(client, extra_noctus_users=[
            {"id": "existing-user", "email": "ana@x.com", "nome": "Ana", "org_id": None},
        ])
        resp = client.post(f"/api/membros/{MEMBRO_1}/acesso")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Este e-mail já tinha login; o acesso foi vinculado."
        client.mock_supabase.auth.admin.create_user.assert_not_called()
        row = client.mock_supabase.table("membros").select("*").execute().data[0]
        assert row["user_id"] == "existing-user"

    def test_404(self, client):
        _seed_admin(client)
        resp = client.post(f"/api/membros/{UNKNOWN_ID}/acesso")
        assert resp.status_code == 404


class TestEventosAuthBoundary:
    def test_list_no_auth_401(self, client):
        assert client.raw().get(f"/api/membros/{MEMBRO_1}/eventos").status_code == 401

    def test_create_no_auth_401(self, client):
        resp = client.raw().post(
            f"/api/membros/{MEMBRO_1}/eventos", json={"tipo": "nota", "descricao": "x"},
        )
        assert resp.status_code == 401


class TestEventos:
    def test_moderador_can_create_nota(self, client):
        seed_community_role(client, org_role="moderador")
        client.mock_supabase.set_table_data("membros", [_membro_row()])
        resp = client.post(
            f"/api/membros/{MEMBRO_1}/eventos", json={"tipo": "nota", "descricao": "Ligou hoje"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["tipo"] == "nota"
        assert body["descricao"] == "Ligou hoje"

    def test_invalid_tipo_422(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row()])
        resp = client.post(
            f"/api/membros/{MEMBRO_1}/eventos", json={"tipo": "status", "descricao": "x"},
        )
        assert resp.status_code == 422

    def test_create_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post(
            f"/api/membros/{UNKNOWN_ID}/eventos", json={"tipo": "contato", "descricao": "x"},
        )
        assert resp.status_code == 404

    def test_list_returns_newest_first_with_autor_nome(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row()])
        client.mock_supabase.set_table_data("noctus_users", [
            {"id": TEST_USER_ID, "org_id": "test-org-123", "role": "user",
             "org_role": "admin", "nome": "Equipe"},
        ])
        autor_uuid = "88888888-8888-8888-8888-888888888888"
        evento_1 = "eeeeeeee-1111-1111-1111-111111111111"
        evento_2 = "eeeeeeee-2222-2222-2222-222222222222"
        client.mock_supabase.set_table_data("membro_eventos", [
            {"id": evento_1, "org_id": ORG_UUID, "membro_id": MEMBRO_1, "tipo": "nota",
             "descricao": "Primeiro contato", "dados": {}, "autor_id": autor_uuid,
             "created_at": "2026-09-01T00:00:00+00:00"},
            {"id": evento_2, "org_id": ORG_UUID, "membro_id": MEMBRO_1, "tipo": "contato",
             "descricao": "Segundo contato", "dados": {}, "autor_id": autor_uuid,
             "created_at": "2026-09-05T00:00:00+00:00"},
        ])
        client.mock_supabase.table("noctus_users").insert({
            "id": autor_uuid, "email": "equipe@x.com", "nome": "Equipe",
        }).execute()
        resp = client.get(f"/api/membros/{MEMBRO_1}/eventos")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert [i["id"] for i in body["items"]] == [evento_2, evento_1]
        assert body["items"][0]["autor_nome"] == "Equipe"


class TestStatusEventing:
    def test_status_change_persists_motivo_as_evento(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(status="ativo")])
        resp = client.post(
            f"/api/membros/{MEMBRO_1}/status",
            json={"status": "pausado", "motivo": "Pediu pausa"},
        )
        assert resp.status_code == 200
        eventos = client.mock_supabase.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "status"
        assert eventos[0]["dados"]["motivo"] == "Pediu pausa"
        assert eventos[0]["dados"]["de"] == "ativo"
        assert eventos[0]["dados"]["para"] == "pausado"

    def test_idempotent_same_status_writes_no_evento(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(status="ativo")])
        resp = client.post(f"/api/membros/{MEMBRO_1}/status", json={"status": "ativo"})
        assert resp.status_code == 200
        assert client.mock_supabase.table("membro_eventos").select("*").execute().data == []


class TestPlanoEventing:
    def test_plano_change_writes_evento(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(plano_id=PLANO_1)])
        novo_plano = "44444444-4444-4444-4444-444444444444"
        resp = client.patch(f"/api/membros/{MEMBRO_1}", json={"plano_id": novo_plano})
        assert resp.status_code == 200
        eventos = client.mock_supabase.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "plano"
        assert eventos[0]["dados"]["de"] == PLANO_1
        assert eventos[0]["dados"]["para"] == novo_plano

    def test_non_plano_update_writes_no_evento(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(plano_id=PLANO_1)])
        resp = client.patch(f"/api/membros/{MEMBRO_1}", json={"observacoes": "VIP"})
        assert resp.status_code == 200
        assert client.mock_supabase.table("membro_eventos").select("*").execute().data == []
