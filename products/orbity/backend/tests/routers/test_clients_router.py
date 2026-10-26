"""
Auth-boundary tests for the /api/clients router.

Every protected endpoint MUST return exactly 401 (not 404/422) when
called without a valid auth token. Strict == 401 per KB § PATTERNS/
compliance/auth-boundary-false-green.md.

The public capture endpoint is tested separately (test_crm_router.py).
"""
import pytest

from tests.routers.test_financial_router import make_admin
from noctusai_lib.testing import handler_status


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
        assert handler_status(resp) == 502 and "manualmente" in resp.text


class TestClientDelete:
    """Soft delete: admin-only, 404 for an unknown client, 409 with a live contract; the row is stamped, never removed."""

    ORG = "00000000-0000-0000-0000-00000000c0de"

    def _seed(self, client, *, contracts=()):
        from app.dependencies import coerce_org_uuid

        org = str(coerce_org_uuid("test-org-123"))
        client.mock_supabase.set_table_data("clients", [
            {"id": CID, "org_id": org, "name": "ACME", "legal_name": "ACME LTDA", "active": True, "deleted_at": None}])
        client.mock_supabase.set_table_data("ctr_contracts", [
            {"id": "k1", "org_id": org, "party_id": CID, "title": "Retainer", "status": s} for s in contracts])
        client.mock_supabase.set_table_data("fin_entries", [])
        client.mock_supabase.set_table_data("billing_charges", [])

    def test_delete_without_auth_is_401(self, client):
        assert client.raw().delete(f"/api/clients/{CID}").status_code == 401

    def test_plain_staff_cannot_delete(self, client):
        assert client.delete(f"/api/clients/{CID}").status_code == 403

    def test_an_unknown_client_is_404(self, client):
        make_admin(client)
        client.mock_supabase.set_table_data("clients", [])
        assert client.delete(f"/api/clients/{CID}").status_code == 404

    def test_an_already_deleted_client_is_404(self, client):
        make_admin(client)
        self._seed(client)
        client.mock_supabase.set_table_data("clients", [
            {"id": CID, "org_id": str(__import__("app.dependencies", fromlist=["x"]).coerce_org_uuid("test-org-123")),
             "name": "ACME", "active": True, "deleted_at": "2026-10-01T00:00:00+00:00"}])
        assert client.delete(f"/api/clients/{CID}").status_code == 404

    def test_a_clean_client_is_soft_deleted_not_removed(self, client):
        make_admin(client)
        self._seed(client)
        resp = client.delete(f"/api/clients/{CID}")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"ok": True, "id": CID}
        patch = client.mock_supabase.table("clients").updated_payloads[-1]
        assert patch["deleted_at"] and "deleted_by" in patch

    def test_an_active_contract_blocks_with_409_and_a_typed_code(self, client):
        make_admin(client)
        self._seed(client, contracts=["active"])
        resp = client.delete(f"/api/clients/{CID}")
        assert resp.status_code == 409, resp.text
        body = resp.json()  # the seed's flat machine-code shape: {"detail", "code", ...}
        assert body["code"] == "cliente_com_pendencias" and body["contracts"] == 1
        assert "contrato" in body["detail"]
        assert client.mock_supabase.table("clients").updated_payloads == []

    def test_an_ended_contract_does_not_block(self, client):
        make_admin(client)
        self._seed(client, contracts=["terminated"])
        assert client.delete(f"/api/clients/{CID}").status_code == 200
