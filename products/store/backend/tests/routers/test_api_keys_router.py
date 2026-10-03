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

    def test_unset_org_is_503(self, keyed):
        from app.api_keys import key_provider

        key_provider.use(store=keyed.creds, resolver=lambda name, org: None, org_id="")
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

    def test_encryption_key_missing_writes_503_never_plaintext(self, client):
        from app.api_keys import key_provider
        from app.dependencies import get_store_admin_emails
        from app.main import app

        from tests.conftest import ADMIN_EMAIL

        # The case under test is "no ENCRYPTION_KEY": stated explicitly through the
        # provider's seam, so the verdict never depends on the machine's env. No
        # store override => the REAL store builder runs with no key.
        key_provider.use(org_id=ORG_ID, encryption_key="")
        app.dependency_overrides[get_store_admin_emails] = lambda: frozenset({ADMIN_EMAIL})
        try:
            as_admin(client)
            resp = _put(client, "asaas_api_key", "plain-text-secret")
        finally:
            app.dependency_overrides.pop(get_store_admin_emails, None)
            key_provider.reset()
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

        key_provider.use(store=keyed.creds, resolver=lambda name, org: "from-platform" if name == "asaas_api_key" else None, org_id=ORG_ID)
        assert key_provider.resolve("asaas_api_key") == "from-platform"
        as_admin(keyed.client)
        assert _put(keyed.client, "asaas_api_key", "local-wins").status_code == 200
        assert key_provider.resolve("asaas_api_key") == "local-wins"

    def test_smtp_resolves_through_the_platform_chain(self, keyed):
        from noctusai_lib.integrations.email import SmtpEmailSender

        from app import store_deps
        from app.api_keys import key_provider

        assert type(store_deps.get_email_sender(keyed.settings)).__name__ == "UnconfiguredEmailSender"
        platform = {"smtp_host": "smtp.x.test", "smtp_username": "u", "smtp_password": "p", "smtp_port": "587"}
        key_provider.use(store=keyed.creds, resolver=lambda name, org: platform.get(name), org_id=ORG_ID)
        assert isinstance(store_deps.get_email_sender(keyed.settings), SmtpEmailSender)

    def test_sender_name_is_the_product_name_over_the_platform_default(self, keyed):
        from app import store_deps
        from app.api_keys import key_provider
        from app.services.settings_service import DEFAULT_SETTINGS

        platform = {
            "smtp_host": "smtp.x.test", "smtp_username": "u", "smtp_password": "p", "smtp_port": "587",
            "email_from": "noreply@x.test", "email_from_name": "Plataforma",
        }
        key_provider.use(store=keyed.creds, resolver=lambda name, org: platform.get(name), org_id=ORG_ID)
        # Empty ledger -> the default product name (what the landing shows).
        assert store_deps.get_email_sender(keyed.settings).config.from_name == DEFAULT_SETTINGS["product_name"]
        # An edited product name is the sender; the address stays the platform's.
        keyed.settings.append(version=1, data={**DEFAULT_SETTINGS, "product_name": "Kit Contratos"}, created_by=None)
        sender = store_deps.get_email_sender(keyed.settings)
        assert (sender.config.from_name, sender.config.from_email) == ("Kit Contratos", "noreply@x.test")
        # No product name -> the platform default name applies.
        keyed.settings.append(version=2, data={**DEFAULT_SETTINGS, "product_name": ""}, created_by=None)
        assert store_deps.get_email_sender(keyed.settings).config.from_name == "Plataforma"


class TestTestarAsaasKey:
    """`POST .../asaas_api_key/test` — key + account readiness, via the seed hosted-checkout
    adapter over an httpx MockTransport (the Asaas HTTP boundary) injected through the probe's seam."""

    URL = f"{BASE}/asaas_api_key/test"

    @staticmethod
    def _asaas(keyed, routes):
        import httpx

        from app.key_testers import checkout_probe
        from noctusai_lib.integrations.payments.checkout import make_hosted_checkout

        seen = []

        def handler(request):
            seen.append((request.method, str(request.url), request.headers.get("access_token")))
            route = routes.get(f"{request.method} {request.url.path}")
            return route if route is not None else httpx.Response(404, json={"errors": [{"description": "x"}]})

        checkout_probe.use(
            factory=lambda key, base: make_hosted_checkout(
                provider="asaas", asaas_api_key=key, asaas_base_url=base,
                asaas_transport=httpx.MockTransport(handler),
            )
        )
        return seen

    def test_requires_token_401_and_admin_403(self, keyed):
        assert keyed.client.raw().post(self.URL).status_code == 401
        as_other_user(keyed.client)
        assert keyed.client.post(self.URL).status_code == 403

    def test_unconfigured_key_is_422(self, keyed):
        as_admin(keyed.client)
        assert keyed.client.post(self.URL).status_code == 422

    def test_ready_account_succeeds_with_environment_base_url(self, keyed):
        import httpx

        seen = self._asaas(keyed, {
            "GET /v3/customers": httpx.Response(200, json={"data": []}),
            "GET /v3/myAccount/commercialInfo": httpx.Response(200, json={"site": "https://store.noctusai.com"}),
        })
        as_admin(keyed.client)
        _put(keyed.client, "asaas_api_key", "$aact_key")
        body = keyed.client.post(self.URL).json()
        assert body["success"] is True and body["key"] == "asaas_api_key"
        assert body["message"].startswith("Chave válida e conta pronta para receber pagamentos.")
        assert all("sandbox" in url and tok == "$aact_key" for _m, url, tok in seen)
        assert "https://store.noctusai.com/obrigado" in body["message"]

    def test_missing_site_fails_with_the_actionable_message(self, keyed):
        import httpx

        self._asaas(keyed, {
            "GET /v3/customers": httpx.Response(200, json={"data": []}),
            "GET /v3/myAccount/commercialInfo": httpx.Response(200, json={"site": None}),
        })
        as_admin(keyed.client)
        _put(keyed.client, "asaas_api_key", "$aact_key")
        body = keyed.client.post(self.URL).json()
        assert body["success"] is False
        assert body["message"] == (
            "Cadastre o site da loja no Asaas: Minha Conta › Informações › Site — "
            "sem isso o Asaas recusa o redirecionamento pós-pagamento."
        )

    def test_bad_key_fails_with_environment_hint(self, keyed):
        import httpx

        self._asaas(keyed, {
            "GET /v3/customers": httpx.Response(
                401, json={"errors": [{"code": "invalid_environment", "description": "env"}]}
            ),
        })
        as_admin(keyed.client)
        _put(keyed.client, "asaas_api_key", "$aact_prodkey")
        body = keyed.client.post(self.URL).json()
        assert body["success"] is False
        assert "Chave inválida ou de outro ambiente (sandbox x produção)" in body["message"]

    def test_other_keys_have_no_tester_400(self, keyed):
        as_admin(keyed.client)
        _put(keyed.client, "asaas_webhook_token", "tok-123456")
        assert keyed.client.post(f"{BASE}/asaas_webhook_token/test").status_code == 400
