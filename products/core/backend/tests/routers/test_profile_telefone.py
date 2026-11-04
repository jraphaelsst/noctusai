"""PATCH /api/auth/profile -- telefone (WhatsApp, E.164, single source of truth).

Owner decision 2026-11-03: the platform user's number lives in core
(public.noctus_users.telefone); other products store a user id and resolve it.
"""


def _user_row(**extra):
    return {
        "id": "test-user-123", "email": "test@example.com", "nome": "Test User",
        "org_id": "org-1", "role": "user", **extra,
    }


class TestProfileTelefone:
    def test_formatted_br_number_is_stored_as_e164(self, client):
        client.mock_supabase.set_table_data("noctus_users", _user_row())
        resp = client.patch("/api/auth/profile", json={"telefone": "(11) 99457-3387"})
        assert resp.status_code == 200
        assert resp.json()["data"]["telefone"] == "+5511994573387"

    def test_empty_string_clears_the_number(self, client):
        client.mock_supabase.set_table_data(
            "noctus_users", _user_row(telefone="+5511994573387")
        )
        resp = client.patch("/api/auth/profile", json={"telefone": "  "})
        assert resp.status_code == 200
        assert resp.json()["data"]["telefone"] is None

    def test_invalid_number_is_422_in_portuguese(self, client):
        client.mock_supabase.set_table_data("noctus_users", _user_row())
        resp = client.patch("/api/auth/profile", json={"telefone": "não informado"})
        assert resp.status_code == 422
        assert "Telefone inválido" in resp.text  # error envelope shape is the platform's, not FastAPI's bare detail

    def test_get_me_returns_telefone(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", _user_row(telefone="+5511994573387"))
        mock_sb.set_table_data("organizations", {"id": "org-1", "nome": "Test Corp"})
        mock_sb.set_table_data("licenses", [])
        mock_sb.set_table_data("products", [])
        assert client.get("/api/auth/me").json()["user"]["telefone"] == "+5511994573387"

    def test_profile_unauthenticated(self, unauth_client):
        resp = unauth_client.patch("/api/auth/profile", json={"telefone": "+5511994573387"})
        assert resp.status_code == 401
