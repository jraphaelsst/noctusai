"""The commerce organ, mounted: migration parity, route contract (401 / 404 / 401), key specs.

Pins (a) `migrations/012_commerce.sql` is exactly what `commerce_migration` emits for
`app/commerce.py`'s config, (b) every staff route is strictly 401 without auth, (c) the
public storefront 404s an unknown Host, (d) the payment webhook is fail-closed (strict 401
on a wrong token, 404 on an unknown gateway), (e) the managed-key specs carry the names the
organ's gateway resolves. Collaborators are swapped through FastAPI `dependency_overrides`
(the DI seam) -- nothing is patched.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.domain.commerce import (
    COMMERCE_TABLES,
    MEDIA_UPLOAD_PATH_PATTERN,
    FakeCheckoutGateway,
    commerce_migration,
)

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "012_commerce.sql"
UUID0 = "11111111-1111-1111-1111-111111111111"


def test_migration_012_is_the_generators_output():
    from app.commerce import generate_migration

    assert MIGRATION.read_text(encoding="utf-8") == generate_migration(), (
        "012_commerce.sql drifted from noctusai_lib.domain.commerce.commerce_migration -- "
        "regenerate it (see app/commerce.py); never hand-edit a generated migration"
    )


def test_migration_covers_every_organ_table_and_the_credentials_table():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in COMMERCE_TABLES:
        assert f"commerce.{table}" in sql
    assert "commerce.credentials" in sql
    assert sql == commerce_migration(__import__("app.commerce", fromlist=["CFG"]).CFG, "commerce")


def test_api_key_specs_use_the_names_the_organ_gateway_resolves():
    from app.api_keys import API_KEY_SPECS
    from app.commerce import CFG

    names = {s.name: s for s in API_KEY_SPECS}
    assert set(names) == {CFG.asaas_api_key_name, CFG.asaas_webhook_token_name, CFG.asaas_environment_name}
    assert names[CFG.asaas_api_key_name].testable is True
    assert names[CFG.asaas_api_key_name].is_secret and names[CFG.asaas_webhook_token_name].is_secret


def test_asaas_environment_is_a_choice_defaulting_to_sandbox():
    from noctusai_lib.integrations.payments.real_asaas import ASAAS_BASE_URLS

    from app.api_keys import API_KEY_SPECS
    from app.commerce import CFG

    env = next(s for s in API_KEY_SPECS if s.name == CFG.asaas_environment_name)
    assert env.is_secret is False
    assert set(env.allowed_values) == set(ASAAS_BASE_URLS)  # every option maps to an API root
    assert env.default == CFG.asaas_default_environment == "sandbox"


def test_config_uses_the_organs_org_picker_aware_default():
    from app.commerce import CFG

    assert CFG.org_id_expr == "public.current_org_id_for('commerce')"


STAFF_ROUTES = [
    ("GET", "/api/commerce/profile"), ("PUT", "/api/commerce/profile"),
    ("GET", "/api/commerce/products"), ("POST", "/api/commerce/products"),
    ("GET", f"/api/commerce/products/{UUID0}"), ("POST", f"/api/commerce/products/{UUID0}/media"),
    ("GET", "/api/commerce/orders"), ("GET", "/api/commerce/customers"), ("GET", "/api/commerce/coupons"),
    ("GET", "/api/commerce/hosts"), ("POST", "/api/commerce/hosts"),
    ("GET", "/api/settings/api-keys"),
]


@pytest.mark.parametrize("method,path", STAFF_ROUTES)
def test_staff_and_key_routes_are_401_without_auth(client, method, path):
    assert client.raw().request(method, path).status_code == 401  # strict ==


def test_media_upload_route_is_mounted_where_the_body_override_pattern_points(client):
    from app.main import app

    pattern = re.compile("^" + re.escape(MEDIA_UPLOAD_PATH_PATTERN).replace(r"\*", r"[^/]+") + "$")
    assert any(pattern.match(re.sub(r"\{[^}]+\}", "x", r.path)) for r in app.routes if hasattr(r, "methods") and "POST" in r.methods)


def test_storefront_unknown_host_is_404(client):
    resp = client.raw().get("/api/storefront/catalog", headers={"host": "nobody.example.test"})
    assert resp.status_code == 404


class TestPaymentWebhook:
    @pytest.fixture
    def gateway(self, client):
        from app import commerce_deps
        from app.main import app

        gw = FakeCheckoutGateway(webhook_secret="hook-token")
        app.dependency_overrides[commerce_deps.get_gateway] = lambda: gw
        yield gw
        app.dependency_overrides.pop(commerce_deps.get_gateway, None)

    def test_wrong_token_is_401(self, client, gateway):
        resp = client.raw().post(
            f"/api/webhooks/payments/{gateway.name}/{UUID0}",
            json={"event": "PAYMENT_RECEIVED"},
            headers={"asaas-access-token": "wrong"},
        )
        assert resp.status_code == 401

    def test_missing_token_is_401(self, client, gateway):
        resp = client.raw().post(f"/api/webhooks/payments/{gateway.name}/{UUID0}", json={"event": "PAYMENT_RECEIVED"})
        assert resp.status_code == 401

    def test_unknown_gateway_is_404(self, client, gateway):
        resp = client.raw().post(f"/api/webhooks/payments/nope/{UUID0}", json={})
        assert resp.status_code == 404


class TestReadinessProbe:
    """The host adapter over the organ's `probe_api_key_readiness` (the probe lives in the seed)."""

    def _run(self, gateway, value="$aact_fake", org=UUID0):
        import asyncio

        from app.key_testers import make_asaas_key_tester

        return asyncio.run(make_asaas_key_tester(lambda: gateway)(value, org))

    def test_ready_account_is_success(self):
        from noctusai_lib.integrations.payments.checkout import READINESS_READY_MESSAGE

        result = self._run(FakeCheckoutGateway())
        assert result.key == "asaas_api_key"
        assert result.success is True and result.message == READINESS_READY_MESSAGE

    def test_missing_site_is_failure_with_the_issue_line(self):
        from noctusai_lib.integrations.payments.checkout import FakeHostedCheckout, ReadinessIssue

        checkout = FakeHostedCheckout()
        checkout.script_readiness([ReadinessIssue("missing_site", "Cadastre o site da loja no Asaas.")])
        result = self._run(FakeCheckoutGateway(checkout=checkout))
        assert result.success is False and result.message == "Cadastre o site da loja no Asaas."
        assert checkout.calls == [("check_checkout_readiness", "https://commerce.noctusai.com/pedido")]

    def test_the_settings_router_registers_it_as_an_org_tester(self, client):
        # Mounted: the probe route exists and is auth-gated (strict 401).
        assert client.raw().post("/api/settings/api-keys/asaas_api_key/test").status_code == 401
