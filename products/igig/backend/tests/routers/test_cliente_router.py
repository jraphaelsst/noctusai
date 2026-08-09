"""Cliente router — the first end-to-end surface over the persistence seam.

Auth still resolves through Supabase (the `client` fixture's mock), while
DOMAIN data comes from an in-memory SQLite store injected by overriding
``get_repositorios``. That split is exactly the product's architecture, so
these tests exercise the real wiring rather than a simplification of it.

Every assertion pins ``.status_code`` per ``check_test_status_assertion``.
"""
from __future__ import annotations

import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.repositories import Repositorios
from app.store import aplicar_schema_sqlite, get_repositorios

#: The org the conftest's mock user belongs to.
ORG = "test-org-123"


@pytest.fixture
def repos() -> Repositorios:
    """A throwaway SQLite store with the real domain schema applied."""
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos):
    """`client`, with domain persistence pointed at the throwaway store."""
    from app.main import app

    app.dependency_overrides[get_repositorios] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)


class TestAuthBoundary:
    """Unauth'd callers never reach the store."""

    def test_list_without_auth_returns_401(self, api):
        assert api.raw().get("/api/clientes").status_code == 401

    def test_create_without_auth_returns_401(self, api):
        assert api.raw().post("/api/clientes", json={"nome": "X"}).status_code == 401

    def test_detail_without_auth_returns_401(self, api):
        assert api.raw().get("/api/clientes/qualquer").status_code == 401

    def test_delete_without_auth_returns_401(self, api):
        assert api.raw().delete("/api/clientes/qualquer").status_code == 401


class TestValidation:
    def test_empty_nome_returns_422(self, api):
        assert api.post("/api/clientes", json={"nome": ""}).status_code == 422

    def test_unknown_field_returns_422(self, api):
        """StrictHttpModel — a typo'd field must not be silently ignored."""
        resp = api.post("/api/clientes", json={"nome": "X", "nomee": "typo"})
        assert resp.status_code == 422

    def test_limit_above_cap_returns_422(self, api):
        assert api.get("/api/clientes?limit=999").status_code == 422

    def test_invalid_status_on_update_returns_422(self, api, repos):
        criado = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
        resp = api.patch(f"/api/clientes/{criado['id']}", json={"status": "inventado"})
        assert resp.status_code == 422


class TestCrud:
    def test_create_returns_201_and_defaults_to_prospect(self, api):
        resp = api.post("/api/clientes", json={"nome": "Padaria Sol", "nicho": "alimentacao"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["nome"] == "Padaria Sol"
        assert body["status"] == "prospect"
        assert body["id"]

    def test_created_client_is_readable_back(self, api):
        criado = api.post("/api/clientes", json={"nome": "Padaria Sol"}).json()
        resp = api.get(f"/api/clientes/{criado['id']}")
        assert resp.status_code == 200
        assert resp.json()["nome"] == "Padaria Sol"

    def test_list_returns_items_and_total(self, api):
        for nome in ("Padaria Sol", "Bar do Zé"):
            api.post("/api/clientes", json={"nome": nome})
        resp = api.get("/api/clientes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {c["nome"] for c in body["itens"]} == {"Padaria Sol", "Bar do Zé"}

    def test_total_reflects_all_matches_not_the_page(self, api):
        """A paged list must not report the page size as the total."""
        for i in range(5):
            api.post("/api/clientes", json={"nome": f"Cliente {i}"})
        body = api.get("/api/clientes?limit=2").json()
        assert len(body["itens"]) == 2
        assert body["total"] == 5

    def test_busca_filters_by_name(self, api):
        api.post("/api/clientes", json={"nome": "Padaria Sol"})
        api.post("/api/clientes", json={"nome": "Bar do Zé"})
        body = api.get("/api/clientes?busca=padaria").json()
        assert [c["nome"] for c in body["itens"]] == ["Padaria Sol"]

    def test_status_filter(self, api):
        criado = api.post("/api/clientes", json={"nome": "Padaria Sol"}).json()
        api.post("/api/clientes", json={"nome": "Bar do Zé"})
        api.post(f"/api/clientes/{criado['id']}/ativar")
        body = api.get("/api/clientes?status=ativo").json()
        assert [c["nome"] for c in body["itens"]] == ["Padaria Sol"]

    def test_patch_updates_fields(self, api):
        criado = api.post("/api/clientes", json={"nome": "Padaria Sol"}).json()
        resp = api.patch(f"/api/clientes/{criado['id']}", json={"nicho": "alimentacao"})
        assert resp.status_code == 200
        assert resp.json()["nicho"] == "alimentacao"
        assert resp.json()["nome"] == "Padaria Sol"

    def test_empty_patch_returns_400(self, api):
        criado = api.post("/api/clientes", json={"nome": "Padaria Sol"}).json()
        assert api.patch(f"/api/clientes/{criado['id']}", json={}).status_code == 400

    def test_ativar_promotes_the_prospect(self, api):
        criado = api.post("/api/clientes", json={"nome": "Padaria Sol"}).json()
        resp = api.post(f"/api/clientes/{criado['id']}/ativar")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ativo"

    def test_delete_then_detail_returns_404(self, api):
        criado = api.post("/api/clientes", json={"nome": "Padaria Sol"}).json()
        assert api.delete(f"/api/clientes/{criado['id']}").status_code == 200
        assert api.get(f"/api/clientes/{criado['id']}").status_code == 404


class TestMisses:
    """A miss is a 404 in Portuguese — never a 500, never an empty 200."""

    def test_detail_miss_returns_404(self, api):
        assert api.get("/api/clientes/nao-existe").status_code == 404

    def test_patch_miss_returns_404(self, api):
        assert api.patch("/api/clientes/nao-existe", json={"nome": "X"}).status_code == 404

    def test_ativar_miss_returns_404(self, api):
        assert api.post("/api/clientes/nao-existe/ativar").status_code == 404

    def test_delete_miss_returns_404(self, api):
        assert api.delete("/api/clientes/nao-existe").status_code == 404

    def test_miss_detail_message_is_portuguese(self, api):
        """The seed wraps errors as {"error": {"code", "message"}} — not
        FastAPI's bare `detail`. Asserting the platform envelope keeps this
        honest if a handler is ever bypassed."""
        resp = api.get("/api/clientes/nao-existe")
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Cliente não encontrado"


class TestTenantIsolation:
    """The app-layer org boundary, exercised through the HTTP surface."""

    def test_another_orgs_client_is_a_404_not_a_leak(self, api, repos):
        alheio = repos.cliente.criar("org-de-outra-agencia", {"nome": "Concorrente"})
        assert api.get(f"/api/clientes/{alheio['id']}").status_code == 404

    def test_list_never_returns_another_orgs_rows(self, api, repos):
        repos.cliente.criar("org-de-outra-agencia", {"nome": "Concorrente"})
        api.post("/api/clientes", json={"nome": "Padaria Sol"})
        body = api.get("/api/clientes").json()
        assert [c["nome"] for c in body["itens"]] == ["Padaria Sol"]
        assert body["total"] == 1

    def test_cannot_delete_another_orgs_client(self, api, repos):
        alheio = repos.cliente.criar("org-de-outra-agencia", {"nome": "Concorrente"})
        assert api.delete(f"/api/clientes/{alheio['id']}").status_code == 404
        assert repos.cliente.buscar("org-de-outra-agencia", alheio["id"])["nome"] == "Concorrente"
