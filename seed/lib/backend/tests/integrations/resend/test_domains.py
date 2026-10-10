"""noctusai_lib.integrations.resend.domains — Protocol + Fake + Real + factory."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from noctusai_lib.integrations.resend import (
    FakeResendDomains, HttpResendDomains, ResendDomains, ResendDomainsError,
    ResendNotConfigured, make_resend_domains,
)


def test_fake_create_then_verify_follows_published_dns():
    fake = FakeResendDomains(verifiable={"ok.example"})
    good, bad = asyncio.run(fake.create("ok.example")), asyncio.run(fake.create("no.example"))
    assert {r["record"] for r in good.records} == {"SPF", "DKIM", "DMARC"}
    assert asyncio.run(fake.verify(good.id)).status == "verified"
    assert asyncio.run(fake.verify(bad.id)).status == "failed"
    assert isinstance(fake, ResendDomains)


def test_factory_refuses_without_a_key_and_fakes_only_on_request():
    with pytest.raises(ResendNotConfigured):
        make_resend_domains(None)
    assert isinstance(make_resend_domains(None, use_fake=True), FakeResendDomains)
    assert isinstance(make_resend_domains("re_key"), HttpResendDomains)


def _client(responses):
    calls = []

    class Client:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def request(self, method, url, json=None, headers=None, timeout=None):
            calls.append((method, url))
            status, body = responses.pop(0)
            return SimpleNamespace(status_code=status, json=lambda: body, text="err")

    return Client, calls


def test_http_verify_posts_then_reads_status():
    client, calls = _client([(200, {"object": "domain"}), (200, {"id": "d1", "name": "x.com", "status": "verified"})])
    rec = asyncio.run(HttpResendDomains("re_key", http_client_factory=client).verify("d1"))
    assert rec.status == "verified"
    assert calls == [("POST", "https://api.resend.com/domains/d1/verify"), ("GET", "https://api.resend.com/domains/d1")]


def test_http_error_raises():
    client, _ = _client([(403, {})])
    with pytest.raises(ResendDomainsError):
        asyncio.run(HttpResendDomains("re_key", http_client_factory=client).create("x.com"))
