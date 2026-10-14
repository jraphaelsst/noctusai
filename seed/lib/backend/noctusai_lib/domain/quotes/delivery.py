"""Sending a quote: the accept link by e-mail (with the PDF attached) or as a link to hand over yourself.

Order of operations (each step leaves a state you can reason about):

1. validate (current version, sendable status, >= 1 line, not past validity, a recipient for e-mail);
2. `draft -> sent` (conditional UPDATE -- the lock; a resend of `sent` / `viewed` only refreshes `sent_at`);
3. mint the signed token + build the URL (the host owns the public page: `accept_url(token) -> https://...`);
4. e-mail. If the send FAILS and step 2 moved the quote out of draft, step 2 is undone (back to `draft`) and the
   caller gets 502 `envio_falhou` -- a quote is never left `sent` that nobody was told about.

The link channel does steps 1-3 and returns the URL (staff copy it into WhatsApp / a chat). The URL is a bearer
credential: it is returned to the authenticated staff member only, never logged.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any, Callable, Mapping, Optional

from noctusai_lib.integrations.email.types import Attachment, EmailSender, OutgoingEmail

from ._common import Scope, now_iso
from .errors import (
    EMAIL_INDISPONIVEL,
    ENVIO_FALHOU,
    ORCAMENTO_EXPIRADO,
    ORCAMENTO_SUBSTITUIDO,
    ORCAMENTO_VAZIO,
    TRANSICAO_INVALIDA,
    QuotesError,
    conflict,
    invalid,
)
from .links import mint_token
from .money import money_text
from .quotes import expire_if_due, get_party, get_quote, get_row, is_past_validity, quote_lines, record_event, transition
from .render import quote_context, render_pdf
from .types import EventKind, QuoteStatus

logger = logging.getLogger(__name__)

SENDABLE = (QuoteStatus.DRAFT.value, QuoteStatus.SENT.value, QuoteStatus.VIEWED.value)
IssuerResolver = Callable[[str], Mapping[str, Any]]


def issuer_name(issuer: Optional[IssuerResolver], org_id: str) -> str:
    """The seller's display name (host-resolved; a quote with no name configured says so honestly: empty)."""
    return str((issuer(org_id) if issuer else {}).get("name") or "")


def _email_bodies(ctx: Mapping[str, Any], url: str, message: Optional[str]) -> tuple[str, str]:
    intro = f"Olá, {ctx['party_name']}. Segue o orçamento {ctx['number']} no valor de {ctx['total']}."
    until = f" Válido até {ctx['valid_until']}." if ctx["valid_until"] else ""
    extra = f"\n\n{message.strip()}" if message and message.strip() else ""
    text = f"{intro}{until}{extra}\n\nPara ver os detalhes e aceitar ou recusar online:\n{url}\n\n— {ctx['issuer_name']}"
    e = escape
    html = (
        f"<p>{e(intro)}{e(until)}</p>"
        + (f"<p>{e(message.strip())}</p>" if message and message.strip() else "")
        + f"<p><a href=\"{e(url)}\">Ver, aceitar ou recusar o orçamento</a></p><p>— {e(ctx['issuer_name'])}</p>"
    )
    return text, html


async def send_quote(
    s: Scope,
    quote_id: Any,
    *,
    channel: str,
    to: Optional[str],
    message: Optional[str],
    link_secret: str,
    accept_url: Callable[[str], str],
    email_sender: Optional[EmailSender],
    issuer: Optional[IssuerResolver] = None,
    user_id: Any = None,
) -> dict:
    """Send (or resend) the quote. Returns `{quote, channel, url, sent_to}`."""
    row = expire_if_due(s, get_row(s, quote_id))
    if not row.get("is_current"):
        raise conflict(ORCAMENTO_SUBSTITUIDO, "Esta versão foi substituída por uma mais recente.", status=row["status"])
    if row["status"] == QuoteStatus.EXPIRED.value or (row["status"] in SENDABLE and is_past_validity(s, row)):
        raise conflict(ORCAMENTO_EXPIRADO, "A validade do orçamento já passou: crie uma nova versão.", status=row["status"])
    if row["status"] not in SENDABLE:
        raise conflict(TRANSICAO_INVALIDA, "Este orçamento não pode mais ser enviado.", status=row["status"])
    lines = quote_lines(s, row["id"])
    if not lines:
        raise invalid("lines", "Adicione ao menos uma linha antes de enviar.", ORCAMENTO_VAZIO)
    party = get_party(s, row["party_id"]) or {}
    recipient = (to or party.get("email") or "").strip() or None
    if channel == "email":
        if email_sender is None:
            raise QuotesError(EMAIL_INDISPONIVEL, "O envio de e-mail não está configurado.", 503)
        if recipient is None:
            raise invalid("to", "Informe o e-mail do destinatário (o cliente não tem e-mail cadastrado).", EMAIL_INDISPONIVEL)

    token = mint_token(link_secret, s.cfg, row)  # 503 before any state change when the host has no secret
    url = accept_url(token)
    was_draft = row["status"] == QuoteStatus.DRAFT.value
    now = now_iso()
    sent = transition(
        s, row, QuoteStatus.SENT.value if was_draft else row["status"], expect=[row["status"]],
        extra={"sent_at": now, "last_sent_to": recipient if channel == "email" else row.get("last_sent_to")},
    )
    if sent is None:
        raise conflict(TRANSICAO_INVALIDA, "O orçamento mudou de situação: recarregue e tente de novo.")

    if channel == "email":
        ctx = quote_context(sent, lines, party_name=str(party.get("legal_name") or ""), issuer_name=issuer_name(issuer, s.org_id))
        text, html = _email_bodies(ctx, url, message)
        try:
            pdf = render_pdf(ctx)
            await email_sender.send(  # type: ignore[union-attr]
                OutgoingEmail(
                    to=[recipient],  # type: ignore[list-item]
                    subject=f"Orçamento {ctx['number']} — {money_text(sent['total_cents'], sent.get('currency') or 'BRL')}",
                    html=html, text=text,
                    attachments=[Attachment(filename=f"{sent['number']}-v{sent['version']}.pdf", content=pdf, mime_type="application/pdf")],
                )
            )
        except Exception as exc:  # noqa: BLE001 - any transport / render failure: undo the draft->sent claim, tell the caller
            logger.exception("quotes: e-mail of quote %s failed (org %s)", row["id"], s.org_id)
            if was_draft:
                s.tbl("quotes").update({"status": "draft", "sent_at": None, "last_sent_to": None, "updated_at": now_iso()}).eq(
                    "org_id", s.org_id
                ).eq("id", str(row["id"])).eq("status", "sent").execute()
            raise QuotesError(ENVIO_FALHOU, "Não foi possível enviar o e-mail. Tente novamente.", 502) from exc

    record_event(
        s, row["id"], EventKind.SENT, from_status=row["status"], to_status=sent["status"], actor=user_id,
        detail={"channel": channel, "to": recipient if channel == "email" else None},
    )
    return {"quote": get_quote(s, row["id"]), "channel": channel, "url": url, "sent_to": recipient if channel == "email" else None}


__all__ = ["IssuerResolver", "issuer_name", "send_quote"]
