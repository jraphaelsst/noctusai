"""`ResendEmailSender` — the Real `EmailSender` over Resend's HTTP API.

Same contract as `SmtpEmailSender`: `send(...)` RAISES on failure
(`EmailSendError`), returns `SentEmail` with Resend's message id. Added
2026-10-10 for social-wiring email marketing P1b (double opt-in confirmation
mail): the transactional family had SMTP only, while the platform's mail
provider is Resend (`digest` already speaks it for scheduled narratives).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .errors import EmailNotConfigured, EmailSendError
from .types import OutgoingEmail, SentEmail

RESEND_EMAILS_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class ResendConfig:
    api_key: str
    from_email: str
    from_name: str = ""

    def __post_init__(self) -> None:
        if not self.api_key or not self.from_email:
            raise EmailNotConfigured("Resend needs api_key and from_email")

    @property
    def from_header(self) -> str:
        return f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email


class ResendEmailSender:
    def __init__(self, config: ResendConfig, *, http_client_factory: Callable[[], Any] = httpx.AsyncClient):
        self._config = config
        self._http_client_factory = http_client_factory  # seam: the Resend HTTP boundary

    def _payload(self, email: OutgoingEmail) -> dict[str, Any]:
        headers = dict(email.headers)
        if email.message_id:
            headers["Message-ID"] = email.message_id
        payload: dict[str, Any] = {
            "from": self._config.from_header,
            "to": list(email.to),
            "subject": email.subject,
        }
        for key, value in (("html", email.html), ("text", email.text), ("reply_to", email.reply_to)):
            if value:
                payload[key] = value
        if email.cc:
            payload["cc"] = list(email.cc)
        if email.bcc:
            payload["bcc"] = list(email.bcc)
        if headers:
            payload["headers"] = headers
        if email.attachments:
            payload["attachments"] = [
                {"filename": a.filename, "content": base64.b64encode(a.content).decode("ascii")}
                for a in email.attachments
            ]
        return payload

    async def send(self, email: OutgoingEmail) -> SentEmail:
        if not email.to:
            raise EmailSendError("no recipients")
        try:
            async with self._http_client_factory() as client:
                resp = await client.post(
                    RESEND_EMAILS_URL,
                    json=self._payload(email),
                    headers={"Authorization": f"Bearer {self._config.api_key}"},
                    timeout=30,
                )
        except Exception as exc:  # transport failure — surfaced, never swallowed
            raise EmailSendError(f"resend transport error: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise EmailSendError(f"resend HTTP {resp.status_code}: {str(getattr(resp, 'text', ''))[:200]}")
        message_id = (resp.json() or {}).get("id") or email.message_id
        if not message_id:
            raise EmailSendError("resend accepted the email but returned no id")
        references = email.headers.get("References")
        return SentEmail(
            message_id=message_id,
            in_reply_to=email.headers.get("In-Reply-To"),
            references=tuple(references.split()) if references else (),
        )


__all__ = ["RESEND_EMAILS_URL", "ResendConfig", "ResendEmailSender"]
