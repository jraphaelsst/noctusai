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
        waba_id: str = "",
    ):
        self.phone_number_id = phone_number_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        # WhatsApp Business Account id: only the template-management calls address it.
        self.waba_id = waba_id

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

    # -- template send / profile / template management (Cloud API only) ------------------------

    @staticmethod
    def build_template_body(
        phone: str, template_name: str, language: str, body_params: list[str] | None
    ) -> dict[str, Any]:
        """Meta Cloud API `type=template` body; `body_params` fill {{1}}..{{n}} in order."""
        template: dict[str, Any] = {"name": template_name, "language": {"code": language}}
        if body_params:
            template["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in body_params]}
            ]
        return {"messaging_product": "whatsapp", "to": phone, "type": "template", "template": template}

    @staticmethod
    def build_profile_body(profile: dict[str, Any]) -> dict[str, Any]:
        """Business-profile update body. Meta's fields: about (<=139), description (<=512), address,
        email, websites (list). The display NAME is not editable through this endpoint (Business Manager)."""
        body: dict[str, Any] = {"messaging_product": "whatsapp"}
        for key in ("about", "description", "address", "email"):
            if profile.get(key):
                body[key] = profile[key]
        if profile.get("websites"):
            body["websites"] = list(profile["websites"])
        return body

    @staticmethod
    def build_create_template_body(
        name: str, category: str, language: str, body_text: str, example_params: list[str] | None
    ) -> dict[str, Any]:
        component: dict[str, Any] = {"type": "BODY", "text": body_text}
        if example_params:
            component["example"] = {"body_text": [list(example_params)]}
        return {"name": name, "category": category, "language": language, "components": [component]}

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers(), json=body)
            response.raise_for_status()
            return response.json()

    async def send_template(
        self, phone: str, template_name: str, language: str = "pt_BR", body_params: list[str] | None = None
    ) -> dict[str, Any]:
        """POST an approved template message (the only way to open a conversation outside the 24 h window)."""
        return await self._post(self.send_url, self.build_template_body(phone, template_name, language, body_params))

    async def update_business_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        """POST /{phone_number_id}/whatsapp_business_profile."""
        return await self._post(
            f"{self.base_url}/{self.phone_number_id}/whatsapp_business_profile", self.build_profile_body(profile)
        )

    async def create_template(
        self, name: str, category: str, language: str, body_text: str, example_params: list[str] | None = None
    ) -> dict[str, Any]:
        """POST /{waba_id}/message_templates -- submit a template for Meta's review (returns id + status)."""
        if not self.waba_id:
            raise ValueError("create_template needs a waba_id")
        return await self._post(
            f"{self.base_url}/{self.waba_id}/message_templates",
            self.build_create_template_body(name, category, language, body_text, example_params),
        )


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
        waba_id: str = "",
    ):
        self.phone_number_id = phone_number_id
        self.base_url = base_url.rstrip("/")
        self.waba_id = waba_id
        self.sent_messages: list[dict[str, Any]] = []
        self.sent_templates: list[dict[str, Any]] = []
        self.profile_updates: list[dict[str, Any]] = []
        self.created_templates: list[dict[str, Any]] = []

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

    async def send_template(
        self, phone: str, template_name: str, language: str = "pt_BR", body_params: list[str] | None = None
    ) -> dict[str, Any]:
        message_id = f"fake-meta-tpl-{len(self.sent_templates) + 1}"
        self.sent_templates.append({
            "phone": phone, "template_name": template_name, "language": language,
            "body_params": list(body_params or []), "message_id": message_id,
        })
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": phone, "wa_id": phone}],
            "messages": [{"id": message_id}],
        }

    async def update_business_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        self.profile_updates.append(MetaCloudClient.build_profile_body(profile))
        return {"success": True}

    async def create_template(
        self, name: str, category: str, language: str, body_text: str, example_params: list[str] | None = None
    ) -> dict[str, Any]:
        template_id = f"fake-meta-template-{len(self.created_templates) + 1}"
        self.created_templates.append({
            "id": template_id, "name": name, "category": category, "language": language,
            "body_text": body_text, "example_params": list(example_params or []),
        })
        return {"id": template_id, "status": "PENDING", "category": category}

    def clear(self) -> None:
        """Reset between test cases."""
        self.sent_messages.clear()
        self.sent_templates.clear()
        self.profile_updates.clear()
        self.created_templates.clear()
