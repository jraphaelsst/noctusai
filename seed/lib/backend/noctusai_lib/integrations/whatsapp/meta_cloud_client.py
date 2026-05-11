"""Meta WhatsApp Cloud API HTTP client (async) + colocated Fake.

Sibling of `WahaClient` — covers the other major outbound transport for
WhatsApp (Meta Cloud API, `https://graph.facebook.com/v{X}/{phone_number_id}/messages`).
Mirrors the Protocol+Fake+Real+factory shape per
`KB § PATTERNS/seed-fake-real-adapter.md`.

Key shape difference vs `WahaClient.send_text(chat_id, text)`:
the Meta Cloud API addresses recipients by **phone** (international
digits-only), not by `<digits>@c.us` chat_id. Both adapters' `send_text`
return the parsed JSON body of the API response; consumer code is
responsible for envelope shaping.
"""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_BASE_URL = "https://graph.facebook.com/v18.0"


class MetaCloudClient:
    """Meta WhatsApp Cloud API HTTP client (async send_text only).

    The Meta Cloud API surface today only needs outbound text sending
    in this codebase; media download / inbound parsing land later under
    the same `WhatsAppInboundMessage` shape per
    `KB § PATTERNS/whatsapp-chatbot-seed.md §1`.
    """

    def __init__(
        self,
        phone_number_id: str,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.phone_number_id = phone_number_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_body(self, phone: str, text: str) -> dict[str, Any]:
        """Meta Cloud API message body shape."""
        return {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text},
        }

    @property
    def send_url(self) -> str:
        return f"{self.base_url}/{self.phone_number_id}/messages"

    async def send_text(self, phone: str, text: str) -> dict[str, Any]:
        """POST a text message; returns parsed Meta response JSON.

        Raises `httpx.HTTPStatusError` on non-2xx. Consumer code is
        responsible for catching and shaping the legacy envelope.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.send_url,
                headers=self._headers(),
                json=self._build_body(phone, text),
            )
            response.raise_for_status()
            return response.json()


class FakeMetaCloudClient:
    """Deterministic in-memory Meta Cloud API stand-in.

    Records sent messages, returns the canonical Meta response envelope
    `{"messages": [{"id": "fake-meta-<N>"}]}`. Use as the dev/local
    fallback when no `api_key` is configured, or in tests as a
    deterministic stand-in. Same shape as `FakeWahaClient` per
    `KB § PATTERNS/seed-fake-real-adapter.md`.
    """

    def __init__(
        self,
        phone_number_id: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.phone_number_id = phone_number_id
        self.base_url = base_url.rstrip("/")
        self.sent_messages: list[dict[str, Any]] = []

    async def send_text(self, phone: str, text: str) -> dict[str, Any]:
        message_id = f"fake-meta-{len(self.sent_messages) + 1}"
        record = {
            "phone": phone,
            "text": text,
            "message_id": message_id,
        }
        self.sent_messages.append(record)
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": phone, "wa_id": phone}],
            "messages": [{"id": message_id}],
        }

    def clear(self) -> None:
        """Reset between test cases."""
        self.sent_messages.clear()
