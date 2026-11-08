"""SSO lifecycle S2 -- ``session_audience`` primitives + the TokenCache registry slot."""
from __future__ import annotations

import time
import uuid

import jwt as pyjwt
import pytest

from noctusai_lib.api.auth import session_audience as sa
from noctusai_lib.api.auth.token_cache import TokenCache


def _jwt(exp_in=3600, **claims):
    return pyjwt.encode({"sub": "u", "exp": int(time.time() + exp_in), **claims}, "x" * 32, algorithm="HS256")


def test_session_id_claim_is_read_unverified_and_must_be_a_uuid():
    sid = str(uuid.uuid4())
    assert sa.session_id_of(_jwt(session_id=sid)) == sid
    assert sa.session_id_of(_jwt()) is None
    assert sa.session_id_of(_jwt(session_id="nope")) is None
    assert sa.session_id_of("garbage") is None


def test_cache_slot_remembers_hit_and_miss_answers_per_token():
    cache = TokenCache(ttl_s=30)
    a, b = _jwt(session_id=str(uuid.uuid4())), _jwt(session_id=str(uuid.uuid4()))
    assert cache.get_session_product(a) == (False, None)
    assert cache.put_session_product(a, "agents")
    assert cache.put_session_product(b, None)  # "not a product session" is an answer too
    assert cache.get_session_product(a) == (True, "agents")
    assert cache.get_session_product(b) == (True, None)


def test_cache_slot_expires_with_ttl_never_past_token_exp_and_is_evicted_on_discard():
    cache = TokenCache(ttl_s=0.05)
    tok = _jwt()
    cache.put_session_product(tok, "agents")
    time.sleep(0.08)
    assert cache.get_session_product(tok) == (False, None)
    short = _jwt(exp_in=-5)
    assert cache.put_session_product(short, "agents") is False
    cache2 = TokenCache(ttl_s=30)
    cache2.put_session_product(tok, "agents")
    assert cache2.discard(tok) is False  # only the user slot counts toward the return value
    assert cache2.get_session_product(tok) == (False, None)


def test_product_session_ok_is_a_signature_preserving_marker():
    @sa.product_session_ok("bell token mint")
    async def handler(x: int, y: str = "a"):
        return x

    assert sa.is_product_session_ok(handler)
    assert not sa.is_product_session_ok(lambda: None)
    with pytest.raises(ValueError):
        sa.product_session_ok("  ")
