"""Tests for `cadastro_router` — contract §Identity, `POST /api/cadastro`,
slice BE-A. PUBLIC, no auth header needed (`client.raw()`).
"""
from types import SimpleNamespace

from tests.conftest import ORG_UUID, seed_public_license

PLANO_GRATUITO = "22222222-2222-2222-2222-222222222222"
PLANO_PAGO = "33333333-3333-3333-3333-333333333333"
NEW_USER_ID = "new-user-1"


def _plano_gratuito_row(**over) -> dict:
    base = {
        "id": PLANO_GRATUITO, "org_id": ORG_UUID, "nome": "Gratuito", "descricao": None,
        "preco_centavos": 0, "ciclo": "mensal",
        "entitlements": {"grupoterapia": "nenhum"}, "ativo": True, "ordem": 0,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _payload(**over) -> dict:
    base = {
        "nome": "Ana", "email": "ana@x.com", "telefone": "+5511999999999",
        "senha": "senha1234", "turnstile_token": "tok", "aceite_termos": True,
    }
    base.update(over)
    return base


def _seed_base(client, *, planos=None):
    seed_public_license(client)
    client.mock_supabase.set_table_data("planos", planos if planos is not None else [_plano_gratuito_row()])
    # `find_auth_user_id_by_email`'s fallback lookup — no matching identity
    # by default. `create_user` mints a fresh identity.
    client.mock_supabase.auth.admin.list_users.return_value = []
    client.mock_supabase.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=NEW_USER_ID)
    )


class TestCadastroHappyPath:
    def test_no_auth_header_required(self, client):
        _seed_base(client)
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 201

    def test_201_shape_and_free_plan_assigned(self, client):
        _seed_base(client)
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) == {"membro_id", "email", "proximo_passo"}
        assert body["email"] == "ana@x.com"
        assert body["proximo_passo"] == "entrar"

        rows = client.mock_supabase.table("membros").select("*").execute().data
        assert len(rows) == 1
        row = rows[0]
        assert row["origem"] == "cadastro"
        assert row["status"] == "ativo"
        assert row["plano_id"] == PLANO_GRATUITO
        assert row["user_id"] == NEW_USER_ID

    def test_creates_the_auth_identity(self, client):
        _seed_base(client)
        client.raw().post("/api/cadastro", json=_payload())
        client.mock_supabase.auth.admin.create_user.assert_called_once()
        payload = client.mock_supabase.auth.admin.create_user.call_args[0][0]
        assert payload["email"] == "ana@x.com"
        assert payload["password"] == "senha1234"

    def test_attaches_membro_org_role(self, client):
        _seed_base(client)
        client.raw().post("/api/cadastro", json=_payload())
        inserted = client.mock_supabase.table("noctus_users").inserted_payloads
        assert len(inserted) == 1
        assert inserted[0]["org_role"] == "membro"
        assert inserted[0]["id"] == NEW_USER_ID

    def test_writes_acesso_evento(self, client):
        _seed_base(client)
        client.raw().post("/api/cadastro", json=_payload())
        eventos = client.mock_supabase.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "acesso"
        assert eventos[0]["descricao"] == "Cadastro realizado pelo site"


class TestCadastroValidation:
    def test_missing_turnstile_token_403(self, client):
        _seed_base(client)
        resp = client.raw().post("/api/cadastro", json=_payload(turnstile_token=None))
        assert resp.status_code == 403
        assert "Verificação de segurança" in resp.json()["detail"]

    def test_aceite_termos_false_400(self, client):
        _seed_base(client)
        resp = client.raw().post("/api/cadastro", json=_payload(aceite_termos=False))
        assert resp.status_code == 400
        assert resp.json()["detail"] == "É preciso aceitar os termos."

    def test_short_senha_422(self, client):
        _seed_base(client)
        resp = client.raw().post("/api/cadastro", json=_payload(senha="short"))
        assert resp.status_code == 422

    def test_extra_field_rejected_422(self, client):
        _seed_base(client)
        resp = client.raw().post("/api/cadastro", json=_payload(extra="nope"))
        assert resp.status_code == 422


class TestCadastroExistingIdentity:
    def test_existing_identity_returns_409_and_nothing_else_happens(self, client):
        _seed_base(client)
        client.mock_supabase.set_table_data(
            "noctus_users",
            [{"id": "existing-1", "email": "ana@x.com", "nome": "Ana", "org_id": None}],
        )
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Este e-mail já tem cadastro. Entre com sua senha."
        client.mock_supabase.auth.admin.create_user.assert_not_called()
        assert client.mock_supabase.table("membros").select("*").execute().data == []


class TestCadastroLinksExistingCrmRow:
    def test_links_staff_created_row_keeps_its_data_assigns_free_plan(self, client):
        """A CRM row created by staff/checkout, no login yet: cadastro
        LINKS `user_id` and keeps everything else (contract: "keep its
        data"), except assigning the free plan since the row had none."""
        _seed_base(client)
        client.mock_supabase.set_table_data("membros", [{
            "id": "aaaaaaaa-1111-1111-1111-111111111111", "org_id": ORG_UUID, "nome": "Ana Staff",
            "email": "ana@x.com", "telefone": None, "status": "pendente",
            "plano_id": None, "origem": "aplicacao", "tags": ["vip"], "user_id": None,
            "observacoes": "nota da equipe", "entrou_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 201
        row = client.mock_supabase.table("membros").select("*").execute().data[0]
        assert row["id"] == "aaaaaaaa-1111-1111-1111-111111111111"
        assert row["origem"] == "aplicacao"  # NOT overwritten to "cadastro"
        assert row["status"] == "pendente"  # kept, not forced to "ativo"
        assert row["observacoes"] == "nota da equipe"
        assert row["plano_id"] == PLANO_GRATUITO  # assigned since it had none
        assert row["user_id"] == NEW_USER_ID

    def test_links_row_that_already_has_a_plan_does_not_overwrite_it(self, client):
        _seed_base(client, planos=[
            _plano_gratuito_row(),
            {"id": PLANO_PAGO, "org_id": ORG_UUID, "nome": "Premium", "descricao": None,
             "preco_centavos": 2700, "ciclo": "mensal", "entitlements": {"grupoterapia": "falar"},
             "ativo": True, "ordem": 2,
             "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"},
        ])
        client.mock_supabase.set_table_data("membros", [{
            "id": "aaaaaaaa-2222-2222-2222-222222222222", "org_id": ORG_UUID, "nome": "Ana Paga",
            "email": "ana@x.com", "telefone": None, "status": "ativo",
            "plano_id": PLANO_PAGO, "origem": "checkout", "tags": [], "user_id": None,
            "observacoes": None, "entrou_em": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 201
        row = client.mock_supabase.table("membros").select("*").execute().data[0]
        assert row["plano_id"] == PLANO_PAGO


class TestCadastroNoFreePlan:
    def test_no_free_plan_configured_returns_409(self, client):
        _seed_base(client, planos=[])
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Plano gratuito não configurado."
