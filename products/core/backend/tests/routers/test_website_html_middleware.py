"""Tests for `app.routers.website_html` — host-split serving (contract §5)."""
from tests.conftest import website_defaults_dict


WEBSITE_HOST = "noctusai.com"
APP_HOST = "core.noctusai.com"


class TestHostSplit:
    def test_website_host_serves_prerendered_home(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "<h1>" in resp.text
        assert resp.headers["cache-control"] == "public, max-age=60"

    def test_app_host_untouched(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/", headers={"Host": APP_HOST})
        assert resp.status_code == 200
        # Whatever the app root returns (JSON platform info) — NOT the
        # website's prerendered HTML.
        assert "<h1>" not in resp.text

    def test_www_redirects_to_apex_301(self, unauth_client, website_site):
        resp = unauth_client.get(
            "/produtos", headers={"Host": "www.noctusai.com"}, follow_redirects=False
        )
        assert resp.status_code == 301
        assert resp.headers["location"] == "https://noctusai.com/produtos"

    def test_dev_override_query_param(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/", params={"__site": "1"})
        assert resp.status_code == 200
        assert "<h1>" in resp.text

    def test_dev_override_header(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/", headers={"X-NX-Site": "1"})
        assert resp.status_code == 200
        assert "<h1>" in resp.text


class TestKillSwitch:
    def test_site_disabled_falls_through_to_app_shell(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        disabled = {**website_defaults_dict(), "site_enabled": False}
        mock_sb.set_table_data("website_settings", [{"version": 1, "data": disabled}])
        resp = unauth_client.get("/", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "<h1>" not in resp.text


class TestSectionAndProductStripping:
    def test_hidden_section_stripped(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        data = website_defaults_dict()
        data["sections"]["pricing"] = False
        mock_sb.set_table_data("website_settings", [{"version": 1, "data": data}])
        resp = unauth_client.get("/", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "PRICING_BLOCK" not in resp.text

    def test_visible_section_kept(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        data = website_defaults_dict()
        data["sections"]["pricing"] = True
        mock_sb.set_table_data("website_settings", [{"version": 1, "data": data}])
        resp = unauth_client.get("/", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "PRICING_BLOCK" in resp.text

    def test_hidden_product_card_stripped(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])  # hidden-product visible=False by default
        resp = unauth_client.get("/", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "HIDDEN_CARD" not in resp.text
        assert "ERP_CARD" in resp.text

    def test_hidden_product_route_is_404(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/produtos/hidden-product", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 404


class TestSettingsInjection:
    def test_settings_json_injected_and_escaped(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        data = website_defaults_dict()
        data["faq"] = [{"q": {"pt": "</script><script>alert(1)</script>", "en": "q"}, "a": {"pt": "a", "en": "a"}}]
        mock_sb.set_table_data("website_settings", [{"version": 1, "data": data}])
        resp = unauth_client.get("/", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "__NX_SETTINGS__" not in resp.text
        assert "</script><script>alert(1)</script>" not in resp.text
        # Every literal `<` becomes `\u003c` (JSON-string escape, not HTML
        # entity — see `_inject_settings` docstring); `>` is left alone.
        assert "\\u003c/script>\\u003cscript>alert(1)\\u003c/script>" in resp.text


class TestGeneratedSurfaces:
    def test_sitemap_xml(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/sitemap.xml", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "noctusai.com/produtos/erp-imobiliario" in resp.text
        assert "hidden-product" not in resp.text

    def test_robots_txt(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/robots.txt", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "Disallow: /api/" in resp.text

    def test_llms_txt(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/llms.txt", headers={"Host": WEBSITE_HOST})
        assert resp.status_code == 200
        assert "NoctusAI" in resp.text


class TestAppPathRedirect:
    def test_unknown_app_path_301s_to_core(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/login", headers={"Host": WEBSITE_HOST}, follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == "https://core.noctusai.com/login"

    def test_website_shaped_typo_is_website_404_not_app_redirect(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/produtos/does-not-exist", headers={"Host": WEBSITE_HOST}, follow_redirects=False)
        assert resp.status_code == 404
