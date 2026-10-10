"""Double opt-in (P1b(d), 2026-10-10) — the ONE place opt-in state is decided.

* **Initial state.** A contact created through ``source in ('form', 'api')``, or
  imported with ``double_opt_in=true``, starts ``email_optin='pending'``; every
  other path (manual, WhatsApp, ERP sync, plain import) is ``'not_required'``
  (also the column default for every pre-existing row, migration 244).
* **Send gate.** :func:`receives_marketing_email` is the single predicate both
  recipient-resolution paths call (``SendService.queue_campaign_sends`` and the
  automation executor's ``send_email`` step): only ``status='active'`` AND
  ``email_optin in ('not_required', 'confirmed')`` receive marketing email.
  An allowlist, so an unknown state never mails by accident.
* **Confirmation mail.** A ``signed_tokens`` purpose ``email_confirm`` link
  (7-day TTL) to the public ``/confirmar-email/{token}`` page, sent through the
  seed ``EmailSender`` (Resend Real; Fake in tests via the router's dependency
  seam). Nothing is ever faked: no Resend key / no ``FRONTEND_BASE_URL`` / no
  ``JWT_SECRET`` ⇒ the contact stays ``pending``, the failure is logged at ERROR
  and returned to the caller as ``{"sent": false, "reason": ...}``.
"""
from __future__ import annotations

import html
import logging
from typing import Any, Optional

from noctusai_lib.integrations.email import (
    EmailNotConfigured,
    EmailSender,
    EmailSendError,
    OutgoingEmail,
    ResendConfig,
    make_email_sender,
)
from noctusai_lib.security import signed_tokens

logger = logging.getLogger(__name__)

OPTIN_NOT_REQUIRED = "not_required"
OPTIN_PENDING = "pending"
OPTIN_CONFIRMED = "confirmed"

DOUBLE_OPTIN_SOURCES = frozenset({"form", "api"})
MARKETING_OPTIN_STATES = frozenset({OPTIN_NOT_REQUIRED, OPTIN_CONFIRMED})

TOKEN_PURPOSE = "email_confirm"
CONFIRM_TTL_SECONDS = 7 * 24 * 3600
CONFIRM_PATH = "/confirmar-email/"

REASON_NO_SENDER = (
    "e-mail de confirmação NÃO enviado: RESEND_API_KEY (ou DEFAULT_FROM_EMAIL) não configurado "
    "— o contato continua aguardando confirmação"
)
REASON_NO_LINK = (
    "e-mail de confirmação NÃO enviado: FRONTEND_BASE_URL e JWT_SECRET precisam estar "
    "configurados para gerar o link — o contato continua aguardando confirmação"
)
REASON_NO_EMAIL = "e-mail de confirmação NÃO enviado: o contato não tem endereço de e-mail"


def initial_optin(source: Optional[str], double_opt_in: bool = False) -> str:
    """The opt-in state a NEW contact starts in."""
    if double_opt_in or (source or "") in DOUBLE_OPTIN_SOURCES:
        return OPTIN_PENDING
    return OPTIN_NOT_REQUIRED


def receives_marketing_email(contact: Optional[dict]) -> bool:
    """The send gate: active AND opt-in not pending (allowlist)."""
    if not contact or not contact.get("email"):
        return False
    return contact.get("status") == "active" and contact.get("email_optin") in MARKETING_OPTIN_STATES


# ── signed confirmation link ────────────────────────────────────────────────

def make_token(secret: str, org_id: str, contact_id: str, email: str) -> str:
    """Purpose-bound, 7-day confirmation token. Raises ValueError on an empty secret."""
    return signed_tokens.sign(
        TOKEN_PURPOSE,
        {"org_id": org_id, "contact_id": contact_id, "email": email},
        secret,
        ttl_seconds=CONFIRM_TTL_SECONDS,
    )


def verify_token(secret: str, token: str) -> Optional[dict]:
    """Payload of a valid, unexpired ``email_confirm`` token, else None."""
    data = signed_tokens.verify(TOKEN_PURPOSE, token, secret)
    if data and all(data.get(k) for k in ("org_id", "contact_id", "email")):
        return data
    return None


def confirm_url(settings: Any, org_id: str, contact_id: str, email: str) -> Optional[str]:
    """The public confirmation URL, or None when it cannot be built (no
    ``FRONTEND_BASE_URL`` or an empty signing secret)."""
    base = (getattr(settings, "frontend_base_url", "") or "").rstrip("/")
    if not base:
        return None
    try:
        token = make_token(getattr(settings, "jwt_secret", ""), org_id, contact_id, email)
    except ValueError:  # empty JWT_SECRET: a token signed with "" is forgeable
        return None
    return f"{base}{CONFIRM_PATH}{token}"


# ── the sender seam ─────────────────────────────────────────────────────────

def build_confirmation_sender(settings: Any) -> Optional[EmailSender]:
    """The Real Resend sender through the seed factory, or None when Resend is
    not configured. Deliberately NOT ``make_email_sender(None)`` — that returns
    a Fake, and a Fake in production would report a confirmation as sent."""
    try:
        config = ResendConfig(
            api_key=getattr(settings, "resend_api_key", "") or "",
            from_email=getattr(settings, "default_from_email", "") or "",
            from_name=getattr(settings, "default_from_name", "") or "",
        )
    except EmailNotConfigured:
        return None
    return make_email_sender(config)


def _render(url: str, nome: Optional[str]) -> tuple[str, str, str]:
    saudacao = f"Olá, {nome}!" if nome else "Olá!"
    subject = "Confirme seu e-mail"
    text = (
        f"{saudacao}\n\n"
        "Recebemos seu cadastro para receber nossos e-mails. Para confirmar seu endereço, "
        f"acesse o link abaixo (válido por 7 dias):\n\n{url}\n\n"
        "Se você não fez esse cadastro, ignore esta mensagem — você não receberá nenhum e-mail nosso."
    )
    safe_url = html.escape(url, quote=True)
    body = (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#111827">'
        f"<p>{html.escape(saudacao)}</p>"
        "<p>Recebemos seu cadastro para receber nossos e-mails. Para confirmar seu endereço, "
        "clique no botão abaixo (o link vale por 7 dias):</p>"
        f'<p style="text-align:center;margin:28px 0"><a href="{safe_url}" '
        'style="background:#2563eb;color:#fff;padding:12px 24px;border-radius:6px;'
        'text-decoration:none;display:inline-block">Confirmar e-mail</a></p>'
        f'<p style="font-size:12px;color:#6b7280">Ou copie este endereço no navegador: {safe_url}</p>'
        '<p style="font-size:12px;color:#6b7280">Se você não fez esse cadastro, ignore esta mensagem '
        "— você não receberá nenhum e-mail nosso.</p></div>"
    )
    return subject, text, body


async def send_confirmation(sender: Optional[EmailSender], settings: Any, contact: dict) -> dict:
    """Send ``contact`` its confirmation email. Returns ``{"sent": bool,
    "reason": str | None}``; never raises and never fakes success — every
    not-sent outcome is logged at ERROR and carries its reason."""
    email = contact.get("email")
    org_id, contact_id = contact.get("org_id"), contact.get("id")
    if not email:
        reason = REASON_NO_EMAIL
    elif sender is None:
        reason = REASON_NO_SENDER
    else:
        url = confirm_url(settings, str(org_id), str(contact_id), email)
        if url is None:
            reason = REASON_NO_LINK
        else:
            subject, text, body = _render(url, contact.get("nome"))
            try:
                await sender.send(OutgoingEmail(to=[email], subject=subject, html=body, text=text))
            except EmailSendError as exc:
                reason = f"e-mail de confirmação NÃO enviado: falha no envio ({exc})"
            else:
                logger.info("double opt-in: confirmation sent to contact %s (org=%s)", contact_id, org_id)
                return {"sent": True, "reason": None}
    logger.error("double opt-in: contact %s (org=%s) stays pending — %s", contact_id, org_id, reason)
    return {"sent": False, "reason": reason}
