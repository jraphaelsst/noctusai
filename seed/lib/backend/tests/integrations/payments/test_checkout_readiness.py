"""`check_checkout_readiness` — Asaas site prerequisite, Stripe, Fake. MockTransport, no network."""
from __future__ import annotations

from typing import Any, Callable

import httpx

from noctusai_lib.integrations.payments.checkout import (
    AsaasHostedCheckout,
    FakeHostedCheckout,
    ReadinessIssue,
    make_hosted_checkout,
    readiness_ok,
)
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.fake import FakePaymentGateway
from noctusai_lib.integrations.payments.real_asaas import AsaasPaymentGateway

URL = "https://store.noctusai.com/obrigado"


def _asaas(routes: dict[str, Callable[[httpx.Request], httpx.Response]]) -> AsaasHostedCheckout:
    def handler(request: httpx.Request) -> httpx.Response:
        route = routes.get(f"{request.method} {request.url.path}")
        if route is None:
            return httpx.Response(404, json={"errors": [{"description": "no route"}]})
        return route(request)

    return make_hosted_checkout(  # type: ignore[return-value]
        provider="asaas", asaas_api_key="k", asaas_transport=httpx.MockTransport(handler)
    )


def _ok(body: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _r: httpx.Response(200, json=body)


def _err(status: int, code: str, desc: str) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _r: httpx.Response(status, json={"errors": [{"code": code, "description": desc}]})


def test_asaas_missing_site_is_an_error() -> None:
    co = _asaas({"GET /v3/customers": _ok({"data": []}), "GET /v3/myAccount/commercialInfo": _ok({"site": None})})
    issues = co.check_checkout_readiness(URL)
    assert [i.code for i in issues] == ["missing_site"]
    assert "Minha Conta › Informações › Site" in issues[0].message
    assert not readiness_ok(issues)


def test_asaas_blank_site_counts_as_missing() -> None:
    co = _asaas({"GET /v3/customers": _ok({"data": []}), "GET /v3/myAccount/commercialInfo": _ok({"site": "  "})})
    assert [i.code for i in co.check_checkout_readiness(URL)] == ["missing_site"]


def test_asaas_site_set_reports_info_only_and_passes() -> None:
    co = _asaas(
        {"GET /v3/customers": _ok({"data": []}), "GET /v3/myAccount/commercialInfo": _ok({"site": "https://x.com"})}
    )
    issues = co.check_checkout_readiness(URL)
    assert [(i.code, i.severity) for i in issues] == [("site_registered", "info")]
    assert "https://x.com" in issues[0].message
    assert readiness_ok(issues)


def test_asaas_site_set_without_success_url_is_clean() -> None:
    co = _asaas(
        {"GET /v3/customers": _ok({"data": []}), "GET /v3/myAccount/commercialInfo": _ok({"site": "https://x.com"})}
    )
    assert co.check_checkout_readiness(None) == []


def test_asaas_bad_key_401_stops_before_commercial_info() -> None:
    seen: list[str] = []

    def commercial(_r: httpx.Request) -> httpx.Response:
        seen.append("commercial")
        return httpx.Response(200, json={"site": None})

    co = _asaas(
        {
            "GET /v3/customers": _err(401, "invalid_environment", "wrong env"),
            "GET /v3/myAccount/commercialInfo": commercial,
        }
    )
    issues = co.check_checkout_readiness(URL)
    assert [i.code for i in issues] == ["invalid_credentials"]
    assert "outro ambiente (sandbox x produção)" in issues[0].message
    assert seen == []


def test_asaas_5xx_is_gateway_unreachable_not_bad_key() -> None:
    co = _asaas({"GET /v3/customers": _err(503, "x", "down")})
    assert [i.code for i in co.check_checkout_readiness(URL)] == ["gateway_unreachable"]


def test_asaas_commercial_info_failure_is_reported() -> None:
    co = _asaas(
        {"GET /v3/customers": _ok({"data": []}), "GET /v3/myAccount/commercialInfo": _err(403, "denied", "sem permissão")}
    )
    issues = co.check_checkout_readiness(URL)
    assert [i.code for i in issues] == ["commercial_info_unavailable"]
    assert "sem permissão" in issues[0].message


def test_stripe_credentials_only() -> None:
    from noctusai_lib.integrations.payments.checkout import StripeHostedCheckout

    gw = FakePaymentGateway()
    co = StripeHostedCheckout(gw)  # type: ignore[arg-type]  # Fake gateway is the DI seam
    assert co.check_checkout_readiness(URL) == []
    gw.fail_credentials(PaymentGatewayError("stripe", "No such key", status=401))
    issues = co.check_checkout_readiness(URL)
    assert [i.code for i in issues] == ["invalid_credentials"]


def test_fake_is_scriptable_and_records_calls() -> None:
    fake = FakeHostedCheckout()
    assert fake.check_checkout_readiness(URL) == []
    fake.script_readiness([ReadinessIssue("missing_site", "x")])
    assert [i.code for i in fake.check_checkout_readiness(None)] == ["missing_site"]
    assert fake.calls == [("check_checkout_readiness", URL), ("check_checkout_readiness", None)]


def test_asaas_gateway_get_commercial_info_returns_body() -> None:
    gw = AsaasPaymentGateway(
        api_key="k",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"site": "s"})),
    )
    assert gw.get_commercial_info() == {"site": "s"}
