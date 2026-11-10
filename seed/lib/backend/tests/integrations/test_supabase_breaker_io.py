"""Breaker IO: Redis store (via the seam, fakeredis) + owner email alerter (never silent when unconfigured)."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.email import FakeEmailSender
from noctusai_lib.integrations.supabase_breaker_io import (
    RedisBreakerStore,
    ResendBreakerAlerter,
    make_breaker_alerter,
    make_breaker_store,
)
from noctusai_lib.integrations.redis import make_fake_redis_client
from noctusai_lib.primitives.supabase_breaker import (
    BREAKER_FLEET_KEY,
    Breaker,
    BreakerAlertNotConfigured,
    InMemoryBreakerStore,
    RecordingAlerter,
)


def test_redis_store_roundtrip_has_no_ttl_and_mget_order():
    r = make_fake_redis_client()
    s = RedisBreakerStore(r)
    s.set("noctus:breaker:p:worker:a", '{"reason":"x"}')
    assert r.ttl("noctus:breaker:p:worker:a") == -1, "a trip must persist until a human re-arms"
    assert s.mget([BREAKER_FLEET_KEY, "noctus:breaker:p:worker:a"]) == [None, '{"reason":"x"}']
    s.delete("noctus:breaker:p:worker:a")
    assert s.get("noctus:breaker:p:worker:a") is None


def test_breaker_end_to_end_over_the_redis_store_and_fleet_key():
    r = make_fake_redis_client()
    b = Breaker(slug="p", store=RedisBreakerStore(r), alerter=RecordingAlerter(), sync_io=True, fleet_ttl_s=0.0)
    b.trip("worker:a", reason="runaway")
    assert r.exists("noctus:breaker:p:worker:a")
    r.set(BREAKER_FLEET_KEY, '{"reason":"402","by":"watcher"}')
    assert b.check_sync("scheduler:x", force=True)["scope"] == "fleet"


def test_alerter_names_exactly_what_is_missing():
    with pytest.raises(BreakerAlertNotConfigured) as e:
        ResendBreakerAlerter({}).send("s", "b")
    assert "RESEND_API_KEY" in str(e.value) and "NOCTUS_BREAKER_ALERT_EMAIL" in str(e.value)
    with pytest.raises(BreakerAlertNotConfigured) as e:
        ResendBreakerAlerter({"RESEND_API_KEY": "k"}).send("s", "b")
    assert "RESEND_API_KEY" not in str(e.value) and "ALERT_EMAIL" in str(e.value)


def test_alerter_sends_through_the_seed_email_seam_with_watchdog_recipient_fallback():
    sent = FakeEmailSender()
    a = ResendBreakerAlerter({"RESEND_API_KEY": "k", "WATCHDOG_ALERT_EMAIL": "owner@example.com"},
                             sender_factory=lambda cfg: sent)
    a.send("subject", "body")
    assert sent.sent[0].to == ["owner@example.com"] and sent.sent[0].subject == "subject"


def test_factories_use_fakes_when_asked_and_log_when_no_redis(monkeypatch, caplog):
    assert isinstance(make_breaker_store(use_fake=True), InMemoryBreakerStore)
    assert isinstance(make_breaker_alerter(use_fake=True), RecordingAlerter)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with caplog.at_level("ERROR"):
        assert isinstance(make_breaker_store(None), InMemoryBreakerStore)
    assert "no REDIS_URL" in caplog.text
