"""Every connector tool result is secret-redacted before it reaches a model (2026-11-04: WAHA
echoed its webhook hmac.key in clear through waha.session.get)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _kit.redact import REDACTED, redact_secret_fields  # noqa: E402

WAHA_SESSION = {
    "name": "default",
    "status": "WORKING",
    "config": {
        "webhooks": [{
            "url": "https://social.noctusai.com/api/whatsapp/webhook/tok",
            "events": ["message"],
            "hmac": {"key": "s3cr3t-hmac-value"},
            "customHeaders": [{"name": "X-Api-Key", "value": "hdr-secret"}],
        }],
    },
}


def test_waha_hmac_key_is_redacted_and_the_rest_survives():
    out = redact_secret_fields(WAHA_SESSION)
    hook = out["config"]["webhooks"][0]
    assert hook["hmac"]["key"] == REDACTED
    assert hook["url"].endswith("/webhook/tok") and hook["events"] == ["message"]
    assert out["status"] == "WORKING" and out["name"] == "default"
    assert "s3cr3t-hmac-value" not in repr(out)


def test_secret_named_fields_are_redacted_in_any_casing():
    src = {"apiKey": "a", "api_key": "b", "X-Api-Key": "c", "clientSecret": "d", "password": "e",
           "access_token": "f", "Authorization": "Bearer g", "privateKey": "h", "webhook_secret": "i"}
    assert all(v == REDACTED for v in redact_secret_fields(src).values())


def test_descriptive_fields_are_kept():
    src = {"token_prefix": "noc_ab12", "api_key_hint": "abcd…wxyz", "token_mascarado": "noc_…6789",
           "token_id": "uuid", "expires_at": "x", "has_token": True, "token_count": 3, "session": "default"}
    assert redact_secret_fields(src) == src


def test_empty_values_are_left_as_is_and_input_is_not_mutated():
    src = {"api_key": "", "password": None, "nested": [{"secret": "z"}]}
    out = redact_secret_fields(src)
    assert out["api_key"] == "" and out["password"] is None and out["nested"][0]["secret"] == REDACTED
    assert src["nested"][0]["secret"] == "z"
