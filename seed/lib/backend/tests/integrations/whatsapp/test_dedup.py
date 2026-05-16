"""Webhook dedup — SETNX pre-filter (Fake + Real) + factory.

Validates the reconcile of the WAHA duplicate-event race
(SESSION-NOTES §4.1): WAHA delivers the same provider_message_id twice
(``message`` + ``message.any``); the first ``claim`` wins, the second
is a duplicate.
"""

from noctusai_lib.integrations.redis import make_fake_redis_client
from noctusai_lib.integrations.whatsapp import (
    InMemoryWebhookDedup,
    RedisWebhookDedup,
    WebhookDedup,
    get_webhook_dedup,
)


def test_in_memory_dedup_claims_first_then_rejects_duplicate() -> None:
    dedup = InMemoryWebhookDedup()

    assert dedup.claim("msg-1") is True
    assert dedup.claim("msg-1") is False
    assert dedup.claim("msg-2") is True


def test_in_memory_dedup_clear_resets() -> None:
    dedup = InMemoryWebhookDedup()
    dedup.claim("msg-1")

    dedup.clear()

    assert dedup.claim("msg-1") is True


def test_redis_dedup_setnx_first_wins_duplicate_rejected() -> None:
    redis = make_fake_redis_client()
    dedup = RedisWebhookDedup(redis)

    assert dedup.claim("3EB0DUP") is True
    assert dedup.claim("3EB0DUP") is False
    assert dedup.claim("3EB0OTHER") is True


def test_redis_dedup_writes_namespaced_key_with_ttl() -> None:
    redis = make_fake_redis_client()
    dedup = RedisWebhookDedup(redis, key_prefix="wa:dedup:", ttl_seconds=120)

    dedup.claim("mid")

    assert redis.get("wa:dedup:mid") == "1"
    ttl = redis.ttl("wa:dedup:mid")
    assert 0 < ttl <= 120


def test_factory_returns_fake_without_redis_real_with_redis() -> None:
    assert isinstance(get_webhook_dedup(), InMemoryWebhookDedup)
    assert isinstance(
        get_webhook_dedup(redis_client=make_fake_redis_client()),
        RedisWebhookDedup,
    )


def test_both_satisfy_webhook_dedup_protocol() -> None:
    assert isinstance(InMemoryWebhookDedup(), WebhookDedup)
    assert isinstance(
        RedisWebhookDedup(make_fake_redis_client()), WebhookDedup
    )
