"""Tests for the webhook delivery service."""
import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.webhook_delivery import (
    dispatch,
    retry_delivery,
    _send_webhook,
    MAX_RETRIES,
    WEBHOOK_TIMEOUT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_ENDPOINT = {
    "id": "ep-1",
    "org_id": "org-1",
    "url": "https://example.com/hook",
    "secret": "whsec_test123",
    "events": ["subscription.created", "*"],
    "is_active": True,
}

SAMPLE_ENDPOINT_FILTERED = {
    **SAMPLE_ENDPOINT,
    "id": "ep-2",
    "events": ["user.invited"],  # Does NOT match subscription.created
}

SAMPLE_PAYLOAD = {"subscription_id": "sub-1", "plan": "pro"}


def _mock_db(endpoints=None, deliveries=None):
    """Create a mock admin client with table routing."""
    db = MagicMock()
    tables = {}

    def _table(name):
        if name not in tables:
            tables[name] = MagicMock()
        return tables[name]

    db.table = _table

    # webhook_endpoints
    ep_builder = MagicMock()
    ep_builder.select.return_value = ep_builder
    ep_builder.eq.return_value = ep_builder
    ep_builder.single.return_value = ep_builder

    ep_resp = MagicMock()
    ep_resp.data = endpoints if endpoints is not None else []
    ep_builder.execute.return_value = ep_resp
    tables["webhook_endpoints"] = ep_builder

    # webhook_deliveries
    del_builder = MagicMock()
    del_builder.select.return_value = del_builder
    del_builder.insert.return_value = del_builder
    del_builder.update.return_value = del_builder
    del_builder.eq.return_value = del_builder
    del_builder.single.return_value = del_builder

    if deliveries is not None:
        del_resp = MagicMock()
        del_resp.data = deliveries
        del_builder.execute.return_value = del_resp
    else:
        # Insert returns record with id, update returns updated record
        insert_resp = MagicMock()
        insert_resp.data = [{"id": "del-1", "status": "pending"}]
        update_resp = MagicMock()
        update_resp.data = [{"id": "del-1", "status": "success", "attempts": 1}]
        del_builder.execute.side_effect = [insert_resp, update_resp]

    tables["webhook_deliveries"] = del_builder

    return db


# ---------------------------------------------------------------------------
# dispatch() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_no_endpoints():
    """dispatch() returns empty list when no endpoints match."""
    db = _mock_db(endpoints=[])

    with patch("app.services.webhook_delivery.get_admin_client", return_value=db):
        result = await dispatch("org-1", "subscription.created", SAMPLE_PAYLOAD)

    assert result == []


@pytest.mark.asyncio
async def test_dispatch_with_matching_endpoint():
    """dispatch() sends to endpoints that match the event type."""
    db = _mock_db(endpoints=[SAMPLE_ENDPOINT])

    # Mock the _send_webhook to avoid real HTTP
    with (
        patch("app.services.webhook_delivery.get_admin_client", return_value=db),
        patch("app.services.webhook_delivery._send_webhook", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.return_value = {"id": "del-1", "status": "success"}
        result = await dispatch("org-1", "subscription.created", SAMPLE_PAYLOAD)

    assert len(result) == 1
    mock_send.assert_called_once_with(SAMPLE_ENDPOINT, "subscription.created", SAMPLE_PAYLOAD)


@pytest.mark.asyncio
async def test_dispatch_filters_non_matching_events():
    """dispatch() skips endpoints whose events list doesn't include the event type."""
    db = _mock_db(endpoints=[SAMPLE_ENDPOINT_FILTERED])

    with (
        patch("app.services.webhook_delivery.get_admin_client", return_value=db),
        patch("app.services.webhook_delivery._send_webhook", new_callable=AsyncMock) as mock_send,
    ):
        result = await dispatch("org-1", "subscription.created", SAMPLE_PAYLOAD)

    assert result == []
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# HMAC signature test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_webhook_hmac_signature():
    """_send_webhook() signs the payload with HMAC-SHA256."""
    db = _mock_db()
    sent_headers = {}

    async def _capture_post(url, content=None, headers=None):
        sent_headers.update(headers or {})
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        return resp

    with (
        patch("app.services.webhook_delivery.get_admin_client", return_value=db),
        patch("httpx.AsyncClient") as MockClient,
    ):
        mock_client = AsyncMock()
        mock_client.post = _capture_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        await _send_webhook(SAMPLE_ENDPOINT, "test.event", SAMPLE_PAYLOAD)

    assert "X-Webhook-Signature" in sent_headers
    assert "X-Webhook-Timestamp" in sent_headers
    assert "X-Webhook-Event" in sent_headers
    assert sent_headers["X-Webhook-Event"] == "test.event"

    # Verify the signature
    timestamp = sent_headers["X-Webhook-Timestamp"]
    payload_json = json.dumps(SAMPLE_PAYLOAD, default=str, ensure_ascii=False)
    expected_sig = hmac.new(
        SAMPLE_ENDPOINT["secret"].encode(),
        f"{timestamp}.{payload_json}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert sent_headers["X-Webhook-Signature"] == expected_sig


# ---------------------------------------------------------------------------
# Retry with backoff test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_webhook_retries_with_backoff():
    """_send_webhook() retries with exponential backoff on failure."""
    db = _mock_db()

    call_count = 0

    async def _failing_post(url, content=None, headers=None):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        return resp

    with (
        patch("app.services.webhook_delivery.get_admin_client", return_value=db),
        patch("httpx.AsyncClient") as MockClient,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_client = AsyncMock()
        mock_client.post = _failing_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        await _send_webhook(SAMPLE_ENDPOINT, "test.event", SAMPLE_PAYLOAD)

    # Should have attempted MAX_RETRIES + 1 times (3 total)
    assert call_count == MAX_RETRIES + 1

    # Backoff sleeps: 2^1=2, 2^2=4 (no sleep after last attempt)
    assert mock_sleep.call_count == MAX_RETRIES
    mock_sleep.assert_any_call(2)
    mock_sleep.assert_any_call(4)


# ---------------------------------------------------------------------------
# retry_delivery() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_delivery_not_found():
    """retry_delivery() raises ValueError for missing delivery."""
    db = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.single.return_value = builder
    resp = MagicMock()
    resp.data = None
    builder.execute.return_value = resp
    db.table.return_value = builder

    with patch("app.services.webhook_delivery.get_admin_client", return_value=db):
        with pytest.raises(ValueError, match="Delivery not found"):
            await retry_delivery("missing-id")


@pytest.mark.asyncio
async def test_retry_delivery_already_succeeded():
    """retry_delivery() raises ValueError if delivery already succeeded."""
    db = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.single.return_value = builder
    resp = MagicMock()
    resp.data = {"id": "del-1", "status": "success", "endpoint_id": "ep-1"}
    builder.execute.return_value = resp
    db.table.return_value = builder

    with patch("app.services.webhook_delivery.get_admin_client", return_value=db):
        with pytest.raises(ValueError, match="already succeeded"):
            await retry_delivery("del-1")


@pytest.mark.asyncio
async def test_retry_delivery_success():
    """retry_delivery() re-dispatches a failed delivery."""
    delivery_record = {
        "id": "del-1",
        "status": "failed",
        "endpoint_id": "ep-1",
        "event_type": "subscription.created",
        "payload": SAMPLE_PAYLOAD,
    }

    # We need table to return different data for deliveries vs endpoints
    call_count = {"table": 0}
    delivery_builder = MagicMock()
    delivery_builder.select.return_value = delivery_builder
    delivery_builder.eq.return_value = delivery_builder
    delivery_builder.single.return_value = delivery_builder
    del_resp = MagicMock()
    del_resp.data = delivery_record
    delivery_builder.execute.return_value = del_resp

    endpoint_builder = MagicMock()
    endpoint_builder.select.return_value = endpoint_builder
    endpoint_builder.eq.return_value = endpoint_builder
    endpoint_builder.single.return_value = endpoint_builder
    ep_resp = MagicMock()
    ep_resp.data = SAMPLE_ENDPOINT
    endpoint_builder.execute.return_value = ep_resp

    db = MagicMock()
    db.table.side_effect = lambda name: (
        delivery_builder if name == "webhook_deliveries" else endpoint_builder
    )

    with (
        patch("app.services.webhook_delivery.get_admin_client", return_value=db),
        patch("app.services.webhook_delivery._send_webhook", new_callable=AsyncMock) as mock_send,
    ):
        mock_send.return_value = {"id": "del-2", "status": "success"}
        result = await retry_delivery("del-1")

    mock_send.assert_called_once_with(SAMPLE_ENDPOINT, "subscription.created", SAMPLE_PAYLOAD)
    assert result["status"] == "success"
