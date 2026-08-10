"""
Tests for the product WORKING-GUIDE axes.

POST /api/products/{id}/activation     — status  (ativo / inativo)
POST /api/products/{id}/deploy-scope   — scope   (live / dev)

The contract under test:

    ativo + live → work it in PROD
    ativo + dev  → work it in DEV only
    inativo      → do not touch the product at all

and the two invariants that keep the guide from drifting into a state the
rules forbid:

    I1. An inactive product can never be live.
    I2. A reactivated product always lands in dev.

Both are asserted on the OBSERVABLE write (what actually gets persisted),
not merely on the response code — a 200 that wrote the wrong scope is the
exact failure this feature exists to prevent.
"""
import pytest


def _product(**over):
    row = {
        "id": "prod-1",
        "nome": "ERP Imobiliario",
        "slug": "erp-imobiliario",
        "url_base": "http://localhost:8001",
        "ativo": True,
        "deploy_scope": "live",
    }
    row.update(over)
    return row


# ---------------------------------------------------------------------------
# POST /api/products/{id}/activation
# ---------------------------------------------------------------------------

class TestActivation:
    def test_deactivate_also_demotes_scope_to_dev(self, admin_client):
        """I1: deactivating a LIVE product must not leave it marked live."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product(ativo=True, deploy_scope="live"))

        resp = admin_client.post("/api/products/prod-1/activation", json={"ativo": False})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ativo"] is False
        # The whole point: the scope came down in the SAME write.
        assert data["deploy_scope"] == "dev"

    def test_reactivate_lands_in_dev_not_live(self, admin_client):
        """I2: a product returning from inactive has not been re-validated."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product(ativo=False, deploy_scope="dev"))

        resp = admin_client.post("/api/products/prod-1/activation", json={"ativo": True})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ativo"] is True
        assert data["deploy_scope"] == "dev"

    def test_delete_endpoint_shares_the_same_transition(self, admin_client):
        """DELETE is a legacy alias — it must not drift from the helper."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product(ativo=True, deploy_scope="live"))

        resp = admin_client.delete("/api/products/prod-1")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ativo"] is False
        assert data["deploy_scope"] == "dev"

    def test_activation_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", None)

        resp = admin_client.post("/api/products/nope/activation", json={"ativo": False})
        assert resp.status_code == 404

    def test_activation_requires_admin(self, client):
        resp = client.post("/api/products/prod-1/activation", json={"ativo": False})
        assert resp.status_code == 403

    def test_activation_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/products/prod-1/activation", json={"ativo": False})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/products/{id}/deploy-scope
# ---------------------------------------------------------------------------

class TestDeployScope:
    def test_promote_active_product_to_live(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product(ativo=True, deploy_scope="dev"))

        resp = admin_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "live"}
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["deploy_scope"] == "live"

    def test_demote_active_product_to_dev(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product(ativo=True, deploy_scope="live"))

        resp = admin_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "dev"}
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["deploy_scope"] == "dev"

    def test_inactive_product_refused_live_with_409(self, admin_client):
        """I1 as an explainable refusal, not an opaque DB constraint 500."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product(ativo=False, deploy_scope="dev"))

        resp = admin_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "live"}
        )

        assert resp.status_code == 409
        # The seed's http_exception_handler renders a string detail into the
        # `{"error": {code, message}}` envelope — assert the message the
        # operator actually sees, not a raw `detail` key that never ships.
        assert "inativo" in resp.json()["error"]["message"].lower()

    def test_inactive_product_may_still_be_set_dev(self, admin_client):
        """Only the LIVE direction is forbidden — dev is already its state."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product(ativo=False, deploy_scope="dev"))

        resp = admin_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "dev"}
        )
        assert resp.status_code == 200

    def test_rejects_unknown_scope_value(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product())

        resp = admin_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "staging"}
        )
        assert resp.status_code == 422

    def test_deploy_scope_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", None)

        resp = admin_client.post(
            "/api/products/nope/deploy-scope", json={"deploy_scope": "dev"}
        )
        assert resp.status_code == 404

    def test_deploy_scope_requires_admin(self, client):
        resp = client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "live"}
        )
        assert resp.status_code == 403

    def test_deploy_scope_unauthenticated(self, unauth_client):
        resp = unauth_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "live"}
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH must NOT be a back door around the transition rules
# ---------------------------------------------------------------------------

class TestGuideChangesAreAudited:
    """A working-guide change decides which products the team touches, so
    "who moved this, and from what?" must be answerable afterwards.

    The audit call is patched at its use site so these assert the CONTRACT
    (it is called, with the before/after states) without needing a real
    audit_logs table.
    """

    @staticmethod
    def _patch_audit(monkeypatch):
        calls = []

        async def _fake_log(**kwargs):
            calls.append(kwargs)
            return {}

        import app.routers.products as products_router
        monkeypatch.setattr(products_router.audit_service, "log", _fake_log)
        return calls

    def test_deactivation_records_the_scope_it_was_demoted_from(
        self, admin_client, monkeypatch
    ):
        calls = self._patch_audit(monkeypatch)
        admin_client.mock_supabase.set_table_data(
            "products", _product(ativo=True, deploy_scope="live")
        )

        resp = admin_client.post("/api/products/prod-1/activation", json={"ativo": False})
        assert resp.status_code == 200

        assert len(calls) == 1
        entry = calls[0]
        assert entry["action"] == "product.deactivated"
        assert entry["resource_type"] == "product"
        # The point of the entry: it was LIVE before, dev after.
        assert entry["details"]["before"] == {"ativo": True, "deploy_scope": "live"}
        assert entry["details"]["after"]["deploy_scope"] == "dev"
        assert entry["details"]["after"]["ativo"] is False

    def test_activation_is_audited(self, admin_client, monkeypatch):
        calls = self._patch_audit(monkeypatch)
        admin_client.mock_supabase.set_table_data(
            "products", _product(ativo=False, deploy_scope="dev")
        )

        resp = admin_client.post("/api/products/prod-1/activation", json={"ativo": True})
        assert resp.status_code == 200
        assert calls and calls[0]["action"] == "product.activated"

    def test_deploy_scope_change_is_audited(self, admin_client, monkeypatch):
        calls = self._patch_audit(monkeypatch)
        admin_client.mock_supabase.set_table_data(
            "products", _product(ativo=True, deploy_scope="dev")
        )

        resp = admin_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "live"}
        )
        assert resp.status_code == 200
        assert calls and calls[0]["action"] == "product.deploy_scope_changed"
        assert calls[0]["details"]["before"]["deploy_scope"] == "dev"
        assert calls[0]["details"]["after"]["deploy_scope"] == "live"

    def test_refused_scope_change_is_not_audited(self, admin_client, monkeypatch):
        """A 409 changed nothing, so it must not leave a trail suggesting it did."""
        calls = self._patch_audit(monkeypatch)
        admin_client.mock_supabase.set_table_data(
            "products", _product(ativo=False, deploy_scope="dev")
        )

        resp = admin_client.post(
            "/api/products/prod-1/deploy-scope", json={"deploy_scope": "live"}
        )
        assert resp.status_code == 409
        assert calls == []

    def test_audit_failure_does_not_break_the_transition(
        self, admin_client, monkeypatch
    ):
        """The operator already saw the toggle flip; a logging fault must not
        retroactively fail it. It is logged loudly instead."""
        async def _boom(**kwargs):
            raise RuntimeError("audit backend down")

        import app.routers.products as products_router
        monkeypatch.setattr(products_router.audit_service, "log", _boom)
        admin_client.mock_supabase.set_table_data(
            "products", _product(ativo=True, deploy_scope="live")
        )

        resp = admin_client.post("/api/products/prod-1/activation", json={"ativo": False})
        assert resp.status_code == 200
        assert resp.json()["data"]["deploy_scope"] == "dev"


class TestPatchCannotBypassTheRules:
    @pytest.mark.parametrize("field,value", [
        ("ativo", False),
        ("deploy_scope", "live"),
    ])
    def test_patch_rejects_guide_fields(self, admin_client, field, value):
        """`StrictHttpModel` rejects unknown fields, so dropping `ativo` /
        `deploy_scope` from ProductUpdate is what makes the dedicated
        endpoints the ONLY path. If either silently reappeared on PATCH, the
        rules could be bypassed and this test is the thing that notices."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", _product())

        resp = admin_client.patch(f"/api/products/prod-1", json={field: value})
        assert resp.status_code == 422
