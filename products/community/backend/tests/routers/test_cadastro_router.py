"""Tests for `cadastro_router` — contract §Identity, `POST /api/cadastro`,
slice BE-A. PUBLIC, no auth header needed (`client.raw()`).
"""
from types import SimpleNamespace

from noctusai_lib.integrations.turnstile import FakeTurnstileVerifier

from app.services.captcha import CaptchaGate, get_captcha_resolver
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


def _captcha_obrigatorio(client, *, rejeitar=()):
    """Router-level seam: an ENABLED captcha gate backed by the seed Fake,
    via FastAPI `dependency_overrides` (cleared per test by conftest)."""
    fake = FakeTurnstileVerifier()
    fake.rejected_tokens.update(rejeitar)
    gate = CaptchaGate.com_verificador(fake, site_key="0xsite")
    client.raw().app.dependency_overrides[get_captcha_resolver] = lambda: (lambda org_id: gate)
    return fake


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
        _captcha_obrigatorio(client)
        resp = client.raw().post("/api/cadastro", json=_payload(turnstile_token=None))
        assert resp.status_code == 403
        assert "Verificação de segurança" in resp.json()["detail"]

    def test_captcha_enabled_bad_token_403(self, client):
        _seed_base(client)
        _captcha_obrigatorio(client, rejeitar={"bad"})
        resp = client.raw().post("/api/cadastro", json=_payload(turnstile_token="bad"))
        assert resp.status_code == 403

    def test_captcha_enabled_valid_token_201(self, client):
        _seed_base(client)
        _captcha_obrigatorio(client)
        resp = client.raw().post("/api/cadastro", json=_payload(turnstile_token="tok"))
        assert resp.status_code == 201

    def test_captcha_disabled_accepts_missing_token_201(self, client):
        """Soft-launch captcha-off mode: no Turnstile keys configured."""
        _seed_base(client)
        resp = client.raw().post("/api/cadastro", json=_payload(turnstile_token=None))
        assert resp.status_code == 201

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


class TestCadastroRefusesExistingCrmEmail:
    """A public form must never LINK an existing CRM row: whoever typed the
    email would inherit a stranger's record, payments and subscription
    (security review 2026-09-28, H5). Staff grant access with "Criar acesso"."""

    MSG = "Já existe um cadastro com este e-mail. Fale com a equipe para receber seu acesso."

    def _seed_crm_row(self, client, email="ana@x.com"):
        client.mock_supabase.set_table_data("membros", [{
            "id": "aaaaaaaa-1111-1111-1111-111111111111", "org_id": ORG_UUID, "nome": "Ana Staff",
            "email": email, "telefone": None, "status": "pendente",
            "plano_id": None, "origem": "aplicacao", "tags": ["vip"], "user_id": None,
            "observacoes": "nota da equipe", "entrou_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])

    def test_existing_crm_email_409_and_no_identity_created(self, client):
        _seed_base(client)
        self._seed_crm_row(client)
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 409
        assert resp.json()["detail"] == self.MSG
        client.mock_supabase.auth.admin.create_user.assert_not_called()
        (row,) = client.mock_supabase.table("membros").select("*").execute().data
        assert row["user_id"] is None
        assert row["observacoes"] == "nota da equipe"

    def test_identity_is_undone_when_a_later_step_fails(self, client):
        """`attach_user_to_org` refuses (409) a profile already in ANOTHER
        org; the identity this request just created must not survive."""
        _seed_base(client)
        client.mock_supabase.set_table_data("noctus_users", [{
            "id": NEW_USER_ID, "org_id": "outra-org", "org_role": "admin", "role": "user",
        }])
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 409
        client.mock_supabase.auth.admin.delete_user.assert_called_once_with(NEW_USER_ID)
        assert client.mock_supabase.table("membros").select("*").execute().data == []


class TestCadastroNoFreePlan:
    def test_no_free_plan_configured_returns_409(self, client):
        _seed_base(client, planos=[])
        resp = client.raw().post("/api/cadastro", json=_payload())
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Plano gratuito não configurado."
