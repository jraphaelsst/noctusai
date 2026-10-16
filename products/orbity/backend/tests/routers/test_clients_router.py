"""
Auth-boundary tests for the /api/clients router.

Every protected endpoint MUST return exactly 401 (not 404/422) when
called without a valid auth token. Strict == 401 per KB § PATTERNS/
compliance/auth-boundary-false-green.md.

The public capture endpoint is tested separately (test_crm_router.py).
"""
import pytest

from tests.routers.test_financial_router import make_admin


CID = "c1000000-0000-4000-8000-000000000001"


class TestClientsRouterAuth:
    """Every /api/clients endpoint requires authentication."""

    def test_list_clients_without_auth_returns_401(self, client):
        resp = client.raw().get("/api/clients")
        assert resp.status_code == 401

    def test_create_client_without_auth_returns_401(self, client):
        resp = client.raw().post("/api/clients", json={"name": "x"})
        assert resp.status_code == 401

    def test_get_client_without_auth_returns_401(self, client):
        resp = client.raw().get("/api/clients/some-id")
        assert resp.status_code == 401

    def test_update_client_without_auth_returns_401(self, client):
        resp = client.raw().patch("/api/clients/some-id", json={"name": "x"})
        assert resp.status_code == 401

    def test_archive_client_without_auth_returns_401(self, client):
        resp = client.raw().post("/api/clients/some-id/archive")
        assert resp.status_code == 401

    def test_offboarding_preview_without_auth_returns_401(self, client):
        assert client.raw().get(f"/api/clients/{CID}/offboarding-preview").status_code == 401

    def test_cnpj_lookup_without_auth_returns_401(self, client):
        assert client.raw().get("/api/clients/cnpj/11222333000181").status_code == 401


class TestInactivation:
    """Inactivating moves money: org ADMINS only, and only through the operation that decides every open charge."""

    def test_plain_staff_cannot_archive(self, client):
        assert client.post(f"/api/clients/{CID}/archive", json={}).status_code == 403

    def test_plain_staff_cannot_preview_the_offboarding(self, client):
        assert client.get(f"/api/clients/{CID}/offboarding-preview").status_code == 403

    def test_patch_cannot_inactivate_around_the_dialog(self, client):
        resp = client.patch(f"/api/clients/{CID}", json={"active": False})
        assert resp.status_code == 409
        assert "archive" in resp.text

    def test_patch_can_still_reactivate(self, client):
        resp = client.patch(f"/api/clients/{CID}", json={"active": True})
        assert resp.status_code != 409

    def test_archive_body_rejects_unknown_actions_and_fields(self, client):
        make_admin(client)
        assert client.post(f"/api/clients/{CID}/archive", json={"charges": [{"entry_id": "e", "action": "maybe"}]}).status_code == 422
        assert client.post(f"/api/clients/{CID}/archive", json={"surprise": 1}).status_code == 422

    def test_an_admin_archiving_an_unknown_client_gets_404(self, client):
        make_admin(client)
        client.mock_supabase.set_table_data("clients", [])
        assert client.post(f"/api/clients/{CID}/archive", json={}).status_code == 404


class TestCnpjLookup:
    """The lookup collaborator is swapped through FastAPI's DI (``dependency_overrides``) -- nothing is patched."""

    URL = "/api/clients/cnpj/11222333000181"  # digits only: the client strips the mask

    @staticmethod
    def _using(lookup):
        from app.main import app
        from app.routers.clients_router import cnpj_lookup_dependency

        app.dependency_overrides[cnpj_lookup_dependency] = lambda: lookup
        return app

    def test_an_invalid_cnpj_is_422_before_any_lookup(self, client):
        assert client.get("/api/clients/cnpj/123").status_code == 422

    def test_a_valid_cnpj_answers_the_razao_social_from_the_registry(self, client):
        from datetime import date

        from noctusai_lib.integrations.cnpj_registry.fake import FakeCnpjRegistryLookup
        from noctusai_lib.integrations.cnpj_registry.types import CnpjRegistryFields

        fake = FakeCnpjRegistryLookup()
        fake.registrar("11222333000181", CnpjRegistryFields(
            cnpj="11222333000181", razao_social="ACME COMERCIO DE ALIMENTOS LTDA", situacao_cadastral="ativa",
            situacao_cadastral_bruta="ATIVA", data_situacao_cadastral=date(2010, 3, 15), source="fake"))
        app = self._using(fake)
        try:
            resp = client.get(self.URL)
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"cnpj": "11222333000181", "legal_name": "ACME COMERCIO DE ALIMENTOS LTDA", "situacao_cadastral": "ativa"}
        assert fake.chamadas == ["11222333000181"]

    def test_an_unknown_cnpj_is_404(self, client):
        from noctusai_lib.integrations.cnpj_registry.errors import CnpjNotFoundError
        from noctusai_lib.integrations.cnpj_registry.fake import FakeCnpjRegistryLookup

        app = self._using(FakeCnpjRegistryLookup(erro=CnpjNotFoundError("11222333000181", source="fake")))
        try:
            assert client.get(self.URL).status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_an_unreachable_registry_is_502_with_a_hint_to_type_it_manually(self, client):
        from noctusai_lib.integrations.cnpj_registry.errors import CnpjRegistryUpstreamError
        from noctusai_lib.integrations.cnpj_registry.fake import FakeCnpjRegistryLookup

        app = self._using(FakeCnpjRegistryLookup(erro=CnpjRegistryUpstreamError("brasilapi down")))
        try:
            resp = client.get(self.URL)
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 502 and "manualmente" in resp.text
