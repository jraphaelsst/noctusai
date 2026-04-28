"""Tests for webhook payload classification (LGPD-minimization layer)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.webhook_classification import (
    WEBHOOK_EVENT_CLASSIFICATION,
    PayloadClassNotReplayable,
    apply_classification,
    classify,
)
from app.services.webhook_delivery import retry_delivery


# ---------------------------------------------------------------------------
# Registry semantics
# ---------------------------------------------------------------------------

def test_every_known_event_classifies_to_metadata_only_today():
    """Default posture per seed-core-consolidation §7.5: every registered
    event_type is metadata_only. If this test breaks, the registry was
    changed — update the test alongside the registry so the change is
    explicit and reviewed."""
    for event_type, cls in WEBHOOK_EVENT_CLASSIFICATION.items():
        assert cls == "metadata_only", (
            f"{event_type!r} is classified {cls!r}; today's policy expects "
            f"'metadata_only' for every registered event. Either update the "
            f"registry rationale OR this test."
        )


def test_classify_returns_metadata_only_for_unknown_event():
    """Unknown events default to metadata_only — safest LGPD posture for
    new events added by forgetful agents."""
    assert classify("brand.new.event.not.yet.registered") == "metadata_only"


def test_classify_returns_registered_class():
    """Registered events return their registered class."""
    assert classify("team.invite_sent") == "metadata_only"


# ---------------------------------------------------------------------------
# apply_classification transforms
# ---------------------------------------------------------------------------

def test_apply_classification_metadata_only_returns_empty_payload():
    """metadata_only class → storable payload is empty JSONB object."""
    payload = {"email": "user@example.com", "role": "admin", "invitation_id": "x"}
    storable, cls = apply_classification("team.invite_sent", payload)
    assert cls == "metadata_only"
    assert storable == {}
    # Original payload unchanged
    assert payload == {"email": "user@example.com", "role": "admin", "invitation_id": "x"}


def test_apply_classification_full_preserves_payload():
    """full class → storable payload is identical to original."""
    payload = {"subscription_id": "sub-1", "plan": "pro"}
    # Temporarily register an event as 'full' for this test
    WEBHOOK_EVENT_CLASSIFICATION["test.full.event"] = "full"
    try:
        storable, cls = apply_classification("test.full.event", payload)
        assert cls == "full"
        assert storable == payload
    finally:
        del WEBHOOK_EVENT_CLASSIFICATION["test.full.event"]


def test_apply_classification_redacted_raises_not_implemented():
    """redacted class without a registered strategy surfaces loudly."""
    WEBHOOK_EVENT_CLASSIFICATION["test.redacted.event"] = "redacted"
    try:
        with pytest.raises(NotImplementedError, match="redaction strategy"):
            apply_classification("test.redacted.event", {"email": "x"})
    finally:
        del WEBHOOK_EVENT_CLASSIFICATION["test.redacted.event"]


def test_apply_classification_hashed_raises_not_implemented():
    """hashed class without a registered strategy surfaces loudly."""
    WEBHOOK_EVENT_CLASSIFICATION["test.hashed.event"] = "hashed"
    try:
        with pytest.raises(NotImplementedError, match="hashing strategy"):
            apply_classification("test.hashed.event", {"data": "x"})
    finally:
        del WEBHOOK_EVENT_CLASSIFICATION["test.hashed.event"]


def test_apply_classification_isolates_metadata_payload():
    """Returned storable payload is a fresh dict — mutating it must not
    poison subsequent calls."""
    storable_a, _ = apply_classification("team.invite_sent", {"a": 1})
    storable_a["mutated"] = True
    storable_b, _ = apply_classification("team.invite_sent", {"b": 2})
    assert "mutated" not in storable_b


# ---------------------------------------------------------------------------
# retry_delivery refuses replay for metadata_only rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_delivery_fails_loudly_for_metadata_only_row():
    """Pre-condition: a stored delivery row classified metadata_only has
    `payload = {}`. Replaying it would POST an empty body to the subscriber
    — worse than refusing. retry_delivery must raise PayloadClassNotReplayable
    with a fix-path in the message."""
    db = MagicMock()
    delivery_row = {
        "id": "del-1",
        "endpoint_id": "ep-1",
        "event_type": "team.invite_sent",
        "payload": {},
        "payload_class": "metadata_only",
        "status": "failed",
    }

    del_builder = MagicMock()
    del_builder.select.return_value = del_builder
    del_builder.eq.return_value = del_builder
    del_builder.single.return_value = del_builder
    del_resp = MagicMock()
    del_resp.data = delivery_row
    del_builder.execute.return_value = del_resp
    db.table.return_value = del_builder

    with patch("app.services.webhook_delivery.get_admin_client", return_value=db):
        with pytest.raises(PayloadClassNotReplayable, match="metadata_only"):
            await retry_delivery("del-1")


@pytest.mark.asyncio
async def test_retry_delivery_fails_loudly_for_hashed_row():
    """Same refusal for hashed-class stored rows."""
    db = MagicMock()
    delivery_row = {
        "id": "del-2",
        "endpoint_id": "ep-1",
        "event_type": "test.hashed.event",
        "payload": {"hash": "abc123"},
        "payload_class": "hashed",
        "status": "failed",
    }

    del_builder = MagicMock()
    del_builder.select.return_value = del_builder
    del_builder.eq.return_value = del_builder
    del_builder.single.return_value = del_builder
    del_resp = MagicMock()
    del_resp.data = delivery_row
    del_builder.execute.return_value = del_resp
    db.table.return_value = del_builder

    with patch("app.services.webhook_delivery.get_admin_client", return_value=db):
        with pytest.raises(PayloadClassNotReplayable, match="hashed"):
            await retry_delivery("del-2")


@pytest.mark.asyncio
async def test_retry_delivery_allows_legacy_null_class_rows():
    """Pre-classification rows (created before 2026-04-24) have
    payload_class=NULL and stored full payload. Retry must still work
    for those — backward compatibility."""
    db = MagicMock()

    # First SELECT returns the legacy delivery
    delivery_row = {
        "id": "del-legacy",
        "endpoint_id": "ep-1",
        "event_type": "legacy.event",
        "payload": {"original": "payload"},
        "payload_class": None,
        "status": "failed",
    }

    endpoint_row = {
        "id": "ep-1",
        "url": "https://example.com/hook",
        "secret": "whsec_test",
    }

    def table_side_effect(name):
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.single.return_value = builder
        resp = MagicMock()
        if name == "webhook_deliveries":
            resp.data = delivery_row
        else:
            resp.data = endpoint_row
        builder.execute.return_value = resp
        return builder

    db.table.side_effect = table_side_effect

    # _send_webhook does actual HTTP; patch it so we don't make real calls.
    with (
        patch("app.services.webhook_delivery.get_admin_client", return_value=db),
        patch(
            "app.services.webhook_delivery._send_webhook",
            new=AsyncMock(return_value={"id": "del-legacy", "status": "success"}),
        ) as mock_send,
    ):
        result = await retry_delivery("del-legacy")

    mock_send.assert_called_once()
    # The legacy path still uses the stored payload
    assert mock_send.call_args.args[2] == {"original": "payload"}
    assert result["status"] == "success"
