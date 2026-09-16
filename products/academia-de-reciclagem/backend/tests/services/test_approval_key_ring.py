"""Contract §D rotation: academia accepts the key ring `agents` publishes.

`approval_assertion_keys_from` is the pure step behind the
`get_approval_assertion_keys` dependency; it is exercised against the seed
`FakeAppConfigStore` (the store seam's own Fake) — no patching.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from noctusai_lib.security.app_config import FakeAppConfigStore
from noctusai_lib.security.key_ring import KeyRing

from app.config import settings
from app.dependencies import approval_assertion_keys_from


def test_env_list_is_the_fallback_when_no_ring_is_stored():
    assert approval_assertion_keys_from(FakeAppConfigStore(), env_value="a,b") == ["a", "b"]


def test_stored_ring_wins_and_includes_a_staged_key():
    now = datetime.now(timezone.utc)
    ring = KeyRing.from_value("old").rotate(
        "new", now=now, activation_delay=timedelta(minutes=5), retire_after=timedelta(hours=1)
    )
    store = FakeAppConfigStore()
    store.put(settings.approval_assertion_ring_key, ring.to_value())

    accepted = approval_assertion_keys_from(store, env_value="stale-env-key")

    assert set(accepted) == {"old", "new"}
    assert "stale-env-key" not in accepted


def test_retired_key_is_no_longer_accepted():
    past = datetime.now(timezone.utc) - timedelta(days=2)
    ring = KeyRing.from_value("old").rotate(
        "new", now=past, activation_delay=timedelta(0), retire_after=timedelta(hours=1)
    )
    store = FakeAppConfigStore()
    store.put(settings.approval_assertion_ring_key, ring.to_value())

    assert approval_assertion_keys_from(store, env_value="") == ["new"]


def test_ring_key_is_audience_scoped():
    """Contract §D: one key list per audience."""
    assert settings.approval_assertion_ring_key.endswith(":academia-de-reciclagem")
