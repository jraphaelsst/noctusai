"""The webhook base: the edge relay on a `send: disabled` line that declares one; the product URL on the live line.

The WAHA core sits on a private network behind the edge deny proxy and cannot reach the product; the seed client
refuses `set_webhook` outside the policy's `webhook_relay` (KB § INTEGRATIONS/whatsapp.md §6a). Registering the
public URL would make pairing fail on the real line.
"""
from __future__ import annotations

import json

import pytest

from app.routers.whatsapp_router import webhook_base_url

POLICY = {
    "send": "disabled", "mark_online": False, "full_sync": False, "auto_repair": False,
    "webhook_relay": "http://waha-assistant:3001",
}


def _never() -> str:
    raise AssertionError("the public product URL must not be used when the line declares a relay")


def test_relay_is_the_webhook_base_on_a_read_only_line():
    assert webhook_base_url(json.dumps(POLICY), _never) == "http://waha-assistant:3001"


def test_without_a_policy_the_product_url_is_used():
    assert webhook_base_url("", lambda: "https://assistant.example.test") == "https://assistant.example.test"


def test_a_policy_without_relay_falls_back_to_the_product_url():
    policy = {k: v for k, v in POLICY.items() if k != "webhook_relay"}
    assert webhook_base_url(json.dumps(policy), lambda: "https://assistant.example.test") == "https://assistant.example.test"


def test_a_malformed_policy_raises_instead_of_guessing():
    with pytest.raises(ValueError):
        webhook_base_url("{not json", _never)


def test_the_live_send_enabled_line_has_no_edge_so_the_webhook_goes_direct_to_the_product():
    live = {"send": "enabled", "mark_online": True, "full_sync": True, "auto_repair": True}
    assert webhook_base_url(json.dumps(live), lambda: "https://assistant.example.test") == "https://assistant.example.test"
