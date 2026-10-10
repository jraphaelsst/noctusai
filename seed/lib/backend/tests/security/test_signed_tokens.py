"""noctusai_lib.security.signed_tokens — purpose-bound public-link tokens."""
from __future__ import annotations

import pytest

from noctusai_lib.security import signed_tokens as st

SECRET = "test-secret"


def test_round_trip():
    token = st.sign("unsubscribe", {"contact_id": "c1"}, SECRET)
    assert st.verify("unsubscribe", token, SECRET) == {"contact_id": "c1"}


def test_a_token_never_verifies_for_another_purpose():
    token = st.sign("click", {"url": "https://example.com"}, SECRET)
    assert st.verify("unsubscribe", token, SECRET) is None


def test_editing_the_payload_breaks_the_mac():
    token = st.sign("click", {"url": "https://good.example"}, SECRET)
    body, mac = token.split(".")
    forged_body = st.sign("click", {"url": "https://evil.example"}, "other-secret").split(".")[0]
    assert st.verify("click", f"{forged_body}.{mac}", SECRET) is None
    assert st.verify("click", token, "wrong-secret") is None


def test_expiry():
    token = st.sign("email_confirm", {"c": 1}, SECRET, ttl_seconds=60, now=lambda: 1000)
    assert st.verify("email_confirm", token, SECRET, now=lambda: 1059) == {"c": 1}
    assert st.verify("email_confirm", token, SECRET, now=lambda: 1060) is None


@pytest.mark.parametrize("token", ["", "no-dot", "a.b.c", "!!.??", "e30.e30"])
def test_malformed_tokens_are_none_never_raise(token):
    assert st.verify("click", token, SECRET) is None


def test_empty_secret_refuses_to_sign_and_never_verifies():
    with pytest.raises(ValueError):
        st.sign("click", {}, "")
    assert st.verify("click", st.sign("click", {}, SECRET), "") is None
