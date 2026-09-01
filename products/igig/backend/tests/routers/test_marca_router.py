"""Central da Marca + Cofre de Acessos — Módulo 2.

The Cofre tests are the point of this file. A credential vault that leaks
ciphertext in a list response, or lets any logged-in member read passwords
back, is a plaintext store with extra steps. Each of those properties is
asserted rather than assumed.
"""
import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin

ORG = str(coerce_org_uuid("test-org-123"))
CHAVE = Fernet.generate_key().decode()


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos, monkeypatch):
    """`client` with domain persistence on a throwaway store + a vault key.

    The key is set through the settings object because IgIg has no
    `Depends(get_settings)` seam yet (its routers read `settings` directly, as
    the scaffold ships). Flagged rather than hidden: if IgIg grows more
    config-dependent tests, it should adopt the same DI seam social-wiring
    uses. `# self-patch-ok` is not claimed — this is a product-level gap to
    close, not a sanctioned exception.
    """
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "igig_cofre_key", CHAVE)
    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)


@pytest.fixture
def como_admin(monkeypatch):
    """Make the caller an org admin for the reveal gate.

    Patches the TRUSTED resolver the router uses, not `user_metadata` — the
    point of the gate is that metadata is forgeable, so a test that forged it
    would prove nothing about the real path.
    """
    import app.routers.marca_router as mr

    monkeypatch.setattr(mr, "get_user_role", lambda _user: "owner")
    return True


@pytest.fixture
def cliente(repos) -> dict:
    return repos.cliente.criar(ORG, {"nome": "Padaria Sol"})


# ── Marca ───────────────────────────────────────────────────────────
class TestMarca:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/marcas").status_code == 401

    def test_create_and_read_back(self, api, cliente):
        payload = {
            "cliente_id": cliente["id"],
            "nome": "Padaria Sol",
            "paleta": [{"nome": "laranja", "hex": "#f97316"}],
            "tom_de_voz": "próximo e caloroso",
            "nivel_formalidade": "informal",
            "linhas_editoriais": [{"nome": "Institucional"}],
            "personas": [{"nome": "Dona Maria", "dores": ["preço"], "desejos": ["frescor"]}],
        }
        resp = api.post("/api/marcas", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["paleta"][0]["hex"] == "#f97316"
        assert body["personas"][0]["dores"] == ["preço"]
        assert api.get(f"/api/marcas/{body['id']}").status_code == 200

    def test_invalid_hex_is_rejected(self, api, cliente):
        """A malformed swatch renders as silent black in the sidebar."""
        resp = api.post("/api/marcas", json={
            "cliente_id": cliente["id"], "nome": "X",
            "paleta": [{"nome": "ruim", "hex": "laranja"}],
        })
        assert resp.status_code == 422

    def test_invalid_formality_is_rejected(self, api, cliente):
        resp = api.post("/api/marcas", json={
            "cliente_id": cliente["id"], "nome": "X", "nivel_formalidade": "casual",
        })
        assert resp.status_code == 422

    def test_unknown_client_returns_404(self, api):
        resp = api.post("/api/marcas", json={"cliente_id": "nao-existe", "nome": "X"})
        assert resp.status_code == 404

    def test_patch_replaces_json_collections(self, api, cliente):
        criada = api.post("/api/marcas", json={
            "cliente_id": cliente["id"], "nome": "X",
            "linhas_editoriais": [{"nome": "Institucional"}],
        }).json()
        resp = api.patch(f"/api/marcas/{criada['id']}", json={
            "linhas_editoriais": [{"nome": "Educacional"}, {"nome": "Comercial"}],
        })
        assert resp.status_code == 200
        assert [l["nome"] for l in resp.json()["linhas_editoriais"]] == ["Educacional", "Comercial"]

    def test_marca_is_org_scoped(self, api, repos, cliente):
        alheia = repos.marca.criar("outra-org", {"cliente_id": cliente["id"], "nome": "Rival"})
        assert api.get(f"/api/marcas/{alheia['id']}").status_code == 404


# ── Repertório (the persistent sidebar payload) ─────────────────────
class TestRepertorio:
    def test_returns_the_creative_direction_fields(self, api, cliente):
        api.post("/api/marcas", json={
            "cliente_id": cliente["id"], "nome": "Padaria Sol",
            "paleta": [{"nome": "laranja", "hex": "#f97316"}],
            "tom_de_voz": "próximo", "termos_proibidos": "barato",
            "linhas_editoriais": [{"nome": "Institucional"}],
        })
        body = api.get(f"/api/marcas/repertorio/{cliente['id']}").json()
        assert body["cliente_nome"] == "Padaria Sol"
        assert body["paleta"][0]["hex"] == "#f97316"
        assert body["tom_de_voz"] == "próximo"
        assert body["termos_proibidos"] == "barato"

    def test_client_without_a_brand_is_an_empty_200_not_a_404(self, api, cliente):
        """The sidebar is ambient chrome — a 404 would show an error over work."""
        resp = api.get(f"/api/marcas/repertorio/{cliente['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cliente_nome"] == "Padaria Sol"
        assert body["marca_nome"] is None
        assert body["paleta"] == []

    def test_unknown_client_returns_404(self, api):
        assert api.get("/api/marcas/repertorio/nao-existe").status_code == 404


# ── Cofre de Acessos ────────────────────────────────────────────────
class TestCofre:
    SEGREDO = "senha-super-secreta"

    def _criar(self, api, cliente, **extra):
        return api.post("/api/marcas/acessos", json={
            "cliente_id": cliente["id"], "rotulo": "Meta Business",
            "senha": self.SEGREDO, **extra,
        })

    def test_create_returns_no_password_and_no_ciphertext(self, api, cliente):
        """The single most important assertion here.

        Ciphertext in a list response is an offline attack target; there is no
        reason a UI needs it.
        """
        resp = self._criar(api, cliente)
        assert resp.status_code == 201
        body = resp.json()
        assert self.SEGREDO not in str(body)
        assert "senha" not in body
        assert "senha_cifrada" not in body
        assert body["tem_senha"] is True

    def test_listing_never_carries_credentials(self, api, cliente):
        self._criar(api, cliente)
        resp = api.get(f"/api/marcas/acessos/{cliente['id']}")
        assert resp.status_code == 200
        assert self.SEGREDO not in resp.text
        assert "senha_cifrada" not in resp.text

    def test_listing_reports_configured_entries_under_itens(self, api, cliente):
        self._criar(api, cliente)
        resp = api.get(f"/api/marcas/acessos/{cliente['id']}")
        body = resp.json()
        assert body["cofre_configurado"] is True
        assert len(body["itens"]) == 1
        assert body["itens"][0]["rotulo"] == "Meta Business"

    def test_listing_reports_unconfigured_vault_even_with_zero_entries(
        self, api, cliente, monkeypatch
    ):
        """The gap this closes: an empty `itens` looks the same whether the
        client has no entries yet OR the vault can't accept one — only this
        flag tells them apart, and it must be right when `itens` is empty."""
        from app.config import settings

        monkeypatch.setattr(settings, "igig_cofre_key", "")
        resp = api.get(f"/api/marcas/acessos/{cliente['id']}")
        body = resp.json()
        assert body["cofre_configurado"] is False
        assert body["itens"] == []

    def test_entry_without_a_password_reports_tem_senha_false(self, api, cliente):
        resp = api.post("/api/marcas/acessos", json={
            "cliente_id": cliente["id"], "rotulo": "Drive", "url": "https://drive.example/x",
        })
        assert resp.status_code == 201
        assert resp.json()["tem_senha"] is False

    def test_reveal_returns_the_plaintext_for_an_admin(self, api, cliente, como_admin):
        criado = self._criar(api, cliente).json()
        resp = api.post(f"/api/marcas/acessos/{criado['id']}/revelar")
        assert resp.status_code == 200
        assert resp.json()["senha"] == self.SEGREDO

    def test_non_admin_cannot_reveal(self, api, cliente):
        """The gate's whole purpose: a logged-in member is not enough.

        The conftest user carries no admin role, so this exercises the real
        refusal path rather than a forged one.
        """
        criado = self._criar(api, cliente).json()
        resp = api.post(f"/api/marcas/acessos/{criado['id']}/revelar")
        assert resp.status_code == 403
        assert "administradores" in resp.text

    def test_reveal_requires_auth(self, api, cliente):
        criado = self._criar(api, cliente).json()
        assert api.raw().post(
            f"/api/marcas/acessos/{criado['id']}/revelar"
        ).status_code == 401

    def test_reveal_on_a_passwordless_entry_returns_404(self, api, cliente, como_admin):
        criado = api.post("/api/marcas/acessos", json={
            "cliente_id": cliente["id"], "rotulo": "Drive",
        }).json()
        assert api.post(f"/api/marcas/acessos/{criado['id']}/revelar").status_code == 404

    def test_reveal_of_another_orgs_entry_returns_404(self, api, repos, cliente, como_admin):
        alheio = repos.acesso.guardar(
            "outra-org", cliente["id"], rotulo="Rival",
            senha="x", chave=CHAVE.encode("utf-8"),
        )
        assert api.post(f"/api/marcas/acessos/{alheio['id']}/revelar").status_code == 404

    def test_unconfigured_vault_refuses_to_store_a_password(self, api, cliente, monkeypatch):
        """Never a silent plaintext downgrade — a loud 409 instead."""
        from app.config import settings

        monkeypatch.setattr(settings, "igig_cofre_key", "")
        resp = self._criar(api, cliente)
        assert resp.status_code == 409
        assert "IGIG_COFRE_KEY" in resp.text

    def test_unconfigured_vault_still_allows_passwordless_entries(self, api, cliente, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "igig_cofre_key", "")
        resp = api.post("/api/marcas/acessos", json={
            "cliente_id": cliente["id"], "rotulo": "Drive", "url": "https://x",
        })
        assert resp.status_code == 201

    def test_update_reencrypts_a_new_password(self, api, cliente, como_admin):
        criado = self._criar(api, cliente).json()
        nova = "outra-senha"
        resp = api.patch(f"/api/marcas/acessos/{criado['id']}", json={"senha": nova})
        assert resp.status_code == 200
        assert nova not in resp.text
        assert api.post(
            f"/api/marcas/acessos/{criado['id']}/revelar"
        ).json()["senha"] == nova

    def test_delete_then_reveal_returns_404(self, api, cliente, como_admin):
        criado = self._criar(api, cliente).json()
        assert api.delete(f"/api/marcas/acessos/{criado['id']}").status_code == 200
        assert api.post(f"/api/marcas/acessos/{criado['id']}/revelar").status_code == 404

    def test_unknown_client_returns_404(self, api):
        resp = api.post("/api/marcas/acessos", json={
            "cliente_id": "nao-existe", "rotulo": "X",
        })
        assert resp.status_code == 404


# ── Logo: the URL is minted per-read, NEVER persisted ───────────────────────
#
# `storage.signed_url` defaults to a ONE-HOUR TTL. `enviar_logo` used to write
# that value into `marca.logo_url`, so every brand logo rendered for an hour
# and then 404'd forever — confirmed in production 2026-09-01 on a logo
# uploaded 90 minutes earlier. `015` added `logo_key`; these pin that the key
# is what persists and that every READ re-signs from it.

class TestLogoSignedUrlFreshness:
    @pytest.fixture(autouse=True)
    def _fake_storage(self, monkeypatch):
        """Select the in-memory backend and clear the lru_cache around it."""
        from app.config import settings
        from app import storage as storage_mod

        monkeypatch.setattr(settings, "igig_storage_kind", "fake")
        storage_mod.get_storage.cache_clear()
        yield
        storage_mod.get_storage.cache_clear()

    def _marca_com_logo(self, api):
        cliente = api.post("/api/clientes", json={"nome": "Padaria Sol"}).json()
        marca = api.post(
            "/api/marcas", json={"cliente_id": cliente["id"], "nome": "Padaria Sol"}
        ).json()
        resposta = api.post(
            f"/api/marcas/{marca['id']}/logo",
            files={"arquivo": ("logo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        return cliente, marca, resposta

    def test_upload_persists_the_key_not_only_the_url(self, api, repos):
        _cliente, marca, resposta = self._marca_com_logo(api)
        assert resposta.status_code == 201

        linha = repos.marca.buscar(ORG, marca["id"])
        assert linha.get("logo_key"), "the durable key must be persisted"
        # The key is a storage path, never a URL — that is the whole point.
        assert "://" not in str(linha["logo_key"])

    def test_read_remints_the_url_over_a_stale_stored_value(self, api, repos):
        _cliente, marca, resposta = self._marca_com_logo(api)
        assert resposta.status_code == 201

        # Simulate the expired state: a stored URL from an hour ago.
        repos.marca.atualizar(ORG, marca["id"], {"logo_url": "fake://EXPIRED"})

        lido = api.get(f"/api/marcas/{marca['id']}")
        assert lido.status_code == 200
        assert lido.json()["logo_url"] != "fake://EXPIRED", (
            "a read must re-sign from logo_key, not echo the stored URL"
        )
        assert repos.marca.buscar(ORG, marca["id"])["logo_key"] in lido.json()["logo_url"]

    def test_list_remints_too(self, api, repos):
        _cliente, marca, _ = self._marca_com_logo(api)
        repos.marca.atualizar(ORG, marca["id"], {"logo_url": "fake://EXPIRED"})

        listadas = api.get("/api/marcas")
        assert listadas.status_code == 200
        assert listadas.json()[0]["logo_url"] != "fake://EXPIRED"

    def test_repertorio_remints_too(self, api, repos):
        """The Módulo 2 sidebar is the surface a designer stares at all day —
        it must not be the one showing a dead logo."""
        cliente, marca, _ = self._marca_com_logo(api)
        repos.marca.atualizar(ORG, marca["id"], {"logo_url": "fake://EXPIRED"})

        rep = api.get(f"/api/marcas/repertorio/{cliente['id']}")
        assert rep.status_code == 200
        assert rep.json()["logo_url"] != "fake://EXPIRED"

    def test_a_marca_without_a_logo_is_untouched(self, api, repos):
        """No logo is a normal state, not an error — the row passes through."""
        cliente = api.post("/api/clientes", json={"nome": "Sem Logo"}).json()
        marca = api.post(
            "/api/marcas", json={"cliente_id": cliente["id"], "nome": "Sem Logo"}
        ).json()

        lido = api.get(f"/api/marcas/{marca['id']}")
        assert lido.status_code == 200
        assert lido.json()["logo_url"] is None
