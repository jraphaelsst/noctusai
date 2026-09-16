"""Tests for `noctusai_lib.security.key_ring` and the app_config additions it
composes (`CachedAppConfigStore`, `resolve_app_config_value`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.security.app_config import (
    AppConfigDecryptError,
    CachedAppConfigStore,
    FakeAppConfigStore,
    resolve_app_config_value,
)
from noctusai_lib.security.key_ring import (
    KeyRing,
    fingerprint,
    generate_ring_secret,
    resolve_key_ring,
)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


class TestLegacyCsv:
    def test_csv_signs_with_first_and_accepts_all(self):
        ring = KeyRing.from_value("k1,k2")
        assert ring.signing_key(NOW).secret == "k1"
        assert ring.accepted(NOW) == ["k1", "k2"]

    def test_empty_value_is_empty_ring(self):
        ring = KeyRing.from_value("")
        assert ring.signing_key(NOW) is None
        assert ring.accepted(NOW) == []

    def test_malformed_json_raises(self):
        with pytest.raises(ValueError):
            KeyRing.from_value('{"keys": "nope"}')


class TestRotation:
    def _rotated(self):
        return KeyRing.from_value("old").rotate(
            "new",
            now=NOW,
            activation_delay=timedelta(seconds=60),
            retire_after=timedelta(hours=24),
        )

    def test_staged_key_is_accepted_but_not_yet_signing(self):
        ring = self._rotated()
        assert ring.signing_key(NOW).secret == "old"
        assert set(ring.accepted(NOW)) == {"old", "new"}

    def test_signer_switches_after_the_activation_delay(self):
        ring = self._rotated()
        later = NOW + timedelta(seconds=61)
        assert ring.signing_key(later).secret == "new"
        assert set(ring.accepted(later)) == {"old", "new"}

    def test_old_key_retires_after_the_window_and_prune_drops_it(self):
        ring = self._rotated()
        after = NOW + timedelta(seconds=60, hours=24, minutes=1)
        assert ring.accepted(after) == ["new"]
        pruned = ring.prune(after)
        assert [k.secret for k in pruned.keys] == ["new"]

    def test_round_trips_through_the_stored_form(self):
        ring = self._rotated()
        again = KeyRing.from_value(ring.to_value())
        assert again == ring

    def test_duplicate_or_comma_secret_refused(self):
        ring = KeyRing.from_value("old")
        with pytest.raises(ValueError):
            ring.rotate("old", now=NOW, activation_delay=timedelta(0), retire_after=timedelta(0))
        with pytest.raises(ValueError):
            ring.rotate("a,b", now=NOW, activation_delay=timedelta(0), retire_after=timedelta(0))


class TestHelpers:
    def test_fingerprint_is_not_a_prefix_of_the_secret(self):
        secret = generate_ring_secret()
        assert len(fingerprint(secret)) == 12
        assert not secret.startswith(fingerprint(secret))
        assert "," not in secret


class TestResolution:
    def test_db_value_wins_over_env(self):
        store = FakeAppConfigStore()
        store.put("ring", "db1")
        assert resolve_key_ring(store, "ring", env_value="env1").accepted(NOW) == ["db1"]

    def test_env_is_the_fallback(self):
        assert resolve_app_config_value(FakeAppConfigStore(), "x", env_value="e") == ("e", "env")
        assert resolve_app_config_value(FakeAppConfigStore(), "x", env_value="") == (None, None)

    def test_decrypt_error_never_falls_back_to_env(self):
        class _Broken(FakeAppConfigStore):
            def get(self, key):
                raise AppConfigDecryptError("bad key")

        with pytest.raises(AppConfigDecryptError):
            resolve_app_config_value(_Broken(), "x", env_value="e")


class _CountingStore(FakeAppConfigStore):
    def __init__(self):
        super().__init__()
        self.reads = 0

    def get(self, key):
        self.reads += 1
        return super().get(key)


class TestCachedAppConfigStore:
    def test_hits_and_misses_are_cached_for_the_ttl(self):
        inner = _CountingStore()
        clock = [0.0]
        cache = CachedAppConfigStore(inner, ttl_seconds=30, clock=lambda: clock[0])
        assert cache.get("k") is None
        assert cache.get("k") is None
        assert inner.reads == 1
        inner.put("k", "v")  # another process writes
        assert cache.get("k") is None  # still inside the TTL
        clock[0] = 31.0
        assert cache.get("k") == "v"
        assert inner.reads == 2

    def test_own_write_invalidates_immediately(self):
        inner = _CountingStore()
        cache = CachedAppConfigStore(inner, ttl_seconds=30, clock=lambda: 0.0)
        assert cache.get("k") is None
        cache.put("k", "v")
        assert cache.get("k") == "v"
        assert cache.delete("k") is True
        assert cache.get("k") is None

    def test_negative_ttl_refused(self):
        with pytest.raises(ValueError):
            CachedAppConfigStore(FakeAppConfigStore(), ttl_seconds=-1)
