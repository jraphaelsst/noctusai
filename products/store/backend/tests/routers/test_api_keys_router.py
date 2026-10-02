"""Owner-managed keys: written through the seed router, stored encrypted-at-rest
(seed credential store), consumed by checkout + webhook via `resolve_api_key`."""
import json

from tests.conftest import ORG_ID, WEBHOOK_TOKEN, as_admin, as_other_user  # noqa: F401

BASE = "/api/settings/api-keys"
CPF = "529.982.247-25"


def _put(c, key, value):
    return c.put(f"{BASE}/{key}", json={"value": value})


class TestGate:
    def test_every_key_route_requires_a_token_401(self, keyed):
        raw = keyed.client.raw()
        assert raw.get(BASE).status_code == 401
        assert raw.put(f"{BASE}/asaas_api_key", json={"value": "x"}).status_code == 401
        assert raw.delete(f"{BASE}/asaas_api_key").status_code == 401

    def test_non_admin_gets_403_on_every_key_route(self, keyed):
        as_other_user(keyed.client)
        c = keyed.client
        assert c.get(BASE).status_code == 403
        assert _put(c, "asaas_api_key", "secret-value").status_code == 403
        assert c.delete(f"{BASE}/asaas_api_key").status_code == 403
        assert keyed.creds.get(ORG_ID, "api_key:asaas_api_key") is None

    def test_unset_org_is_503(self, keyed, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "store_org_id", "")  # self-patch-ok: configuration value, not a guard
        as_admin(keyed.client)
        assert keyed.client.get(BASE).status_code == 503


class TestRoutes:
    def test_list_shape_and_order(self, keyed):
        as_admin(keyed.client)
        resp = keyed.client.get(BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert [i["key"] for i in body["items"]] == ["asaas_api_key", "asaas_webhook_token", "asaas_environment"]
        env = body["items"][2]
        assert env["is_secret"] is False and env["default"] == "sandbox" and env["configured"] is False
        assert [o["value"] for o in env["options"]] == ["sandbox", "production"]
        assert all(i["configured"] is False and i["hint"] is None for i in body["items"][:2])

    def test_put_masks_value_and_never_echoes_it(self, keyed):
        as_admin(keyed.client)
        resp = _put(keyed.client, "asaas_api_key", "$aact_SUPERSECRET_b3f9")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True and body["source"] == "local" and body["hint"] == "...b3f9"
        assert "SUPERSECRET" not in resp.text
        assert "SUPERSECRET" not in keyed.client.get(BASE).text

    def test_non_secret_environment_is_shown_verbatim(self, keyed):
        as_admin(keyed.client)
        assert _put(keyed.client, "asaas_environment", "production").json()["hint"] == "production"

    def test_invalid_environment_422_and_unknown_key_404_and_blank_422(self, keyed):
        as_admin(keyed.client)
        assert _put(keyed.client, "asaas_environment", "staging").status_code == 422
        assert _put(keyed.client, "nope", "x").status_code == 404
        assert _put(keyed.client, "asaas_api_key", "   ").status_code == 422

    def test_delete_removes_local_override(self, keyed):
        as_admin(keyed.client)
        _put(keyed.client, "asaas_api_key", "abcdefgh")
        resp = keyed.client.delete(f"{BASE}/asaas_api_key")
        assert resp.status_code == 200 and resp.json()["configured"] is False

    def test_value_is_stored_under_the_owner_org(self, keyed):
        as_admin(keyed.client)
        _put(keyed.client, "asaas_webhook_token", "tok-123456")
        assert keyed.creds.get(ORG_ID, "api_key:asaas_webhook_token").tokens["value"] == "tok-123456"

    def test_encryption_key_missing_writes_503_never_plaintext(self, client, monkeypatch):
        from app.config import settings
        from app.api_keys import key_provider
        from app.dependencies import get_store_admin_emails
        from app.main import app

        from tests.conftest import ADMIN_EMAIL

        monkeypatch.setattr(settings, "store_org_id", ORG_ID)  # self-patch-ok: configuration value, not a guard
        key_provider.reset()  # the REAL store builder: ENCRYPTION_KEY is unset in tests
        app.dependency_overrides[get_store_admin_emails] = lambda: frozenset({ADMIN_EMAIL})
        try:
            as_admin(client)
            resp = _put(client, "asaas_api_key", "plain-text-secret")
        finally:
            app.dependency_overrides.pop(get_store_admin_emails, None)
        assert resp.status_code == 503
        assert "ENCRYPTION_KEY" in resp.json()["error"]["message"]


class TestConsumption:
    def _checkout(self, keyed):
        return keyed.client.raw().post(
            "/api/public/checkout", json={"nome": "Maria Souza", "email": "m@gmail.com", "cpf": CPF}
        )

    def test_checkout_503_until_the_key_is_written_then_uses_it(self, keyed):
        from noctusai_lib.integrations.payments.checkout import AsaasHostedCheckout

        assert self._checkout(keyed).status_code == 503
        assert keyed.pedidos.rows == {}

        as_admin(keyed.client)
        assert _put(keyed.client, "asaas_api_key", "$aact_key").status_code == 200

        from app import store_deps

        hosted = store_deps.build_hosted_checkout()
        assert isinstance(hosted, AsaasHostedCheckout)
        assert hosted._gateway._client.headers["access_token"] == "$aact_key"

    def test_environment_selects_the_base_url(self, keyed):
        from app.api_keys import key_provider

        assert "sandbox" in key_provider.asaas_base_url()  # unset => sandbox
        as_admin(keyed.client)
        _put(keyed.client, "asaas_environment", "production")
        assert key_provider.asaas_base_url() == "https://api.asaas.com/v3"
        _put(keyed.client, "asaas_environment", "sandbox")
        assert "sandbox" in key_provider.asaas_base_url()

    def test_webhook_token_comes_from_the_store(self, keyed):
        body = json.dumps({"id": "e1", "event": "PAYMENT_RECEIVED", "payment": {"id": "p", "externalReference": "x"}}).encode()
        post = lambda tok: keyed.client.raw().post(  # noqa: E731
            "/api/webhooks/asaas", content=body,
            headers={"asaas-access-token": tok, "content-type": "application/json"},
        )
        assert post("tok-store").status_code == 401  # nothing stored => fail closed

        as_admin(keyed.client)
        _put(keyed.client, "asaas_webhook_token", "tok-store")
        assert post("tok-store").status_code == 200
        assert post("wrong").status_code == 401

    def test_platform_chain_is_the_fallback_tier(self, keyed):
        from app.api_keys import key_provider

        key_provider.use(store=keyed.creds, resolver=lambda name, org: "from-platform" if name == "asaas_api_key" else None)
        assert key_provider.resolve("asaas_api_key") == "from-platform"
        as_admin(keyed.client)
        assert _put(keyed.client, "asaas_api_key", "local-wins").status_code == 200
        assert key_provider.resolve("asaas_api_key") == "local-wins"

    def test_smtp_resolves_through_the_platform_chain(self, keyed):
        from noctusai_lib.integrations.email import SmtpEmailSender

        from app import store_deps
        from app.api_keys import key_provider

        assert type(store_deps.get_email_sender()).__name__ == "UnconfiguredEmailSender"
        platform = {"smtp_host": "smtp.x.test", "smtp_username": "u", "smtp_password": "p", "smtp_port": "587"}
        key_provider.use(store=keyed.creds, resolver=lambda name, org: platform.get(name))
        assert isinstance(store_deps.get_email_sender(), SmtpEmailSender)
