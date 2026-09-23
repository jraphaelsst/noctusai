"""Integrações → E-mail (wave-2 slice B): SMTP account + Gmail connect.

The properties under test: a password/refresh token goes in and never comes
back out; the platform SMTP fallback is visible (``origem: "plataforma"``),
never silent; a Gmail connect with no GCP push config reports
``configuracao_gcp_ok=false`` and does NOT pretend a watch started.

Every collaborator arrives through an ``app.email_deps`` seam, overridden with
the seed Fakes (`FakeEmailSender`, `FakeGmailClient`, `FakeOAuthProvider`) —
nothing of ours is patched.
"""
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import pytest
from noctusai_lib.integrations.gmail import FakeGmailClient
from noctusai_lib.integrations.persistence import SqliteRecordStore
from noctusai_lib.security.oauth import FakeOAuthProvider
from noctusai_lib.testing.clients import TEST_USER_ID

from app.email_deps import (
    get_email_sender_factory,
    get_email_settings,
    get_gmail_client_factory,
    get_gmail_oauth_provider,
    get_gmail_profile_fetcher,
)
from app.repositories import Repositorios
from app.repositories.email import repositorios_email
from app.services import email_config
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin
from tests.email_support import (
    BASE,
    CHAVE,
    COM_GCP,
    MAILBOX,
    ORG,
    SEM_GCP,
    SENHA,
    SMTP,
    TOPICO,
    ConfigBox,
    Senders,
)


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def cfg() -> ConfigBox:
    return ConfigBox(SEM_GCP)


@pytest.fixture
def senders() -> Senders:
    return Senders()


@pytest.fixture
def gmail() -> FakeGmailClient:
    return FakeGmailClient()


@pytest.fixture
def api(client, repos, cfg, senders, gmail):
    from app.main import app

    async def _perfil(_creds):
        return MAILBOX

    overrides = {
        get_repositorios: lambda: repos,
        get_repositorios_admin: lambda: repos,
        get_email_settings: cfg,
        get_email_sender_factory: lambda: senders,
        get_gmail_client_factory: lambda: (lambda _creds: gmail),
        get_gmail_oauth_provider: lambda: FakeOAuthProvider("google"),
        get_gmail_profile_fetcher: lambda: _perfil,
    }
    app.dependency_overrides.update(overrides)
    yield client
    for dep in overrides:
        app.dependency_overrides.pop(dep, None)


# ── SMTP ─────────────────────────────────────────────────────────────
class TestSmtpStatus:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/integracoes/email/smtp").status_code == 401

    def test_unconfigured(self, api):
        data = api.get("/api/integracoes/email/smtp").json()["data"]
        assert data["configurado"] is False
        assert data["origem"] == "nenhuma"

    def test_platform_fallback_is_explicit(self, api, cfg):
        cfg.valor = replace(
            SEM_GCP, smtp_host="smtp.noctus.test", smtp_user="noc@noctus.test",
            smtp_password="noc-pass",
        )
        resp = api.get("/api/integracoes/email/smtp")
        data = resp.json()["data"]
        assert data["configurado"] is True
        assert data["origem"] == "plataforma"
        assert data["host"] == "smtp.noctus.test"
        assert data["security"] == "ssl", "port 465 ⇒ implicit TLS"
        assert "noc-pass" not in resp.text


class TestSmtpSalvar:
    def test_put_stores_and_never_echoes_the_password(self, api, repos):
        resp = api.put("/api/integracoes/email/smtp", json=SMTP)
        assert resp.status_code == 200
        assert SENHA not in resp.text
        assert resp.json()["data"] == {
            "configurado": True, "origem": "org", "host": "smtp.gmail.com", "port": 465,
            "username": "agencia@gmail.com", "security": "ssl",
            "from_email": "agencia@gmail.com", "from_name": "Agência Sol",
        }
        assert SENHA not in api.get("/api/integracoes/email/smtp").text
        guardado = repos.integracao.por_canal(ORG, "smtp")
        assert guardado["token_cifrado"] and SENHA not in guardado["token_cifrado"]
        assert repos.integracao.token_de(ORG, "smtp", CHAVE.encode()) == SENHA

    def test_first_save_needs_a_password(self, api):
        sem = {k: v for k, v in SMTP.items() if k != "password"}
        resp = api.put("/api/integracoes/email/smtp", json=sem)
        assert resp.status_code == 422
        assert resp.json()["code"] == "senha_obrigatoria"

    def test_omitted_password_keeps_the_stored_one(self, api, repos):
        api.put("/api/integracoes/email/smtp", json=SMTP)
        novo = {**{k: v for k, v in SMTP.items() if k != "password"}, "host": "smtp.outro.test"}
        resp = api.put("/api/integracoes/email/smtp", json=novo)
        assert resp.status_code == 200
        assert resp.json()["data"]["host"] == "smtp.outro.test"
        assert repos.integracao.token_de(ORG, "smtp", CHAVE.encode()) == SENHA

    def test_refuses_without_the_cofre_key(self, api, cfg):
        cfg.valor = replace(SEM_GCP, cofre_key="")
        resp = api.put("/api/integracoes/email/smtp", json=SMTP)
        assert resp.status_code == 409
        assert resp.json()["code"] == "cofre_nao_configurado"

    def test_unknown_field_is_rejected(self, api):
        assert api.put("/api/integracoes/email/smtp", json={**SMTP, "x": 1}).status_code == 422

    def test_invalid_security_is_rejected(self, api):
        resp = api.put("/api/integracoes/email/smtp", json={**SMTP, "security": "none"})
        assert resp.status_code == 422

    def test_delete(self, api):
        assert api.delete("/api/integracoes/email/smtp").status_code == 404
        api.put("/api/integracoes/email/smtp", json=SMTP)
        resp = api.delete("/api/integracoes/email/smtp")
        assert resp.status_code == 200
        assert resp.json()["data"]["origem"] == "nenhuma"


class TestSmtpTestar:
    def test_sends_through_the_org_account(self, api, senders):
        api.put("/api/integracoes/email/smtp", json=SMTP)
        resp = api.post("/api/integracoes/email/smtp/testar", json={"para": "dono@x.com"})
        assert resp.status_code == 200
        assert resp.json()["data"]["message_id"].startswith("<fake-1@")
        assert senders.fake.sent[0].to == ["dono@x.com"]
        smtp = senders.configs[0]
        assert (smtp.host, smtp.port, smtp.security, smtp.password) == (
            "smtp.gmail.com", 465, "ssl", SENHA,
        )

    def test_platform_fallback_is_used_when_the_org_has_none(self, api, cfg, senders):
        cfg.valor = replace(
            SEM_GCP, smtp_host="smtp.noctus.test", smtp_port=587,
            smtp_user="noc@noctus.test", smtp_password="noc-pass",
        )
        assert api.post(
            "/api/integracoes/email/smtp/testar", json={"para": "a@b.co"}
        ).status_code == 200
        assert senders.configs[0].security == "starttls"
        assert senders.configs[0].from_email == "noc@noctus.test"

    def test_nothing_configured_is_a_409_not_a_fake_send(self, api, senders):
        resp = api.post("/api/integracoes/email/smtp/testar", json={"para": "a@b.co"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "smtp_nao_configurado"
        assert senders.fake.sent == []

    def test_send_failure_is_surfaced(self, api, senders):
        api.put("/api/integracoes/email/smtp", json=SMTP)
        senders.falhar = True
        resp = api.post("/api/integracoes/email/smtp/testar", json={"para": "a@b.co"})
        assert resp.status_code == 502
        assert resp.json()["code"] == "envio_falhou"

    def test_invalid_address(self, api):
        resp = api.post("/api/integracoes/email/smtp/testar", json={"para": "nope"})
        assert resp.status_code == 422


# ── Gmail ────────────────────────────────────────────────────────────
def _conectar(api) -> str:
    """Walk start → Google → callback; returns the callback redirect URL."""
    url = api.get("/api/integracoes/email/gmail/oauth/start").json()["data"]["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    resp = api.raw().get(
        "/api/integracoes/email/gmail/oauth/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return resp.headers["location"]


class TestGmailStatus:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/integracoes/email/gmail").status_code == 401

    def test_not_connected(self, api):
        data = api.get("/api/integracoes/email/gmail").json()["data"]
        assert data["conectado"] is False
        assert data["watch_ativo"] is False
        assert data["configuracao_gcp_ok"] is False

    def test_gcp_ok_when_all_four_are_set(self, api, cfg):
        cfg.valor = COM_GCP
        assert api.get("/api/integracoes/email/gmail").json()["data"]["configuracao_gcp_ok"] is True

    def test_any_missing_gcp_piece_is_not_ok(self, api, cfg):
        cfg.valor = replace(COM_GCP, gmail_push_service_account="")
        assert api.get("/api/integracoes/email/gmail").json()["data"]["configuracao_gcp_ok"] is False


class TestGmailOAuth:
    def test_start_needs_the_oauth_app(self, api):
        from app.main import app

        app.dependency_overrides[get_gmail_oauth_provider] = lambda: None
        resp = api.get("/api/integracoes/email/gmail/oauth/start")
        assert resp.status_code == 503
        assert resp.json()["code"] == "oauth_nao_configurado"

    def test_start_needs_the_public_url(self, api, cfg):
        cfg.valor = replace(SEM_GCP, public_url=None)
        resp = api.get("/api/integracoes/email/gmail/oauth/start")
        assert resp.status_code == 503
        assert resp.json()["code"] == "url_publica_ausente"

    def test_start_url_carries_scopes_and_the_public_callback(self, api):
        url = api.get("/api/integracoes/email/gmail/oauth/start").json()["data"]["url"]
        query = parse_qs(urlparse(url).query)
        assert query["redirect_uri"] == [f"{BASE}/api/integracoes/email/gmail/oauth/callback"]
        assert "https://www.googleapis.com/auth/gmail.readonly" in query["scope"][0]
        assert "https://www.googleapis.com/auth/gmail.send" in query["scope"][0]

    def test_the_state_binds_the_caller(self, api):
        url = api.get("/api/integracoes/email/gmail/oauth/start").json()["data"]["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        assert email_config.ler_state(state, SEM_GCP) == (ORG, TEST_USER_ID)

    def test_connect_with_gcp_starts_the_watch(self, api, cfg, repos, gmail):
        cfg.valor = COM_GCP
        assert _conectar(api) == f"{BASE}/integracoes?gmail=ok"
        assert gmail.watches == [(TOPICO, ("INBOX",))]
        watch = repositorios_email(repos.store).watches.por_email(ORG, MAILBOX)
        assert watch["history_id"] == gmail.history_id
        data = api.get("/api/integracoes/email/gmail").json()["data"]
        assert data["conectado"] is True
        assert data["email"] == MAILBOX
        assert data["expira_em"] is not None
        assert data["configuracao_gcp_ok"] is True

    def test_connect_without_gcp_does_not_fake_a_watch(self, api, repos, gmail):
        assert _conectar(api) == f"{BASE}/integracoes?gmail=ok"
        assert gmail.watches == [], "no watch may be attempted without GCP config"
        assert repositorios_email(repos.store).watches.da_org(ORG) == []
        data = api.get("/api/integracoes/email/gmail").json()["data"]
        assert data["conectado"] is True
        assert data["watch_ativo"] is False
        assert data["configuracao_gcp_ok"] is False

    def test_refresh_token_is_stored_encrypted(self, api, repos):
        _conectar(api)
        registro = repos.integracao.por_canal(ORG, "gmail")
        assert "fake-refresh-abc" not in registro["token_cifrado"]
        assert "fake-refresh-abc" in repos.integracao.token_de(ORG, "gmail", CHAVE.encode())
        assert "fake-refresh-abc" not in api.get("/api/integracoes/email/gmail").text

    def test_forged_state_is_refused(self, api, repos):
        resp = api.raw().get(
            "/api/integracoes/email/gmail/oauth/callback",
            params={"code": "abc", "state": f"{ORG}:nonce:"},
            follow_redirects=False,
        )
        assert resp.headers["location"] == f"{BASE}/integracoes?gmail=erro&motivo=state_invalido"
        assert repos.integracao.por_canal(ORG, "gmail") is None

    def test_state_signed_under_another_key_is_refused(self, api):
        outro = replace(SEM_GCP, cofre_key="outra-chave")
        state = email_config.emitir_state(ORG, TEST_USER_ID, outro)
        resp = api.raw().get(
            "/api/integracoes/email/gmail/oauth/callback",
            params={"code": "abc", "state": state}, follow_redirects=False,
        )
        assert "motivo=state_invalido" in resp.headers["location"]

    def test_consent_denied(self, api):
        resp = api.raw().get(
            "/api/integracoes/email/gmail/oauth/callback",
            params={"error": "access_denied"}, follow_redirects=False,
        )
        assert "gmail=erro" in resp.headers["location"]

    def test_disconnect_stops_the_watch(self, api, cfg, repos, gmail):
        cfg.valor = COM_GCP
        _conectar(api)
        resp = api.delete("/api/integracoes/email/gmail")
        assert resp.status_code == 200
        assert resp.json()["data"]["conectado"] is False
        assert gmail.stop_calls == 1
        assert repositorios_email(repos.store).watches.da_org(ORG) == []
        assert api.delete("/api/integracoes/email/gmail").status_code == 404
