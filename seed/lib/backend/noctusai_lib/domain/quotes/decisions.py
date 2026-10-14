"""Accept / reject a quote -- the customer-consent record, and the convert-on-accept hand-off.

One path for both channels (`public_link`: the customer on the signed link, `staff`: an operator recording an
acceptance obtained elsewhere). The order of operations is the whole point:

1. **Claim.** A conditional `UPDATE ... WHERE status IN ('sent','viewed')` is the lock. The second of two
   concurrent decisions matches zero rows and gets 409; a partial unique index (one `accepted` per quote root) is
   the backstop across versions.
2. **Record.** The append-only acceptance row: who typed what name, when, from which IP / user agent, the EXACT
   consent sentence shown, and the sha256 of the terms decided on (the quote cannot change after `draft`, so the
   hash is reproducible). If this insert fails, step 1 is undone -- the status is mutable, the record is not.
3. **Convert** (accept only). The host's `QuoteAcceptHandler` runs; a failure is stored on the quote
   (`conversion_status = failed`) and NEVER rolls back the customer's acceptance.

Nothing here reads the caller's org from the request: the `Scope` carries the org the token / session proved.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ._common import Scope, dec, first, new_id, now_iso
from .errors import (
    CONSENTIMENTO_OBRIGATORIO,
    CONVERSAO_INDISPONIVEL,
    NOME_OBRIGATORIO,
    ORCAMENTO_ENCERRADO,
    ORCAMENTO_EXPIRADO,
    ORCAMENTO_SUBSTITUIDO,
    TRANSICAO_INVALIDA,
    conflict,
    invalid,
)
from .handler import NoopQuoteAcceptHandler, QuoteAcceptContext, QuoteAcceptHandler
from .money import money_text
from .quotes import (
    effective_convert_to,
    expire_if_due,
    get_party,
    get_row,
    present_line,
    present_quote,
    quote_lines,
    record_event,
    transition,
)
from .types import Channel, ConversionStatus, ConvertTo, Decision, EventKind, OPEN_STATUSES, QuoteStatus

logger = logging.getLogger(__name__)

_ACCEPTANCES = "acceptances"
_QUOTES = "quotes"
_ERROR_CAP = 300


def consent_text(quote: Mapping[str, Any], name: str) -> str:
    """The sentence the customer agrees to -- stored VERBATIM on the acceptance (what was shown is what is recorded)."""
    return (
        f"Eu, {name.strip()}, li e aceito o orçamento {quote['number']} (versão {quote['version']}), "
        f"no valor total de {money_text(quote['total_cents'], quote.get('currency') or 'BRL')}, "
        "nos termos e condições nele descritos."
    )


def content_sha256(quote: Mapping[str, Any], lines: list[Mapping[str, Any]]) -> str:
    """Hash of WHAT was offered (canonical JSON): number, version, party, validity, terms, money and every line."""
    doc = {
        "number": quote["number"], "version": quote["version"], "party_id": str(quote["party_id"]),
        "currency": quote.get("currency"), "valid_until": str(quote.get("valid_until") or "")[:10],
        "title": quote.get("title"), "notes": quote.get("notes"), "terms": quote.get("terms"),
        "subtotal_cents": quote["subtotal_cents"], "discount_cents": quote["discount_cents"], "total_cents": quote["total_cents"],
        "lines": [
            {
                "position": int(ln.get("position") or 0), "item_id": str(ln["item_id"]) if ln.get("item_id") else None,
                "description": ln["description"], "unit": ln.get("unit"), "kind": ln.get("kind"),
                "qty": format(dec(ln["qty"]), "f"), "unit_price_cents": ln["unit_price_cents"],
                "discount_cents": ln["discount_cents"], "total_cents": ln["total_cents"],
            }
            for ln in sorted(lines, key=lambda r: int(r.get("position") or 0))
        ],
    }
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _decidable(s: Scope, quote_id: Any) -> dict:
    """The quote row, only if a decision is still possible -- else the precise 409 (expired / superseded / closed)."""
    row = expire_if_due(s, get_row(s, quote_id))
    status = row["status"]
    if status in OPEN_STATUSES and row.get("is_current"):
        return row
    if status == QuoteStatus.EXPIRED.value:
        raise conflict(ORCAMENTO_EXPIRADO, "Este orçamento expirou: peça uma nova versão.", status=status)
    if status == QuoteStatus.SUPERSEDED.value or (not row.get("is_current") and status in OPEN_STATUSES):
        raise conflict(ORCAMENTO_SUBSTITUIDO, "Esta versão foi substituída por uma mais recente.", status=status)
    if status == QuoteStatus.DRAFT.value:
        raise conflict(TRANSICAO_INVALIDA, "O orçamento ainda não foi enviado.", status=status)
    raise conflict(ORCAMENTO_ENCERRADO, "Este orçamento já foi decidido.", status=status)


def _revert(s: Scope, row: Mapping[str, Any], decided_to: str) -> None:
    """Undo the claim after the consent record failed to write (status is mutable; the record is not)."""
    patch = {"status": row["status"], "accepted_at": None, "rejected_at": None, "rejection_reason": None,
             "conversion_status": ConversionStatus.NONE.value, "updated_at": now_iso()}
    s.tbl(_QUOTES).update(patch).eq("org_id", s.org_id).eq("id", str(row["id"])).eq("status", decided_to).execute()


def _decide(
    s: Scope, quote_id: Any, decision: Decision, *, channel: Channel, signer_name: str, reason: Optional[str],
    consent: Optional[str], ip: Optional[str], user_agent: Optional[str], user_id: Any,
) -> tuple[dict, dict, list[dict]]:
    row = _decidable(s, quote_id)
    lines = quote_lines(s, row["id"])
    digest = content_sha256(row, lines)
    now = datetime.now(timezone.utc).isoformat()
    accepted = decision is Decision.ACCEPTED
    effective = effective_convert_to(row, lines)
    extra: dict[str, Any] = (
        {"accepted_at": now, "conversion_status": ConversionStatus.NONE.value if effective == ConvertTo.NONE.value else ConversionStatus.PENDING.value}
        if accepted else {"rejected_at": now, "rejection_reason": reason}
    )
    target = QuoteStatus.ACCEPTED.value if accepted else QuoteStatus.REJECTED.value
    claimed = transition(s, row, target, expect=OPEN_STATUSES, extra=extra)
    if claimed is None:
        raise conflict(ORCAMENTO_ENCERRADO, "Este orçamento já foi decidido.", status=get_row(s, row["id"])["status"])
    acceptance = {
        "id": new_id(), "org_id": s.org_id, "quote_id": str(row["id"]), "decision": decision.value, "channel": channel.value,
        "signer_name": signer_name.strip(), "reason": reason, "consent_text": consent, "content_sha256": digest,
        "ip": (ip or None), "user_agent": (user_agent or "")[:300] or None, "decided_by": str(user_id) if user_id else None,
        "decided_at": now,
    }
    try:
        saved = first(s.tbl(_ACCEPTANCES).insert(acceptance).execute()) or acceptance
    except Exception:
        _revert(s, row, target)
        raise
    record_event(
        s, row["id"], EventKind.ACCEPTED if accepted else EventKind.REJECTED, from_status=row["status"], to_status=target,
        actor=user_id, detail={"channel": channel.value, "content_sha256": digest},
    )
    return claimed, saved, lines


def accept_quote(
    s: Scope, quote_id: Any, *, channel: Channel, signer_name: str, agree: bool = False, note: Optional[str] = None,
    ip: Optional[str] = None, user_agent: Optional[str] = None, user_id: Any = None,
    handler: Optional[QuoteAcceptHandler] = None,
) -> dict:
    """Accept. `public_link` REQUIRES `agree` (consent is explicit) and a name; `staff` records an offline acceptance."""
    name = (signer_name or "").strip()
    if len(name) < 2:
        raise invalid("name", "Informe o seu nome completo.", NOME_OBRIGATORIO)
    if channel is Channel.PUBLIC_LINK and not agree:
        raise invalid("agree", "É necessário concordar com os termos para aceitar.", CONSENTIMENTO_OBRIGATORIO)
    row = _decidable(s, quote_id)
    consent = consent_text(row, name) if channel is Channel.PUBLIC_LINK else None
    claimed, acceptance, lines = _decide(
        s, quote_id, Decision.ACCEPTED, channel=channel, signer_name=name, reason=(note or None), consent=consent,
        ip=ip, user_agent=user_agent, user_id=user_id,
    )
    final = run_conversion(s, claimed, lines, acceptance, handler or NoopQuoteAcceptHandler())
    return {"quote": final, "lines": lines, "acceptance": acceptance}


def reject_quote(
    s: Scope, quote_id: Any, *, channel: Channel, signer_name: Optional[str] = None, reason: Optional[str] = None,
    ip: Optional[str] = None, user_agent: Optional[str] = None, user_id: Any = None,
) -> dict:
    cleaned = (reason or "").strip() or None
    if channel is Channel.STAFF and not cleaned:
        from .errors import MOTIVO_OBRIGATORIO

        raise invalid("reason", "Informe o motivo da recusa.", MOTIVO_OBRIGATORIO)
    claimed, acceptance, lines = _decide(
        s, quote_id, Decision.REJECTED, channel=channel, signer_name=(signer_name or "").strip() or "(não informado)",
        reason=cleaned, consent=None, ip=ip, user_agent=user_agent, user_id=user_id,
    )
    return {"quote": claimed, "lines": lines, "acceptance": acceptance}


def get_acceptance(s: Scope, quote_id: Any) -> Optional[dict]:
    rows = s.rows(_ACCEPTANCES, eq={"quote_id": str(quote_id)})
    return rows[0] if rows else None


# ─── convert-on-accept ───────────────────────────────────────────────────────


def run_conversion(
    s: Scope, quote: dict, lines: list[dict], acceptance: Mapping[str, Any], handler: QuoteAcceptHandler
) -> dict:
    """Hand the accepted quote to the host's handler. NEVER raises: a failure is recorded (`failed`) and retryable."""
    effective = effective_convert_to(quote, lines)
    if effective == ConvertTo.NONE.value:
        return quote
    ctx = QuoteAcceptContext(
        org_id=s.org_id,
        quote=present_quote(quote, lines, get_party(s, quote["party_id"])),
        lines=tuple(present_line(ln) for ln in lines),
        acceptance=dict(acceptance),
        convert_to=effective,
    )
    patch: dict[str, Any]
    try:
        result = handler.handle(ctx)
    except Exception as exc:  # noqa: BLE001 - the handler is host code; its failure must not undo the acceptance
        logger.exception("quotes: convert-on-accept handler failed for quote %s (org %s)", quote["id"], s.org_id)
        patch = {"conversion_status": ConversionStatus.FAILED.value, "conversion_kind": effective,
                 "conversion_error": f"{type(exc).__name__}: {exc}"[:_ERROR_CAP]}
        event, detail = EventKind.CONVERSION_FAILED, {"error": patch["conversion_error"]}
    else:
        if result is None:
            patch = {"conversion_status": ConversionStatus.SKIPPED.value, "conversion_kind": effective, "conversion_error": None}
            event, detail = None, {}
        else:
            patch = {"conversion_status": ConversionStatus.DONE.value, "conversion_kind": result.kind,
                     "conversion_ref": str(result.ref), "conversion_error": None}
            event, detail = EventKind.CONVERTED, {"kind": result.kind, "ref": str(result.ref)}
    patch["updated_at"] = now_iso()
    updated = first(s.tbl(_QUOTES).update(patch).eq("org_id", s.org_id).eq("id", str(quote["id"])).execute())
    if event is not None:
        record_event(s, quote["id"], event, detail=detail)
    return updated or {**quote, **patch}


def convert_quote(s: Scope, quote_id: Any, handler: Optional[QuoteAcceptHandler]) -> dict:
    """Re-run the conversion of an ACCEPTED quote whose conversion is pending / failed / skipped (the handler is idempotent)."""
    row = get_row(s, quote_id)
    if row["status"] != QuoteStatus.ACCEPTED.value:
        raise conflict(TRANSICAO_INVALIDA, "Só é possível converter um orçamento aceito.", status=row["status"])
    if row["conversion_status"] == ConversionStatus.DONE.value:
        return present_quote(row, quote_lines(s, row["id"]), get_party(s, row["party_id"]))
    if handler is None or isinstance(handler, NoopQuoteAcceptHandler):
        raise conflict(CONVERSAO_INDISPONIVEL, "Nenhuma conversão está configurada para este orçamento.", status=row["conversion_status"])
    lines = quote_lines(s, row["id"])
    acceptance = get_acceptance(s, row["id"]) or {}
    final = run_conversion(s, row, lines, acceptance, handler)
    return present_quote(final, lines, get_party(s, final["party_id"]))


__all__ = [
    "accept_quote", "consent_text", "content_sha256", "convert_quote", "get_acceptance", "reject_quote",
    "run_conversion",
]
