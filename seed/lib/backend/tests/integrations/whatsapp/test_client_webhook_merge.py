"""set_webhook / remove_webhook MERGE into the session's shared webhook list.

WAHA's PUT /api/sessions/{name} is a full replace and one session can serve
several products; these tests pin that a product only ever touches its own
entries. Uses the client's ``transport=`` seam (real ``_request`` path).
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from noctusai_lib.integrations.whatsapp import FakeWahaClient, WahaWebhookError
from noctusai_lib.integrations.whatsapp.client import WahaClient

SW = "https://sw.example.com/api/webhooks/whatsapp"
ORB = "https://orbity.example.com/api/webhooks/whatsapp"
FOREIGN = {
    "url": f"{ORB}/tok-orb",
    "events": ["message.any"],
    "hmac": {"key": "s3cret"},
    "retries": {"delaySeconds": 2, "attempts": 5, "policy": "linear"},
    "customHeaders": [{"name": "X-A", "value": "1"}],
}


class _Waha:
    """Stateful WAHA stand-in behind httpx.MockTransport."""

    def __init__(self, webhooks=None, get_status=200, body_override=None):
        self.webhooks = list(webhooks or [])
        self.get_status = get_status
        self.body_override = body_override
        self.puts: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            if self.get_status >= 400:
                return httpx.Response(self.get_status, json={"error": "boom"})
            if self.body_override is not None:
                return httpx.Response(200, json=self.body_override)
            return httpx.Response(
                200, json={"name": "default", "config": {"webhooks": self.webhooks}}
            )
        body = json.loads(request.content)
        self.puts.append(body)
        self.webhooks = body["config"]["webhooks"]
        return httpx.Response(200, json={"name": "default"})

    def client(self) -> WahaClient:
        return WahaClient(
            base_url="https://waha.test", api_key="k", session="default",
            transport=httpx.MockTransport(self.handler),
        )


def _urls(waha: _Waha) -> list[str]:
    return [h["url"] for h in waha.webhooks]


def test_two_products_keep_both_webhooks() -> None:
    waha = _Waha()
    asyncio.run(waha.client().set_webhook(f"{SW}/tok-sw", ["message"]))
    asyncio.run(waha.client().set_webhook(f"{ORB}/tok-orb", ["message"]))
    assert _urls(waha) == [f"{SW}/tok-sw", f"{ORB}/tok-orb"]


def test_reregister_new_token_replaces_only_own() -> None:
    waha = _Waha(webhooks=[{"url": f"{SW}/old", "events": ["message"]}, FOREIGN])
    asyncio.run(waha.client().set_webhook(f"{SW}/new", ["message"]))
    assert _urls(waha) == [FOREIGN["url"], f"{SW}/new"]


def test_same_url_reregistered_does_not_duplicate() -> None:
    waha = _Waha(webhooks=[{"url": f"{SW}/t", "events": ["a"]}])
    asyncio.run(waha.client().set_webhook(f"{SW}/t", ["message"]))
    assert _urls(waha) == [f"{SW}/t"]
    assert waha.webhooks[0]["events"] == ["message"]


def test_foreign_entry_fields_preserved_verbatim() -> None:
    waha = _Waha(webhooks=[FOREIGN])
    asyncio.run(waha.client().set_webhook(f"{SW}/t", ["message"]))
    assert waha.puts[0]["config"]["webhooks"][0] == FOREIGN


def test_explicit_owned_prefix_and_no_bare_host_prefix() -> None:
    peer = {"url": "https://x/other", "events": []}
    waha = _Waha(webhooks=[peer])
    # default prefix for a one-segment path must be exact-match only
    asyncio.run(waha.client().set_webhook("https://x/wh", ["message"]))
    assert _urls(waha) == ["https://x/other", "https://x/wh"]
    asyncio.run(waha.client().set_webhook("https://x/wh2", [], owned_prefix="https://x/wh"))
    assert _urls(waha) == ["https://x/other", "https://x/wh2"]


def test_noweb_store_present_in_every_put() -> None:
    waha = _Waha(webhooks=[FOREIGN])
    asyncio.run(waha.client().set_webhook(f"{SW}/t", ["message"]))
    asyncio.run(waha.client().remove_webhook(f"{SW}/t"))
    assert len(waha.puts) == 2
    for put in waha.puts:
        assert put["config"]["noweb"]["store"] == {"enabled": True, "fullSync": True}


def test_remove_removes_only_own() -> None:
    waha = _Waha(webhooks=[{"url": f"{SW}/t", "events": []}, FOREIGN])
    out = asyncio.run(waha.client().remove_webhook(f"{SW}/t"))
    assert out["removed"] == 1
    assert waha.webhooks == [FOREIGN]


def test_remove_noop_when_nothing_matches_does_not_put() -> None:
    waha = _Waha(webhooks=[FOREIGN])
    out = asyncio.run(waha.client().remove_webhook(f"{SW}/t"))
    assert out == {"removed": 0}
    assert waha.puts == []


@pytest.mark.parametrize("op", ["set", "remove"])
def test_get_session_failure_raises_and_never_puts(op: str) -> None:
    waha = _Waha(webhooks=[FOREIGN], get_status=500)
    client = waha.client()
    with pytest.raises(WahaWebhookError):
        if op == "set":
            asyncio.run(client.set_webhook(f"{SW}/t", ["message"]))
        else:
            asyncio.run(client.remove_webhook(f"{SW}/t"))
    assert waha.puts == []


@pytest.mark.parametrize(
    "body", [["not", "an", "object"], {}, {"config": "x"}, {"config": {"webhooks": "x"}}]
)
def test_malformed_shape_raises_and_never_puts(body) -> None:
    waha = _Waha(body_override=body)
    with pytest.raises(WahaWebhookError):
        asyncio.run(waha.client().set_webhook(f"{SW}/t", ["message"]))
    assert waha.puts == []


@pytest.mark.parametrize("body", [{"name": "d"}, {"config": None}, {"config": {}}])
def test_absent_config_or_webhooks_means_empty(body) -> None:
    waha = _Waha(body_override=body)
    asyncio.run(waha.client().set_webhook(f"{SW}/t", ["message"]))
    assert _urls(waha) == [f"{SW}/t"]


def test_fake_mirrors_merge_semantics() -> None:
    fake = FakeWahaClient()
    asyncio.run(fake.set_webhook(f"{SW}/old", ["message"]))
    asyncio.run(fake.set_webhook(f"{ORB}/o", ["message"]))
    asyncio.run(fake.set_webhook(f"{SW}/new", ["message"]))
    assert [h["url"] for h in fake.session_webhooks] == [f"{ORB}/o", f"{SW}/new"]
    assert asyncio.run(fake.remove_webhook(f"{SW}/new")) == {"removed": 1}
    assert asyncio.run(fake.remove_webhook(f"{SW}/new")) == {"removed": 0}
    assert [h["url"] for h in fake.session_webhooks] == [f"{ORB}/o"]
    fake.fail_webhook_read = True
    with pytest.raises(WahaWebhookError):
        asyncio.run(fake.set_webhook(f"{SW}/x", []))
    assert [h["url"] for h in fake.session_webhooks] == [f"{ORB}/o"]
