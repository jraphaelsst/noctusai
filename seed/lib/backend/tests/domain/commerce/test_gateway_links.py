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
