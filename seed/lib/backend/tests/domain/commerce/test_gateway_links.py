"""Real Asaas gateway adapter (httpx.MockTransport) and the signed e-mail links."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from noctusai_lib.domain.commerce import AsaasCheckoutGateway, CommerceError, FakeCheckoutGateway, GatewayNotConfigured, make_checkout_gateway
from noctusai_lib.domain.commerce import access_links as links

from .conftest import CFG, ORG_A, ORG_B


def resolver(values):
    return lambda key, org_id=None: values.get((key, org_id)) or values.get((key, None))


def gw(values, handler=None):
    transport = httpx.MockTransport(handler or (lambda r: httpx.Response(404)))
    return AsaasCheckoutGateway(CFG, resolver=resolver(values), transport=transport)


class TestAsaas:
    def test_no_key_means_not_configured(self):
        with pytest.raises(GatewayNotConfigured):
            gw({}).hosted_checkout(ORG_A)

    def test_key_builds_a_hosted_checkout(self):
        assert gw({("asaas_api_key", ORG_A): "k"}).hosted_checkout(ORG_A).name.value == "asaas"

    def test_wallet_is_platform_tier_never_a_clients(self):
        g = gw({(CFG.platform_wallet_credential, None): "wal-noc"})
        assert g.platform_wallet_id() == "wal-noc"
        assert gw({}).platform_wallet_id() is None

    def test_webhook_token_is_per_org(self):
        g = gw({("asaas_webhook_token", ORG_A): "ta", ("asaas_webhook_token", ORG_B): "tb"})
        assert (g.webhook_token(ORG_A), g.webhook_token(ORG_B)) == ("ta", "tb")

    def test_customer_data_is_normalised(self):
        def handler(request):
            assert request.url.path.endswith("/customers/cus_1") and request.headers["access_token"] == "k"
            return httpx.Response(200, json={"name": "Ana", "cpfCnpj": "529.982.247-25", "email": "a@x.io",
                                             "mobilePhone": "(11) 98888-7777", "address": "Rua A", "addressNumber": "10",
                                             "province": "Centro", "postalCode": "01001000"})

        data = gw({("asaas_api_key", ORG_A): "k"}, handler).customer_data(ORG_A, "cus_1")
        assert data == {"name": "Ana", "doc": "52998224725", "email": "a@x.io", "phone": "11988887777",
                        "address": {"street": "Rua A", "number": "10", "district": "Centro", "zip": "01001000"}}

    def test_customer_data_failure_is_none_not_a_raise(self):
        assert gw({("asaas_api_key", ORG_A): "k"}, lambda r: httpx.Response(500, json={})).customer_data(ORG_A, "c") is None

    def test_factory(self):
        assert isinstance(make_checkout_gateway(CFG, use_fake=True), FakeCheckoutGateway)
        assert isinstance(make_checkout_gateway(CFG), AsaasCheckoutGateway)


class TestAsaasEnvironment:
    """Each org's key belongs to ONE Asaas environment; the gateway calls that environment's
    API root. Unset => sandbox (never real money by accident); garbage => refused."""

    def _host(self, values):
        hosts = []

        def handler(request):
            hosts.append(request.url.host)
            return httpx.Response(200, json={"name": "Ana"})

        gw({("asaas_api_key", ORG_A): "k", **values}, handler).customer_data(ORG_A, "cus_1")
        return hosts

    def test_unset_environment_is_sandbox(self):
        assert gw({}).environment(ORG_A) == "sandbox"
        assert self._host({}) == ["api-sandbox.asaas.com"]

    def test_production_is_an_explicit_per_org_choice(self):
        values = {("asaas_environment", ORG_A): "production"}
        assert gw(values).environment(ORG_A) == "production" and gw(values).environment(ORG_B) == "sandbox"
        assert self._host(values) == ["api.asaas.com"]

    def test_choice_is_normalised(self):
        assert gw({("asaas_environment", ORG_A): " Production "}).environment(ORG_A) == "production"

    def test_unknown_environment_refuses_instead_of_guessing(self):
        g = gw({("asaas_api_key", ORG_A): "k", ("asaas_environment", ORG_A): "prod"})
        with pytest.raises(GatewayNotConfigured):
            g.hosted_checkout(ORG_A)
        assert g.customer_data(ORG_A, "c") is None  # enrichment degrades, logged

    def test_hosted_checkout_targets_the_orgs_environment(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, json={"object": "account", "site": "https://loja.test"})

        g = gw({("asaas_api_key", ORG_A): "k", ("asaas_environment", ORG_A): "production"}, handler)
        g.hosted_checkout(ORG_A).check_checkout_readiness()
        assert seen and all(u.startswith("https://api.asaas.com/v3/") for u in seen)

    def test_config_refuses_an_unknown_default(self):
        from noctusai_lib.domain.commerce import CommerceConfig

        with pytest.raises(ValueError):
            CommerceConfig(schema="x", asaas_default_environment="prod")


class TestReadinessProbe:
    """`probe_api_key_readiness` -- the settings page's "Testar", lifted from the store/commerce copies."""

    def _probe(self, gateway, key="$aact_x", org=ORG_A):
        from noctusai_lib.domain.commerce import probe_api_key_readiness

        from .conftest import run

        return run(probe_api_key_readiness(gateway, CFG, org_id=org, api_key=key, public_url="https://loja.test/"))

    def test_ready_and_the_return_url_is_the_order_page(self):
        from noctusai_lib.domain.commerce import order_return_url
        from noctusai_lib.integrations.payments.checkout import READINESS_READY_MESSAGE

        fake = FakeCheckoutGateway()
        v = self._probe(fake)
        assert v.success is True and v.message == READINESS_READY_MESSAGE
        assert fake.checkout.calls == [("check_checkout_readiness", "https://loja.test/pedido")]
        assert order_return_url(CFG, "https://loja.test/") == "https://loja.test/pedido"

    def test_info_only_is_ready_with_the_info_and_error_is_not(self):
        from noctusai_lib.integrations.payments.checkout import ReadinessIssue

        fake = FakeCheckoutGateway()
        fake.checkout.script_readiness([ReadinessIssue("site_registered", "Site: x", severity="info")])
        v = self._probe(fake)
        assert v.success is True and v.message.endswith("Site: x")
        fake.checkout.script_readiness([ReadinessIssue("missing_site", "Cadastre o site.")])
        assert self._probe(fake) == type(v)(False, "Cadastre o site.")

    def test_typed_key_runs_in_the_orgs_environment(self):
        seen = []

        def handler(request):
            seen.append((request.url.host, request.headers.get("access_token")))
            return httpx.Response(401, json={"errors": [{"code": "invalid_environment", "description": "x"}]})

        g = gw({("asaas_environment", ORG_A): "production"}, handler)
        v = self._probe(g, key="$aact_typed")
        assert v.success is False and "ambiente" in v.message
        assert seen[0] == ("api.asaas.com", "$aact_typed")

    def test_unknown_environment_is_a_failed_verdict_not_a_raise(self):
        v = self._probe(gw({("asaas_environment", ORG_A): "prod"}))
        assert v.success is False and "Ambiente do Asaas" in v.message

    def test_gateway_error_is_a_failed_verdict_not_a_raise(self):
        from noctusai_lib.integrations.payments.errors import PaymentGatewayError

        class Boom:
            def check_checkout_readiness(self, success_url=None):
                raise PaymentGatewayError("asaas", "down", retryable=True)

        fake = FakeCheckoutGateway(checkout=Boom())
        v = self._probe(fake)
        assert v.success is False and "down" in v.message


class TestLinks:
    NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)

    def tok(self, **kw):
        base = dict(purpose="my_orders", org_id=ORG_A, subject="c1", ttl_minutes=10, at=self.NOW)
        base.update(kw)
        return links.sign_token("s3cret", **base)

    def test_roundtrip(self):
        claim = links.verify_token("s3cret", self.tok(), purpose="my_orders", org_id=ORG_A, at=self.NOW)
        assert claim["s"] == "c1"

    @pytest.mark.parametrize("mutate", ["expired", "purpose", "org", "secret", "tamper", "garbage"])
    def test_rejections_are_400_link_invalido(self, mutate):
        token, kw = self.tok(), dict(purpose="my_orders", org_id=ORG_A, at=self.NOW)
        secret = "s3cret"
        if mutate == "expired":
            kw["at"] = self.NOW + timedelta(minutes=11)
        elif mutate == "purpose":
            kw["purpose"] = "privacy_verify"
        elif mutate == "org":
            kw["org_id"] = ORG_B
        elif mutate == "secret":
            secret = "other"
        elif mutate == "tamper":
            token = "A" + token[1:]
        else:
            token = "nope"
        with pytest.raises(CommerceError) as exc:
            links.verify_token(secret, token, **kw)
        assert exc.value.code == "link_invalido" and exc.value.status_code == 400

    def test_no_secret_cannot_sign(self):
        with pytest.raises(CommerceError):
            links.sign_token("", purpose="x", org_id=ORG_A, subject="c", ttl_minutes=1)
