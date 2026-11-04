"""``GrantDelivery`` — Fake records, Real speaks HTTP (httpx MockTransport), the
factory refuses the Fake in a deploy context."""
from __future__ import annotations

import httpx
import pytest

from noctusai_lib.api.auth.grants import (
    FakeGrantDelivery,
    GrantDeliveryError,
    GrantPayload,
    HttpGrantDelivery,
    make_grant_delivery,
)


def _real(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpGrantDelivery(client=client, db_url_bases={"social-wiring": "https://sw.example"})


def test_fake_records_put_and_delete_and_can_fail():
    fake = FakeGrantDelivery()
    fake.deliver("social-wiring", "agents", GrantPayload(credential="noc_abc12345"), delivery_token="t1")
    assert fake.revoke("social-wiring", "agents", delivery_token="t1") is True
    assert [(c.method, c.delivery_token) for c in fake.calls] == [("PUT", "t1"), ("DELETE", "t1")]
    fake.fail_deliver = True
    with pytest.raises(GrantDeliveryError):
        fake.deliver("social-wiring", "agents", GrantPayload(credential="x" * 8), delivery_token="t")


def test_real_puts_to_the_product_with_the_delivery_bearer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["url"] = request.method, str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.read()
        return httpx.Response(204)

    _real(handler).deliver(
        "social-wiring", "agents", GrantPayload(credential="noc_secret12", agent_id="a1"),
        delivery_token="noc_delivery",
    )
    assert seen["method"] == "PUT"
    assert seen["url"] == "https://sw.example/api/platform/grants/agents"
    assert seen["auth"] == "Bearer noc_delivery"
    assert b'"credential"' in seen["body"] and b"org_id" not in seen["body"]


def test_real_raises_on_refusal_and_on_transport_error():
    with pytest.raises(GrantDeliveryError) as exc:
        _real(lambda r: httpx.Response(403)).deliver(
            "social-wiring", "agents", GrantPayload(credential="x" * 8), delivery_token="t")
    assert exc.value.status_code == 403

    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(GrantDeliveryError):
        _real(boom).deliver("social-wiring", "agents", GrantPayload(credential="x" * 8), delivery_token="t")


def test_real_revoke_is_best_effort_never_raises():
    assert _real(lambda r: httpx.Response(204)).revoke("social-wiring", "agents", delivery_token="t") is True
    assert _real(lambda r: httpx.Response(401)).revoke("social-wiring", "agents", delivery_token="t") is False

    def boom(request):
        raise httpx.ConnectError("down")

    assert _real(boom).revoke("social-wiring", "agents", delivery_token="t") is False


def test_url_comes_from_resolve_product_url_env_override(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://env.example/")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    HttpGrantDelivery(client=client).deliver(
        "social-wiring", "agents", GrantPayload(credential="x" * 8), delivery_token="t")
    assert seen["url"] == "https://env.example/api/platform/grants/agents"


class TestFactory:
    def test_fake_outside_deploy(self):
        assert isinstance(make_grant_delivery(deploy_context=False), FakeGrantDelivery)

    def test_fake_refused_in_deploy(self):
        with pytest.raises(RuntimeError, match="deploy context"):
            make_grant_delivery(deploy_context=True)

    def test_real_when_requested_even_in_deploy(self):
        assert isinstance(make_grant_delivery(real=True, deploy_context=True), HttpGrantDelivery)
