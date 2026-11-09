"""
Tests for the public SSO entry router (slice S3, contract products/core/docs/sso-entry-contract.md).

GET /api/sso/produto/{slug} -- {slug, nome, icone, landing_url}; ACTIVE catalog rows only.
"""
import pytest

from noctusai_lib.api.access_tiers import access_tier  # noqa: F401  (marker is read off the route below)

from app.routers import sso_public


def _seed(client, monkeypatch, *, ativo=True, url_base="https://agents.noctusai.com", slug="agents", rows=None):
    monkeypatch.setenv("PRODUCT_URL_CORE", "https://noctusai.com")
    for k in [k for k in __import__("os").environ if k.startswith("PRODUCT_URL_") and k != "PRODUCT_URL_CORE"]:
        monkeypatch.delenv(k, raising=False)
    client.mock_supabase.set_table_data("products", rows if rows is not None else [{
        "slug": slug, "nome": "Agentes", "icone": "bot", "url_base": url_base,
        "ativo": ativo, "deploy_scope": "live",
    }])


class TestProdutoPublico:
    def test_active_product_returns_exact_shape(self, client, monkeypatch):
        _seed(client, monkeypatch)
        resp = client.get("/api/sso/produto/agents")
        assert resp.status_code == 200
        assert resp.json() == {
            "slug": "agents", "nome": "Agentes", "icone": "bot",
            "landing_url": "https://agents.noctusai.com",
        }

    def test_trailing_slash_in_url_base_is_not_carried(self, client, monkeypatch):
        _seed(client, monkeypatch, url_base="https://agents.noctusai.com/")
        assert client.get("/api/sso/produto/agents").json()["landing_url"] == "https://agents.noctusai.com"

    def test_no_internal_catalog_field_leaks(self, client, monkeypatch):
        _seed(client, monkeypatch)
        assert set(client.get("/api/sso/produto/agents").json()) == {"slug", "nome", "icone", "landing_url"}

    def test_anonymous_caller_is_allowed(self, client, monkeypatch):
        """No Authorization header and no auth dependency: public by declaration."""
        _seed(client, monkeypatch)
        resp = client.get("/api/sso/produto/agents", headers={})
        assert resp.status_code == 200
        route = next(r for r in sso_public.router.routes if r.path == "/api/sso/produto/{slug}")
        assert not route.dependant.dependencies, "a public route carries no auth dependency"
        assert sso_public.router.access_tier == "public"
        assert sso_public.router.access_tier_category == "auth"

    def test_inactive_product_is_404(self, client, monkeypatch):
        _seed(client, monkeypatch, ativo=False)
        resp = client.get("/api/sso/produto/agents")
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Produto não encontrado"

    def test_row_with_non_true_ativo_is_404_even_if_the_data_layer_returns_it(self, client, monkeypatch):
        _seed(client, monkeypatch, ativo="true")
        assert client.get("/api/sso/produto/agents").status_code == 404

    def test_unknown_slug_is_404_same_body_as_inactive(self, client, monkeypatch):
        _seed(client, monkeypatch, rows=[])
        unknown = client.get("/api/sso/produto/nope")
        _seed(client, monkeypatch, ativo=False)
        inactive = client.get("/api/sso/produto/agents")
        assert unknown.status_code == inactive.status_code == 404
        assert unknown.json() == inactive.json()

    def test_cross_site_url_base_is_409(self, client, monkeypatch):
        _seed(client, monkeypatch, url_base="https://academiadareciclagem.eco")
        resp = client.get("/api/sso/produto/agents")
        assert resp.status_code == 409
        assert "mesmo site" in resp.text

    def test_unresolvable_url_is_409(self, client, monkeypatch):
        _seed(client, monkeypatch, url_base=None)
        resp = client.get("/api/sso/produto/agents")
        assert resp.status_code == 409
        assert "URL" in resp.text

    def test_env_override_wins_over_db_url_base(self, client, monkeypatch):
        _seed(client, monkeypatch, url_base="https://stale.noctusai.com")
        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.noctusai.com")
        assert client.get("/api/sso/produto/agents").json()["landing_url"] == "https://agents.noctusai.com"

    def test_route_is_rate_limited_per_ip(self):
        """The limiter decorator is on the route (same limiter the other sso routes use)."""
        from app.rate_limit import limiter
        names = {n for n in limiter._route_limits}  # noqa: SLF001 -- slowapi exposes registered limits only here
        assert any("get_produto_publico" in n for n in names)
