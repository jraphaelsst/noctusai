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
    assert "NOCTUS_BREAKER_REDIS_URL" in caplog.text


# --- Redis ACL compatibility: a product writes ONLY under noctus:breaker:<slug>:* and reads only the fleet key -----


class _SpyRedis:
    """Records every key a command touches, then delegates to fakeredis."""

    def __init__(self):
        self._r = make_fake_redis_client()
        self.written: set[str] = set()
        self.read: set[str] = set()
        self.commands: set[str] = set()

    def __getattr__(self, name):
        fn = getattr(self._r, name)

        def call(*a, **kw):
            self.commands.add({"delete": "del"}.get(name, name))  # redis-py method -> the Redis command
            keys = [x for x in a if isinstance(x, str) and x.startswith("noctus:")] + \
                   ([k for x in a if isinstance(x, list) for k in x])
            (self.written if name in ("set", "delete", "sadd", "srem", "rpush", "ltrim") else self.read).update(keys)
            return fn(*a, **kw)

        return call

    def pipeline(self, transaction=True):  # the audit cap path: MULTI/EXEC are not granted, so it must not be a transaction
        assert transaction is False, "a product's ACL grant has no MULTI/EXEC"
        outer = self
        pipe = self._r.pipeline(transaction=False)

        class P:
            def rpush(self, k, v):
                outer.commands.add("rpush")
                outer.written.add(k)
                pipe.rpush(k, v)
                return self

            def ltrim(self, k, a, b):
                outer.commands.add("ltrim")
                outer.written.add(k)
                pipe.ltrim(k, a, b)
                return self

            def execute(self):
                return pipe.execute()

        return P()


import re

SLUG = "social-wiring"
#: the product's grant on the breaker Redis (feat/redis-acl-lockdown `breaker-users.acl`):
#: RW noctus:breaker:<slug>:{worker:*,scheduler:*,gate:*,audit,index}; READ-ONLY noctus:breaker:<slug>:rearm:* + the fleet key.
RW_GRANT = re.compile(rf"^noctus:breaker:{SLUG}:(worker:.+|scheduler:.+|gate:.+|audit|index)$")
RO_GRANT = re.compile(rf"^(noctus:breaker:{SLUG}:rearm:.+|{re.escape(BREAKER_FLEET_KEY)})$")
#: commands the product user may run (same file); MULTI/EXEC/SCAN/KEYS/EVAL are NOT in it
GRANTED_COMMANDS = {"get", "mget", "set", "del", "exists", "ttl", "pttl", "sadd", "srem", "smembers", "sismember",
                    "scard", "rpush", "ltrim", "lrange", "llen", "ping"}


def test_every_key_and_command_the_product_uses_falls_inside_its_acl_grant():
    spy = _SpyRedis()
    b = Breaker(slug=SLUG, store=RedisBreakerStore(spy), alerter=RecordingAlerter(), sync_io=True, fleet_ttl_s=0.0)
    b.trip("worker:a", reason="runaway", rate=3, window=300)            # SET + SADD index
    b.trip("scheduler:nightly", reason="runaway")
    b.check_sync("worker:a", force=True)                                  # MGET fleet + own keys + markers (read)
    spy._r.set(f"noctus:breaker:{SLUG}:worker:z", '{"reason":"manual","by":"manual:ana"}')  # ops-set key, no SADD
    b.check_sync("worker:z", force=True)                                  # SADD index on first observe
    b.rearm("worker:a", by="ana", reason="fixed")                         # DEL + SREM + RPUSH/LTRIM audit (no marker)
    b.rearm("scheduler:nightly", by="ana", reason="fixed")
    assert spy.written, "nothing was written?"
    for k in spy.written:
        assert RW_GRANT.match(k), f"WRITE to {k!r} is outside the RW grant (would be NOPERM at cutover)"
    for k in spy.read:
        assert RW_GRANT.match(k) or RO_GRANT.match(k), f"READ of {k!r} is outside the grant"
    assert not any(k.startswith(f"noctus:breaker:{SLUG}:rearm:") for k in spy.written), "rearm:* is READ-ONLY"
    assert BREAKER_FLEET_KEY not in spy.written and "noctus:breaker:audit" not in spy.written
    assert spy.commands <= GRANTED_COMMANDS, f"commands outside the grant: {spy.commands - GRANTED_COMMANDS}"


def test_per_source_keys_are_indexed_and_deindexed_never_scanned():
    r = make_fake_redis_client()
    s = RedisBreakerStore(r)
    s.set("noctus:breaker:p:worker:a", "{}")
    s.set(BREAKER_FLEET_KEY, "{}")
    assert r.smembers("noctus:breaker:p:index") == {"noctus:breaker:p:worker:a"}
    assert not r.exists("noctus:breaker:index"), "fleet is not indexed"
    s.delete("noctus:breaker:p:worker:a")
    assert r.smembers("noctus:breaker:p:index") == set()


def test_operator_set_key_is_indexed_when_the_product_first_observes_it():
    r = make_fake_redis_client()
    b = Breaker(slug="p", store=RedisBreakerStore(r), alerter=RecordingAlerter(), sync_io=True, fleet_ttl_s=0.0)
    r.set("noctus:breaker:p:worker:z", '{"reason":"manual","by":"manual:ana"}')  # ops has no SADD
    assert b.check_sync("worker:z", force=True) is not None
    assert r.smembers("noctus:breaker:p:index") == {"noctus:breaker:p:worker:z"}


def test_a_product_cannot_rearm_the_fleet_key():
    r = make_fake_redis_client()
    r.set(BREAKER_FLEET_KEY, "{}")
    b = Breaker(slug="p", store=RedisBreakerStore(r), alerter=RecordingAlerter(), sync_io=True)
    with pytest.raises(ValueError):
        b.rearm("fleet", by="ana", reason="x")
    assert r.exists(BREAKER_FLEET_KEY)


def test_rearm_marker_and_audit_keys_are_never_indexed_as_held_sources():
    for k in ("noctus:breaker:p:rearm:worker:a", "noctus:breaker:p:audit", "noctus:breaker:p:index", BREAKER_FLEET_KEY):
        assert RedisBreakerStore.index_key(k) is None, k
    assert RedisBreakerStore.index_key("noctus:breaker:p:worker:a") == "noctus:breaker:p:index"


def test_breaker_store_selection_dedicated_redis_then_loud_app_fallback_then_fake(caplog):
    from noctusai_lib.integrations.supabase_breaker_io import make_breaker_store

    env = {"NOCTUS_BREAKER_REDIS_URL": "redis://noctus-breaker-redis:6379/0", "NOCTUS_BREAKER_REDIS_USERNAME": "social-wiring",
           "NOCTUS_BREAKER_REDIS_PASSWORD": "s3cret", "REDIS_URL": "redis://app:6379/0", "REDIS_USERNAME": "app-user"}
    st = make_breaker_store(environ=env, deploy=True)
    kw = st._r.connection_pool.connection_kwargs
    assert isinstance(st, RedisBreakerStore) and kw["host"] == "noctus-breaker-redis"
    assert kw["username"] == "social-wiring" and kw["password"] == "s3cret", "explicit breaker creds, not REDIS_*"
    with caplog.at_level("WARNING"):
        fb = make_breaker_store(environ={"REDIS_URL": "redis://app:6379/0"}, deploy=True)
    assert isinstance(fb, RedisBreakerStore) and fb._r.connection_pool.connection_kwargs["host"] == "app"
    assert "breaker-redis-cutover" in caplog.text and "NOCTUS_BREAKER_REDIS_URL" in caplog.text
    assert isinstance(make_breaker_store(environ={"REDIS_URL": "redis://app:6379/0"}, deploy=False), InMemoryBreakerStore)
    assert isinstance(make_breaker_store(environ={}, deploy=True), InMemoryBreakerStore)
    assert isinstance(make_breaker_store(environ=env, deploy=True, use_fake=True), InMemoryBreakerStore)


def test_P3_3_the_breaker_client_uses_only_breaker_credentials_and_refuses_unauthenticated(caplog):
    from noctusai_lib.integrations.supabase_breaker_io import make_breaker_store

    base = {"NOCTUS_BREAKER_REDIS_URL": "redis://noctus-breaker-redis:6379/0", "REDIS_USERNAME": "app-user",
            "REDIS_PASSWORD": "app-secret"}
    with caplog.at_level("CRITICAL"):
        st = make_breaker_store(environ=base, deploy=True)  # breaker creds absent: NO fallback to REDIS_*
    assert isinstance(st, InMemoryBreakerStore) and "refusing to connect unauthenticated" in caplog.text
    ok = make_breaker_store(environ={**base, "NOCTUS_BREAKER_REDIS_USERNAME": "sw", "NOCTUS_BREAKER_REDIS_PASSWORD": "bk"},
                            deploy=True)
    kw = ok._r.connection_pool.connection_kwargs
    assert (kw["username"], kw["password"]) == ("sw", "bk") and ok.on_app_redis_fallback is False


def test_P2_2_the_app_redis_fallback_is_flagged_so_the_app_can_mark_it_degraded():
    from noctusai_lib.integrations.supabase_breaker_io import make_breaker_store

    fb = make_breaker_store(environ={"REDIS_URL": "redis://app:6379/0"}, deploy=True)
    assert fb.on_app_redis_fallback is True
