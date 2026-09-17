"""Tests for the flags router — contract §Ingest + flags, item 20.
Both `admin` + `moderador` read AND resolve — "moderation IS the
moderador's job" (contract)."""
from tests.conftest import ORG_UUID, seed_community_role

FLAG_1 = "11111111-1111-1111-1111-111111111111"
MENSAGEM_1 = "22222222-2222-2222-2222-222222222222"


def _flag_row(**over) -> dict:
    base = {
        "id": FLAG_1, "org_id": ORG_UUID, "mensagem_id": MENSAGEM_1,
        "categoria": "spam", "severidade": "media", "justificativa": "propaganda",
        "modelo": "gpt-4o-mini", "prompt_versao": "v1", "estado": "aberta",
        "resolvido_por": None, "resolvido_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/whatsapp/flags").status_code == 401

    def test_resolver_without_auth_401(self, client):
        resp = client.raw().post(
            f"/api/whatsapp/flags/{FLAG_1}/resolver", json={"estado": "resolvida"},
        )
        assert resp.status_code == 401


class TestRoleGate:
    """Both roles read AND resolve — moderation is the moderador's job."""

    def test_moderador_can_list(self, client):
        seed_community_role(client, org_role="moderador")
        client.mock_supabase.set_table_data("mensagem_flags", [_flag_row()])
        assert client.get("/api/whatsapp/flags").status_code == 200

    def test_moderador_can_resolve(self, client):
        seed_community_role(client, org_role="moderador")
        client.mock_supabase.set_table_data("mensagem_flags", [_flag_row()])
        resp = client.post(
            f"/api/whatsapp/flags/{FLAG_1}/resolver", json={"estado": "resolvida"},
        )
        assert resp.status_code == 200
        assert resp.json()["estado"] == "resolvida"


class TestCrud:
    def test_list_filters_by_estado_and_severidade(self, client):
        client.mock_supabase.set_table_data("mensagem_flags", [
            _flag_row(id=FLAG_1, estado="aberta", severidade="alta"),
            _flag_row(id="33333333-3333-3333-3333-333333333333", estado="resolvida", severidade="baixa"),
        ])
        resp = client.get("/api/whatsapp/flags", params={"estado": "aberta"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_resolver_missing_404(self, client):
        resp = client.post(
            f"/api/whatsapp/flags/{FLAG_1}/resolver", json={"estado": "descartada"},
        )
        assert resp.status_code == 404

    def test_resolver_invalid_estado_422(self, client):
        client.mock_supabase.set_table_data("mensagem_flags", [_flag_row()])
        resp = client.post(
            f"/api/whatsapp/flags/{FLAG_1}/resolver", json={"estado": "invalido"},
        )
        assert resp.status_code == 422

    def test_resolver_sets_resolvido_por_and_em(self, client):
        client.mock_supabase.set_table_data("mensagem_flags", [_flag_row()])
        resp = client.post(
            f"/api/whatsapp/flags/{FLAG_1}/resolver",
            json={"estado": "descartada", "nota": "falso positivo"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["estado"] == "descartada"
        assert body["resolvido_por"] is not None
        assert body["resolvido_em"] is not None
