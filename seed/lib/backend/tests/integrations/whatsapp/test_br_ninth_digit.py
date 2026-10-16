"""BR 9th-digit resolution: pure variants + WahaClient/Fake send path."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from noctusai_lib.integrations.whatsapp import (
    FakeWahaClient,
    WahaNumberCheckError,
    WahaNumberNotOnWhatsApp,
)
from noctusai_lib.integrations.whatsapp.client import WahaClient
from noctusai_lib.primitives.phone import br_mobile_variants


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5511994573387", ["5511994573387", "551194573387"]),
        ("+55 (11) 99457-3387", ["5511994573387", "551194573387"]),
        ("11994573387", ["5511994573387", "551194573387"]),
        ("551194573387", ["551194573387", "5511994573387"]),
        ("1194573387", ["551194573387", "5511994573387"]),
        ("551132165498", ["551132165498"]),
        ("+14155550123", ["14155550123"]),
        ("lixo", []),
        ("", []),
        (None, []),
    ],
)
def test_variants(raw, expected):
    assert br_mobile_variants(raw) == expected


class _Waha:
    def __init__(self, registered, check_status=200):
        self.registered = registered
        self.check_status = check_status
        self.checks: list[str] = []
        self.sends: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/contacts/check-exists":
            if self.check_status >= 400:
                return httpx.Response(self.check_status, json={})
            phone = request.url.params["phone"]
            self.checks.append(phone)
            ok = phone in self.registered
            return httpx.Response(
                200, json={"numberExists": ok, "chatId": f"{phone}@c.us" if ok else None}
            )
        body = json.loads(request.content)
        self.sends.append(body["chatId"])
        if body["chatId"].split("@")[0] not in self.registered:
            return httpx.Response(422, json={"error": "nope"})
        return httpx.Response(201, json={"id": "m1"})

    def client(self):
        return WahaClient("https://waha.test", "k", transport=httpx.MockTransport(self.handler))


def test_resolves_variant_before_send_and_caches():
    w = _Waha({"551194573387"})
    c = w.client()
    r = asyncio.run(c.send_text_to_phone("5511994573387", "oi"))
    assert w.sends == ["551194573387@c.us"]
    assert r["resolvedChatId"] == "551194573387@c.us"
    assert r["resolvedVariantUsed"] is True and r["resolutionMethod"] == "check-exists"
    asyncio.run(c.send_text_to_phone("5511994573387", "again"))
    assert len(w.checks) == 2  # second call served from cache (no new checks)


def test_as_given_wins_without_variant():
    w = _Waha({"5511994573387"})
    r = asyncio.run(w.client().send_text_to_phone("5511994573387", "oi"))
    assert r["resolvedVariantUsed"] is False and w.checks == ["5511994573387"]


def test_not_on_whatsapp_raises_with_tried():
    w = _Waha(set())
    with pytest.raises(WahaNumberNotOnWhatsApp) as ei:
        asyncio.run(w.client().send_text_to_phone("5511994573387", "oi"))
    assert ei.value.tried == ["5511994573387", "551194573387"]
    assert w.sends == []


def test_check_unavailable_falls_back_to_send_retry():
    w = _Waha({"551194573387"}, check_status=501)
    r = asyncio.run(w.client().send_text_to_phone("5511994573387", "oi"))
    assert w.sends == ["5511994573387@c.us", "551194573387@c.us"]
    assert r["resolutionMethod"] == "send-retry" and r["resolvedVariantUsed"] is True


def test_check_exists_error_class():
    with pytest.raises(WahaNumberCheckError):
        asyncio.run(_Waha(set(), check_status=500).client().check_exists("5511994573387"))


def test_fake_mirrors_behaviour():
    f = FakeWahaClient()
    f.registered_numbers = {"551194573387"}
    r = asyncio.run(f.send_text_to_phone("5511994573387", "oi"))
    assert f.sent_messages[0]["chatId"] == "551194573387@c.us"
    assert r["resolvedVariantUsed"] is True
    f.check_unavailable = True
    r = asyncio.run(f.send_text_to_phone("5511994573387", "oi"))
    assert r["resolutionMethod"] == "send-retry"
    f.registered_numbers = set()
    with pytest.raises(WahaNumberNotOnWhatsApp):
        asyncio.run(f.send_text_to_phone("5511994573387", "oi"))
