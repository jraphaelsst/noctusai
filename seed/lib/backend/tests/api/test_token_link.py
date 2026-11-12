"""`resolve_token_link` -- the token-link tier's one resolver: malformed = 404, expiry fails CLOSED, no token in logs."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.api.token_link import TokenLinkGone, TokenLinkNotFound, resolve_token_link, token_fingerprint

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
TOK = str(uuid.uuid4())


def _fetch(row):
    calls = []

    def fetch(token):
        calls.append(token)
        return row

    fetch.calls = calls
    return fetch


def test_valid_link_returns_the_row():
    row = {"id": "1", "expires_at": (NOW + timedelta(days=1)).isoformat()}
    assert resolve_token_link(TOK, _fetch(row), now=NOW) is row


def test_malformed_token_is_not_found_and_never_looked_up():
    fetch = _fetch({"expires_at": NOW.isoformat()})
    with pytest.raises(TokenLinkNotFound):
        resolve_token_link("not-a-uuid", fetch, now=NOW)
    assert fetch.calls == []


def test_unknown_token_is_not_found():
    with pytest.raises(TokenLinkNotFound):
        resolve_token_link(TOK, _fetch(None), now=NOW)


def test_token_is_canonicalised_before_the_lookup():
    fetch = _fetch({"expires_at": (NOW + timedelta(days=1)).isoformat()})
    resolve_token_link(TOK.upper(), fetch, now=NOW)
    assert fetch.calls == [TOK]


@pytest.mark.parametrize("expires", [None, "", "garbage", "2026-13-45"])
def test_missing_or_unparsable_expiry_fails_closed(expires):
    with pytest.raises(TokenLinkGone):
        resolve_token_link(TOK, _fetch({"expires_at": expires}), now=NOW)


def test_expired_link_is_gone():
    with pytest.raises(TokenLinkGone):
        resolve_token_link(TOK, _fetch({"expires_at": (NOW - timedelta(seconds=1)).isoformat()}), now=NOW)


def test_z_suffix_and_naive_timestamps_parse():
    ok = resolve_token_link(TOK, _fetch({"expires_at": "2026-11-11T00:00:00Z"}), now=NOW)
    assert ok
    ok2 = resolve_token_link(TOK, _fetch({"expires_at": "2026-11-11T00:00:00"}), now=NOW)
    assert ok2


def test_fingerprint_never_contains_the_token():
    fp = token_fingerprint(TOK)
    assert TOK not in fp and TOK[:8] not in fp and fp.startswith("tok:")
