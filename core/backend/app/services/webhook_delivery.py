"""
NoctusAI Core — Webhook Delivery Service.

Dispatches webhook events to registered endpoints with HMAC-SHA256 signed payloads.
Logs delivery attempts and results.
"""
import asyncio
import hmac
import json
import hashlib
import logging
import time
from typing import Optional

import httpx
from app.database import get_admin_client

logger = logging.getLogger(__name__)

# Timeout for webhook HTTP requests (seconds)
WEBHOOK_TIMEOUT = 10.0
MAX_RETRIES = 2


async def dispatch(org_id: str, event_type: str, payload: dict) -> list[dict]:
    """
    Find all matching webhook endpoints for the org/event, send HTTP POST
    with HMAC-SHA256 signature, and log delivery results.

    Args:
        org_id: The organization UUID that triggered the event.
        event_type: Event type string (e.g. 'subscription.created', 'user.invited').
        payload: The JSON-serializable event payload.

    Returns:
        List of delivery log records.
    """
    db = get_admin_client()

    # Find active webhook endpoints for this org that listen to this event
    endpoints_result = db.table("webhook_endpoints").select("*").eq(
        "org_id", org_id
    ).eq("is_active", True).execute()

    if not endpoints_result.data:
        return []

    deliveries = []

    for endpoint in endpoints_result.data:
        # Check if this endpoint listens to this event type
        events = endpoint.get("events", [])
        if events and event_type not in events and "*" not in events:
            continue

        delivery = await _send_webhook(endpoint, event_type, payload)
        deliveries.append(delivery)

    return deliveries


async def _send_webhook(endpoint: dict, event_type: str, payload: dict) -> dict:
    """
    Send a single webhook delivery to an endpoint.

    Signs the payload with HMAC-SHA256 using the endpoint's secret.
    Logs the delivery attempt and result.
    """
    db = get_admin_client()
    endpoint_id = endpoint["id"]
    url = endpoint["url"]
    secret = endpoint["secret"]

    # Prepare the payload
    payload_json = json.dumps(payload, default=str, ensure_ascii=False)
    timestamp = str(int(time.time()))

    # Create HMAC-SHA256 signature
    signature_payload = f"{timestamp}.{payload_json}"
    signature = hmac.new(
        secret.encode(),
        signature_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event_type,
        "X-Webhook-Timestamp": timestamp,
        "User-Agent": "NoctusAI-Webhooks/1.0",
    }

    # Create initial delivery record
    delivery_data = {
        "endpoint_id": endpoint_id,
        "event_type": event_type,
        "payload": payload,
        "attempts": 0,
        "status": "pending",
    }
    delivery_result = db.table("webhook_deliveries").insert(delivery_data).execute()
    if not delivery_result.data:
        logger.error(f"Failed to create delivery record for endpoint={endpoint_id}")
        return {}

    delivery_id = delivery_result.data[0]["id"]
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    status = "failed"

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
                response = await client.post(url, content=payload_json, headers=headers)
                response_status = response.status_code
                response_body = response.text[:2000]  # Truncate response body

                if 200 <= response.status_code < 300:
                    status = "success"
                    break

                logger.warning(
                    f"Webhook delivery failed: endpoint={endpoint_id} "
                    f"status={response.status_code} attempt={attempt}"
                )
        except httpx.TimeoutException:
            response_body = "Timeout"
            logger.warning(f"Webhook timeout: endpoint={endpoint_id} attempt={attempt}")
        except httpx.RequestError as exc:
            response_body = str(exc)[:2000]
            logger.warning(f"Webhook request error: endpoint={endpoint_id} error={exc} attempt={attempt}")

        # Exponential backoff before next retry (skip after last attempt)
        if status != "success" and attempt < MAX_RETRIES + 1:
            await asyncio.sleep(2 ** attempt)

    # Update delivery record with result
    update_data = {
        "response_status": response_status,
        "response_body": response_body,
        "attempts": attempt,
        "status": status,
    }
    updated = db.table("webhook_deliveries").update(update_data).eq("id", delivery_id).execute()

    if status == "success":
        logger.info(f"Webhook delivered: endpoint={endpoint_id} event={event_type}")
    else:
        logger.error(
            f"Webhook delivery failed permanently: endpoint={endpoint_id} "
            f"event={event_type} attempts={attempt}"
        )

    return updated.data[0] if updated.data else delivery_data


async def retry_delivery(delivery_id: str) -> dict:
    """
    Re-dispatch a failed webhook delivery.

    Fetches the original delivery record, looks up the endpoint,
    and re-sends the payload with the same event type.

    Returns the updated delivery record.
    """
    db = get_admin_client()

    delivery = db.table("webhook_deliveries").select("*").eq(
        "id", delivery_id
    ).single().execute()

    if not delivery.data:
        raise ValueError(f"Delivery not found: {delivery_id}")

    record = delivery.data
    if record.get("status") == "success":
        raise ValueError(f"Delivery already succeeded: {delivery_id}")

    endpoint = db.table("webhook_endpoints").select("*").eq(
        "id", record["endpoint_id"]
    ).single().execute()

    if not endpoint.data:
        raise ValueError(f"Endpoint not found for delivery: {delivery_id}")

    # Re-dispatch using the original event type and payload
    result = await _send_webhook(endpoint.data, record["event_type"], record["payload"])
    return result
