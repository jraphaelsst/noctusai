"""Tests for `eu_router` — contract §Identity, `GET /api/eu`, slice BE-A.

Base auth: reachable by staff AND membro alike (never the staff gate).
"""
from tests.conftest import ORG_UUID, TEST_USER_ID, seed_community_role

PLANO_1 = "11111111-1111-1111-1111-111111111111"
MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _plano_row(**over) -> dict:
    base = {
        "id": PLANO_1, "org_id": ORG_UUID, "nome": "Ouvinte", "descricao": None,
        "preco_centavos": 700, "ciclo": "mensal",
        "entitlements": {"feed": False, "forum": False, "chat": False, "eventos": False,
                         "conteudo_ids": [], "grupos_whatsapp": [], "conteudo_todos": False,
                         "grupoterapia": "ouvir"},
        "ativo": True, "ordem": 1,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana", "email": "ana@x.com",
        "telefone": None, "status": "ativo", "plano_id": None, "origem": "cadastro",
        "tags": [], "user_id": TEST_USER_ID, "observacoes": None,
        "entrou_em": "2026-09-16T20:00:00+00:00",
        "created_at": "2026-09-16T20:00:00+00:00", "updated_at": "2026-09-16T20:00:00+00:00",
    }
    base.update(over)
    return base


class TestEuAuthBoundary:
    def test_no_auth_401(self, client):
        assert client.raw().get("/api/eu").status_code == 401


class TestEuStaff:
    def test_admin_papel_and_null_membro(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/eu")
        assert resp.status_code == 200
        body = resp.json()
        assert body["papel"] == "admin"
        assert body["membro"] is None
        assert body["email"] == "test@example.com"

    def test_moderador_papel(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.get("/api/eu")
        assert resp.status_code == 200
        assert resp.json()["papel"] == "moderador"

    def test_nome_falls_back_to_platform_admin_when_no_metadata(self, client):
        """The base `client` fixture's `MockUser` carries no `nome` in
        `user_metadata` — the email-local-part fallback must still answer
        with a non-empty string, never 500."""
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/eu")
        assert resp.status_code == 200
        assert resp.json()["nome"] == "test"


class TestEuMembro:
    def test_membro_with_plano_returns_nivel_grupoterapia(self, client):
        seed_community_role(client, org_role="membro")
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        client.mock_supabase.set_table_data(
            "membros", [_membro_row(plano_id=PLANO_1)],
        )
        resp = client.get("/api/eu")
        assert resp.status_code == 200
        body = resp.json()
        assert body["papel"] == "membro"
        assert body["membro"]["id"] == MEMBRO_1
        assert body["membro"]["plano_nome"] == "Ouvinte"
        assert body["membro"]["nivel_grupoterapia"] == "ouvir"

    def test_membro_without_plano_is_nenhum(self, client):
        seed_community_role(client, org_role="membro")
        client.mock_supabase.set_table_data("membros", [_membro_row(plano_id=None)])
        resp = client.get("/api/eu")
        assert resp.status_code == 200
        body = resp.json()
        assert body["membro"]["plano_id"] is None
        assert body["membro"]["nivel_grupoterapia"] == "nenhum"

    def test_membro_without_linked_row_is_null_not_500(self, client):
        """A `membro` org_role with no `community.membros` row yet — this
        endpoint degrades gracefully (unlike `get_membro_context`, which
        403s); `GET /api/eu` uses the base auth, not the portal gate."""
        seed_community_role(client, org_role="membro")
        resp = client.get("/api/eu")
        assert resp.status_code == 200
        body = resp.json()
        assert body["papel"] == "membro"
        assert body["membro"] is None
