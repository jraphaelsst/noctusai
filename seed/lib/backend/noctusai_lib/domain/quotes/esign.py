"""Accept-and-sign: an ACCEPTED quote goes to the e-signature provider (`integrations.signature`, D4Sign).

The acceptance (consent record) and the signature are different things: acceptance is the customer saying yes
to the terms; the signature envelope is the provider's legally-evidenced document. `request_signature` renders the
accepted quote to PDF (`render.render_pdf` -- the document the customer accepted, frozen by the database), creates
the envelope and stores `signature_ref` / `signature_status` on the quote. The provider's webhook is the host's
route (it owns the secret and the URL); it calls `apply_signature_event` here.

Nothing about the provider leaks in: the adapter is injected (`make_signature_adapter(real=...)` in the host, the
Fake in tests), signer CPFs are validated BEFORE the adapter is called, and an adapter error surfaces as a typed
`assinatura_indisponivel` 502 -- never a silent "sent".
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Sequence

from noctusai_lib.integrations.documents import cpf as cpf_lib
from noctusai_lib.integrations.signature import (
    DocumentoParaAssinar,
    EventoAssinatura,
    Signatario,
    SignatureAdapter,
    SignatureError,
    is_forward_transition,
)

from ._common import Scope, now_iso
from .delivery import IssuerResolver, issuer_name
from .errors import ASSINATURA_INDISPONIVEL, ASSINATURA_INVALIDA, TRANSICAO_INVALIDA, QuotesError, conflict, invalid, not_found
from .quotes import get_party, get_row, quote_lines, record_event
from .render import quote_context, render_pdf
from .types import EventKind, QuoteStatus

logger = logging.getLogger(__name__)

#: Provider statuses that never move again.
TERMINAL = frozenset({"concluido", "cancelado", "expirado"})
_QUOTES = "quotes"


def _signers(raw: Sequence[Mapping[str, Any]]) -> list[Signatario]:
    out: list[Signatario] = []
    for i, r in enumerate(raw):
        if not cpf_lib.is_valid(str(r.get("cpf") or "")):
            raise invalid(f"signers[{i}].cpf", "CPF do signatário inválido.", ASSINATURA_INVALIDA)
        out.append(Signatario(nome=str(r["name"]).strip(), email=str(r["email"]).strip(), cpf=str(r["cpf"]), papel="comprador", ordem=0))
    return out


async def request_signature(
    s: Scope, quote_id: Any, adapter: SignatureAdapter, signers: Sequence[Mapping[str, Any]], *,
    message: Optional[str] = None, issuer: Optional[IssuerResolver] = None, user_id: Any = None,
) -> dict:
    row = get_row(s, quote_id)
    if row["status"] != QuoteStatus.ACCEPTED.value:
        raise conflict(TRANSICAO_INVALIDA, "Só é possível enviar para assinatura um orçamento aceito.", status=row["status"])
    if row.get("signature_ref") and row.get("signature_status") not in ("cancelado", "expirado"):
        raise conflict(ASSINATURA_INVALIDA, "Este orçamento já foi enviado para assinatura.", status=row.get("signature_status"))
    people = _signers(signers)
    party = get_party(s, row["party_id"]) or {}
    ctx = quote_context(row, quote_lines(s, row["id"]), party_name=str(party.get("legal_name") or ""), issuer_name=issuer_name(issuer, s.org_id))
    doc = DocumentoParaAssinar(nome=f"{row['number']}-v{row['version']}.pdf", conteudo=render_pdf(ctx), mime_type="application/pdf")
    try:
        envelope = await adapter.criar_envelope(doc, people, mensagem=message)
    except SignatureError as exc:
        logger.exception("quotes: signature envelope failed for quote %s (org %s)", row["id"], s.org_id)
        raise QuotesError(ASSINATURA_INDISPONIVEL, "Não foi possível criar o envelope de assinatura.", 502) from exc
    s.tbl(_QUOTES).update({"signature_ref": envelope.external_id, "signature_status": "pendente", "updated_at": now_iso()}).eq(
        "org_id", s.org_id
    ).eq("id", str(row["id"])).execute()
    record_event(s, row["id"], EventKind.SIGNATURE_REQUESTED, actor=user_id, detail={"provider": envelope.provedor, "external_id": envelope.external_id})
    return {"external_id": envelope.external_id, "status": "pendente", "link": envelope.link_assinatura, "provider": envelope.provedor}


def _apply(s: Scope, row: Mapping[str, Any], event: EventoAssinatura) -> dict:
    current = row.get("signature_status")
    if event.status != current and not is_forward_transition(current, event.status, terminais=TERMINAL):
        logger.warning("quotes: ignoring regressive signature status %s -> %s for quote %s", current, event.status, row["id"])
        return {"status": current, "changed": False}
    if event.status == current:
        return {"status": current, "changed": False}
    s.tbl(_QUOTES).update({"signature_status": event.status, "updated_at": now_iso()}).eq("org_id", s.org_id).eq("id", str(row["id"])).execute()
    record_event(s, row["id"], EventKind.SIGNATURE_UPDATED, from_status=current, to_status=event.status, detail={"external_id": event.external_id})
    return {"status": event.status, "changed": True}


async def refresh_signature(s: Scope, quote_id: Any, adapter: SignatureAdapter) -> dict:
    """Ask the provider where the envelope stands (the pull twin of the webhook)."""
    row = get_row(s, quote_id)
    if not row.get("signature_ref"):
        raise not_found("Assinatura")
    try:
        event = await adapter.consultar(row["signature_ref"])
    except SignatureError as exc:
        raise QuotesError(ASSINATURA_INDISPONIVEL, "Não foi possível consultar o provedor de assinatura.", 502) from exc
    return {**_apply(s, row, event), "external_id": row["signature_ref"]}


def apply_signature_event(s: Scope, event: EventoAssinatura) -> Optional[dict]:
    """The webhook entry point: apply a VERIFIED provider event to the quote that owns the envelope (`None` = not ours)."""
    rows = s.rows(_QUOTES, eq={"signature_ref": event.external_id})
    if not rows:
        return None
    return _apply(s, rows[0], event)


__all__ = ["TERMINAL", "apply_signature_event", "refresh_signature", "request_signature"]
