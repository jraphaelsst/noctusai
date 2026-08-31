"""Integrações de canal — the Módulo 5 credential shell.

The property under test: a token goes IN and never comes back out. Everything
else here is setup-screen ergonomics.
"""
import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin

ORG = str(coerce_org_uuid("test-org-123"))
CHAVE = Fernet.generate_key().decode()
TOKEN = "EAAG-token-super-secreto"


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos, monkeypatch):
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "igig_cofre_key", CHAVE)
    for env in ("igig_meta_token", "igig_tiktok_token", "igig_linkedin_token"):
        monkeypatch.setattr(settings, env, "")
    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)


class TestStatus:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/integracoes").status_code == 401

    def test_lists_every_channel_even_when_unconfigured(self, api):
        """The setup screen renders the same shape whether or not anything is set."""
        body = api.get("/api/integracoes").json()
        assert {i["canal"] for i in body} == {"instagram", "facebook", "tiktok", "linkedin"}
        assert all(i["conectado"] is False for i in body)
        assert all(i["origem"] == "nenhuma" for i in body)

    def test_env_fallback_shows_as_connected_from_env(self, api, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "igig_meta_token", "env-token")
        body = {i["canal"]: i for i in api.get("/api/integracoes").json()}
        assert body["instagram"]["conectado"] is True
        assert body["instagram"]["origem"] == "env"
        assert body["tiktok"]["conectado"] is False

    def test_reports_cofre_configurado_true_when_the_key_is_set(self, api):
        """The `api` fixture sets `igig_cofre_key` — the setup screen must
        know this WITHOUT trying (and failing) a save first."""
        body = api.get("/api/integracoes").json()
        assert all(i["cofre_configurado"] is True for i in body)

    def test_reports_cofre_configurado_false_when_the_key_is_unset(self, api, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "igig_cofre_key", "")
        body = api.get("/api/integracoes").json()
        assert all(i["cofre_configurado"] is False for i in body)


class TestConexao:
    def test_connect_returns_201_and_no_token(self, api):
        """The assertion that matters: a token goes in, never comes back."""
        resp = api.post("/api/integracoes/instagram",
                        json={"token": TOKEN, "conta_externa": "@padariasol"})
        assert resp.status_code == 201
        assert TOKEN not in resp.text
        assert "token" not in resp.json()
        assert resp.json()["conta_externa"] == "@padariasol"

    def test_status_never_leaks_the_token(self, api):
        api.post("/api/integracoes/instagram", json={"token": TOKEN})
        assert TOKEN not in api.get("/api/integracoes").text

    def test_stored_token_is_ciphertext(self, api, repos):
        api.post("/api/integracoes/instagram", json={"token": TOKEN})
        registro = repos.integracao.por_canal(ORG, "instagram")
        assert registro["token_cifrado"] != TOKEN
        assert TOKEN not in str(registro)

    def test_round_trips_for_the_publisher(self, api, repos):
        api.post("/api/integracoes/instagram", json={"token": TOKEN})
        assert repos.integracao.token_de(
            ORG, "instagram", CHAVE.encode("utf-8")
        ) == TOKEN

    def test_reconnecting_replaces_the_token(self, api, repos):
        api.post("/api/integracoes/instagram", json={"token": TOKEN})
        api.post("/api/integracoes/instagram", json={"token": "novo-token"})
        assert repos.integracao.token_de(
            ORG, "instagram", CHAVE.encode("utf-8")
        ) == "novo-token"
        assert len(repos.integracao.listar(ORG)) == 1, "one row per channel"

    def test_invalid_channel_returns_422(self, api):
        assert api.post("/api/integracoes/orkut", json={"token": "x"}).status_code == 422

    def test_without_encryption_key_it_refuses(self, api, monkeypatch):
        """Never a plaintext downgrade — same contract as the Cofre."""
        from app.config import settings

        monkeypatch.setattr(settings, "igig_cofre_key", "")
        resp = api.post("/api/integracoes/instagram", json={"token": TOKEN})
        assert resp.status_code == 409
        assert "IGIG_COFRE_KEY" in resp.text

    def test_disconnect(self, api):
        api.post("/api/integracoes/instagram", json={"token": TOKEN})
        assert api.delete("/api/integracoes/instagram").status_code == 200
        body = {i["canal"]: i for i in api.get("/api/integracoes").json()}
        assert body["instagram"]["conectado"] is False

    def test_disconnect_unconnected_returns_404(self, api):
        assert api.delete("/api/integracoes/tiktok").status_code == 404

    def test_integrations_are_org_scoped(self, api, repos):
        api.post("/api/integracoes/instagram", json={"token": TOKEN})
        assert repos.integracao.por_canal("outra-org", "instagram") is None


class TestPublicacaoUsaOToken:
    def test_auth_failure_is_surfaced_on_the_integration(self, api, repos, monkeypatch):
        """So the setup screen can say 'reconectar' instead of staying silent."""
        import app.routers.distribuicao_router as dr
        from app.services.publicacao_publisher import PublisherNotConfigured

        api.post("/api/integracoes/instagram", json={"token": TOKEN})

        class SemAuth:
            canal = "instagram"

            def publicar(self, **_kwargs):
                raise PublisherNotConfigured("token expirado")

        monkeypatch.setattr(dr, "get_publisher", lambda *_a, **_k: SemAuth())
        cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
        pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})
        pub = api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": pauta["id"], "canal": "instagram",
            "agendada_para": "2026-09-01T09:00:00",
        }).json()
        api.post(f"/api/distribuicao/publicacoes/{pub['id']}/executar")

        estado = {i["canal"]: i for i in api.get("/api/integracoes").json()}["instagram"]
        assert estado["ultimo_erro"] and "expirado" in estado["ultimo_erro"]
