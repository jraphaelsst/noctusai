"""Contract services: create / edit / lifecycle / amendments / readjustment / termination / usage.

Status flow: `draft -> active <-> suspended -> terminated | expired` (the last two are final).
Money is integer cents. Every change to the TERMS of a vigente contract is a new row in
`contract_versions` (v1 = the initial terms); a draft is edited in place. Billing never lives here:
`billing_run.py` turns the schedule into finance receivables through the `ContractsBilling` seam.

Readjustment (v1): the index (IPCA / IGPM / INPC / fixed) is a STORED CHOICE; the operator types the
percentage (basis points) and applies it by hand.
NOC-REMEDIATE[contracts-index-fetch]: no external index fetch (BCB / IBGE series) in v1 -- suggesting
a percentage from the index is the next step; it plugs in as a `percent_bp` provider on `readjust`. — 2026-10-14
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Mapping, Optional

from noctusai_lib.domain.finance.entries import mask_doc, normalize_doc
from noctusai_lib.domain.finance.errors import DOCUMENTO_INVALIDO
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from . import schedule as sched
from ._common import Scope, add_months, first, iso, like_term, new_id, now_iso, to_date, today
from .errors import (
    AVISO_PREVIO, CONTRATO_FINALIZADO, CONTRATO_NAO_RASCUNHO, CONTRATO_VIGENTE, ITEM_INVALIDO, MODELO_COBRANCA_INVALIDO,
    NUMERO_DUPLICADO, PARTE_INVALIDA, PERIODO_JA_FATURADO, REAJUSTE_NAO_APLICAVEL, TRANSICAO_INVALIDA, USO_NAO_APLICAVEL,
    conflict, invalid,
)
from .types import (
    FINAL_STATUSES, BillingFrequency, BillingModel, ContractStatus, ReadjustmentIndex, SignatureStatus, VersionKind, values,
)

logger = logging.getLogger(__name__)

#: Terms an AMENDMENT may change on a vigente contract (and a draft may change freely).
TERM_FIELDS = (
    "amount_cents", "end_date", "due_day", "auto_renew", "renewal_months", "retainer_minutes", "excess_rate_cents",
    "readjustment_index", "readjustment_percent_bp", "readjustment_every_months", "notice_days", "penalty_cents", "penalty_bp",
)
#: Structure: draft only (a vigente contract's billing shape is fixed; end it and open another).
STRUCTURE_FIELDS = ("billing_model", "frequency", "installments_count", "first_due_date", "start_date")
DESCRIPTIVE_FIELDS = ("title", "number", "party_id", "party_name", "party_doc", "notes", "document_body")
_DATE_FIELDS = ("end_date", "first_due_date", "start_date")
_FINITE = (BillingModel.ONE_TIME.value, BillingModel.INSTALLMENTS.value)
_OPEN_ENDED = (BillingModel.RECURRING.value, BillingModel.RETAINER.value)
_MODEL_NULLABLE = ("frequency", "installments_count", "retainer_minutes", "excess_rate_cents")

_ALLOWED = {
    ContractStatus.DRAFT.value: (ContractStatus.ACTIVE.value,),
    ContractStatus.ACTIVE.value: (ContractStatus.SUSPENDED.value, ContractStatus.TERMINATED.value, ContractStatus.EXPIRED.value),
    ContractStatus.SUSPENDED.value: (ContractStatus.ACTIVE.value, ContractStatus.TERMINATED.value),
}


def _plain(v: Any) -> Any:
    return getattr(v, "value", v)


def _doc(raw: Optional[str]) -> Optional[str]:
    """CPF / CNPJ with valid check digits (finance's validator), as OUR error."""
    try:
        return normalize_doc(raw)
    except Exception as exc:  # FinanceError: re-raised under the contracts namespace
        if getattr(exc, "code", None) != DOCUMENTO_INVALIDO:
            raise
        raise invalid("party_doc", "CPF ou CNPJ inválido.", code=DOCUMENTO_INVALIDO) from exc


def _clean(data: Mapping[str, Any]) -> dict:
    out = {}
    for k, v in data.items():
        v = _plain(v)
        out[k] = iso(v) if k in _DATE_FIELDS and v is not None else v
    return out


# --- reads ----------------------------------------------------------------------------------------------------


def get_contract(s: Scope, contract_id: Any) -> dict:
    return s.get("contracts", contract_id, what="Contrato")


def contract_lines(s: Scope, contract_id: Any) -> list[dict]:
    rows = s.rows("contract_lines", eq={"contract_id": str(contract_id)})
    rows.sort(key=lambda r: (int(r.get("position") or 0), str(r["id"])))
    return rows


def present_contract(row: Mapping[str, Any], *, is_admin: bool, lines: Optional[list[dict]] = None, on: Optional[date] = None) -> dict:
    """Wire shape: `party_doc` masked for non-admins (LGPD) + computed `terminable_from`, `readjustment_due_on`, `lapsed`."""
    out = dict(row)
    on = on or today()
    if not is_admin:
        out["party_doc"] = mask_doc(out.get("party_doc"))
    if lines is not None:
        out["lines"] = lines
    out["terminable_from"] = iso(on + timedelta(days=int(out.get("notice_days") or 0)))
    out["readjustment_due_on"] = iso(_next_readjustment_on(out))
    end = to_date(out.get("end_date"))
    out["lapsed"] = bool(out.get("status") == ContractStatus.ACTIVE.value and end is not None and end < on)
    return out


def _next_readjustment_on(c: Mapping[str, Any]) -> Optional[date]:
    if c.get("readjustment_index") in (None, ReadjustmentIndex.NONE.value):
        return None
    base = to_date(c.get("last_readjusted_on")) or to_date(c.get("start_date")) or to_date(c.get("first_due_date"))
    return add_months(base, int(c.get("readjustment_every_months") or 12)) if base else None


def list_contracts(s: Scope, *, q: Optional[str] = None, status: Optional[str] = None, billing_model: Optional[str] = None,
                   party_id: Optional[str] = None, expiring_within_days: Optional[int] = None, page: int = 1,
                   page_size: int = 20) -> tuple[list[dict], int, int, int]:
    def refine(query):
        if status:
            query = query.eq("status", status)
        if billing_model:
            query = query.eq("billing_model", billing_model)
        if party_id:
            query = query.eq("party_id", str(party_id))
        if expiring_within_days is not None:
            query = query.eq("status", ContractStatus.ACTIVE.value).lte("end_date", iso(today() + timedelta(days=expiring_within_days)))
        if q and q.strip():
            t = like_term(q)
            query = query.or_(f"title.ilike.{t},number.ilike.{t},party_name.ilike.{t}")
        return query

    return s.page("contracts", page=page, page_size=page_size, refine=refine, order=(("created_at", True), ("id", True)))


# --- validation / references ----------------------------------------------------------------------------------


def _resolve_party(s: Scope, party_id: Optional[str]) -> dict:
    """With the parties organ mounted: the party must belong to this org; its name/doc are snapshotted."""
    if not party_id or not s.cfg.with_parties:
        return {}
    resp = (s.db.table(s.cfg.parties_table).select("id,legal_name,doc").eq("org_id", s.org_id).eq("id", str(party_id))
            .limit(1).execute())
    row = first(resp)
    if row is None:
        raise invalid("party_id", "Parte não encontrada.", code=PARTE_INVALIDA)
    return {"party_name": row.get("legal_name"), "party_doc": row.get("doc")}


def _check_items(s: Scope, lines: list[Mapping[str, Any]]) -> None:
    if not s.cfg.with_items:
        return
    for ln in lines:
        if ln.get("item_id"):
            resp = s.db.table(s.cfg.items_table).select("id").eq("org_id", s.org_id).eq("id", str(ln["item_id"])).limit(1).execute()
            if first(resp) is None:
                raise invalid("lines.item_id", "Item não encontrado.", code=ITEM_INVALIDO)


def _lines_total(lines: list[Mapping[str, Any]]) -> int:
    return sum(int(ln.get("quantity") or 1) * int(ln["unit_price_cents"]) for ln in lines)


def _write_lines(s: Scope, contract_id: str, lines: list[Mapping[str, Any]]) -> list[dict]:
    s.tbl("contract_lines").delete().eq("org_id", s.org_id).eq("contract_id", contract_id).execute()
    rows = [{
        "id": new_id(), "org_id": s.org_id, "contract_id": contract_id, "position": i, "item_id": ln.get("item_id") or None,
        "description": str(ln["description"]).strip(), "quantity": int(ln.get("quantity") or 1),
        "unit_price_cents": int(ln["unit_price_cents"]), "created_at": now_iso(),
    } for i, ln in enumerate(lines)]
    if rows:
        s.tbl("contract_lines").insert(rows).execute()
    return rows


def _normalize_model_fields(c: dict) -> dict:
    """Null what the billing model does not use; default what it needs; validate the shape."""
    model = c["billing_model"]
    if model not in values(BillingModel):
        raise invalid("billing_model", "Modelo de cobrança inválido.", code=MODELO_COBRANCA_INVALIDO)
    first_due = to_date(c.get("first_due_date")) or to_date(c.get("start_date"))
    if first_due is None:
        raise invalid("first_due_date", "Informe o primeiro vencimento (ou a data de início).")
    c["first_due_date"] = iso(first_due)
    c["due_day"] = int(c["due_day"]) if c.get("due_day") else None
    if model == BillingModel.INSTALLMENTS.value:
        n = int(c.get("installments_count") or 0)
        if n < 1:
            raise invalid("installments_count", "Informe o número de parcelas.")
        if int(c.get("amount_cents") or 0) < n:
            raise invalid("amount_cents", "O valor total é menor que o número de parcelas.")
    else:
        c["installments_count"] = None
    if model == BillingModel.RECURRING.value:
        c["frequency"] = c.get("frequency") or BillingFrequency.MONTHLY.value
    elif model == BillingModel.RETAINER.value:
        c["frequency"] = BillingFrequency.MONTHLY.value
    else:
        c["frequency"] = None
    if model == BillingModel.RETAINER.value:
        if c.get("retainer_minutes") is None:
            raise invalid("retainer_minutes", "Informe a franquia mensal de horas do retainer.")
        c["excess_rate_cents"] = int(c.get("excess_rate_cents") or 0)
    else:
        c["retainer_minutes"] = None
        c["excess_rate_cents"] = None
    if int(c.get("amount_cents") or 0) <= 0:
        raise invalid("amount_cents", "O valor deve ser maior que zero.")
    start, end = to_date(c.get("start_date")), to_date(c.get("end_date"))
    if start and end and end < start:
        raise invalid("end_date", "A data final deve ser igual ou posterior à data de início.")
    if c.get("readjustment_index") == ReadjustmentIndex.FIXED.value and c.get("readjustment_percent_bp") is None:
        raise invalid("readjustment_percent_bp", "O índice fixo exige o percentual (pontos-base).")
    return c


def _snapshot(c: Mapping[str, Any], lines: Optional[list[dict]] = None) -> dict:
    snap = {k: c.get(k) for k in (*TERM_FIELDS, *STRUCTURE_FIELDS, "title", "number", "party_id", "party_name")}
    if lines is not None:
        snap["lines"] = [{k: ln.get(k) for k in ("item_id", "description", "quantity", "unit_price_cents")} for ln in lines]
    return snap


def _record_version(s: Scope, contract: Mapping[str, Any], *, kind: VersionKind, version_n: int, summary: Optional[str] = None,
                    changes: Optional[dict] = None, effective_on: Optional[date] = None, user_id: Optional[str] = None,
                    lines: Optional[list[dict]] = None) -> dict:
    row = {
        "id": new_id(), "org_id": s.org_id, "contract_id": str(contract["id"]), "version_n": version_n, "kind": kind.value,
        "summary": summary, "changes": changes or {}, "snapshot": _snapshot(contract, lines), "effective_on": iso(effective_on),
        "created_by": user_id, "created_at": now_iso(),
    }
    return first(s.tbl("contract_versions").insert(row).execute()) or row


def _diff(before: Mapping[str, Any], after: Mapping[str, Any], fields) -> dict:
    return {f: {"from": before.get(f), "to": after.get(f)} for f in fields if f in after and before.get(f) != after.get(f)}


# --- create / edit / delete -----------------------------------------------------------------------------------


def _check_number(s: Scope, number: Optional[str], *, except_id: Any = None) -> None:
    if not number:
        return
    for r in s.rows("contracts", refine=lambda q: q.ilike("number", number.strip())):
        if str(r["id"]) != str(except_id):
            raise conflict(NUMERO_DUPLICADO, "Já existe um contrato com este número.")


def create_contract(s: Scope, data: Mapping[str, Any], *, user_id: Optional[str] = None, source_quote_id: Optional[str] = None) -> dict:
    """A DRAFT contract (+ lines + version 1). `amount_cents` is derived from `lines` when given."""
    c = _clean(data)
    lines = [dict(ln) for ln in (c.pop("lines", None) or [])]
    if lines:
        total = _lines_total(lines)
        if c.get("amount_cents") not in (None, total):
            raise invalid("amount_cents", "O valor informado difere da soma das linhas.")
        c["amount_cents"] = total
    c["amount_cents"] = int(c.get("amount_cents") or 0)
    _check_items(s, lines)
    snap = _resolve_party(s, c.get("party_id"))
    c.update({k: v for k, v in snap.items() if v is not None})
    if c.get("party_doc"):
        c["party_doc"] = _doc(c["party_doc"])
    c["number"] = (c.get("number") or "").strip() or None
    _check_number(s, c["number"])
    _normalize_model_fields(c)
    now = now_iso()
    row = {
        **{k: v for k, v in c.items() if v is not None or k in _MODEL_NULLABLE},
        "id": new_id(), "org_id": s.org_id, "status": ContractStatus.DRAFT.value, "version_n": 1,
        "signature_status": SignatureStatus.NONE.value, "source_quote_id": source_quote_id, "created_by": user_id,
        "created_at": now, "updated_at": now,
    }
    try:
        saved = first(s.tbl("contracts").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(NUMERO_DUPLICADO, "Já existe um contrato com este número (ou cotação).") from exc
        raise
    saved_lines = _write_lines(s, str(saved["id"]), lines) if lines else []
    _record_version(s, saved, kind=VersionKind.INITIAL, version_n=1, summary="Termos iniciais", user_id=user_id,
                    effective_on=to_date(saved.get("start_date")), lines=saved_lines)
    return saved


def _ensure_editable(c: Mapping[str, Any]) -> None:
    if c["status"] in FINAL_STATUSES:
        raise conflict(CONTRATO_FINALIZADO, "O contrato está encerrado e não aceita alterações.")


def update_contract(s: Scope, contract_id: Any, patch: Mapping[str, Any]) -> dict:
    """Descriptive fields any time before final; terms/structure/lines only on a DRAFT (later: `amend_contract`)."""
    current = get_contract(s, contract_id)
    _ensure_editable(current)
    data = _clean(patch)
    lines = data.pop("lines", None)
    structural = [k for k in (*TERM_FIELDS, *STRUCTURE_FIELDS) if k in data] + (["lines"] if lines is not None else [])
    if structural and current["status"] != ContractStatus.DRAFT.value:
        raise conflict(CONTRATO_VIGENTE, "Contrato vigente: altere os termos por aditivo.", fields=structural)
    merged = {**current, **data}
    if lines is not None:
        lines = [dict(ln) for ln in lines]
        _check_items(s, lines)
        merged["amount_cents"] = data["amount_cents"] = _lines_total(lines)
    if "party_id" in data:
        snap = _resolve_party(s, data["party_id"])
        data.update({k: v for k, v in snap.items() if v is not None})
        merged.update(data)
    if data.get("party_doc"):
        data["party_doc"] = merged["party_doc"] = _doc(data["party_doc"])
    if "number" in data:
        data["number"] = merged["number"] = (data["number"] or "").strip() or None
        _check_number(s, data["number"], except_id=contract_id)
    if structural:
        _normalize_model_fields(merged)
        data.update({k: merged[k] for k in (*_MODEL_NULLABLE, "first_due_date", "due_day")})
    if not data and lines is None:
        return current
    data["updated_at"] = now_iso()
    try:
        s.tbl("contracts").update(data).eq("org_id", s.org_id).eq("id", str(contract_id)).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(NUMERO_DUPLICADO, "Já existe um contrato com este número.") from exc
        raise
    if lines is not None:
        _sync_initial_version(s, {**current, **data}, _write_lines(s, str(contract_id), lines))
    elif structural:
        _sync_initial_version(s, {**current, **data}, contract_lines(s, contract_id))
    return {**current, **data}


def _sync_initial_version(s: Scope, contract: Mapping[str, Any], lines: list[dict]) -> None:
    """A draft is edited in place: its single version (v1) always mirrors the current terms."""
    s.tbl("contract_versions").update({"snapshot": _snapshot(contract, lines)}).eq("org_id", s.org_id) \
        .eq("contract_id", str(contract["id"])).eq("version_n", 1).execute()


def delete_contract(s: Scope, contract_id: Any) -> None:
    current = get_contract(s, contract_id)
    if current["status"] != ContractStatus.DRAFT.value:
        raise conflict(CONTRATO_NAO_RASCUNHO, "Só rascunhos podem ser excluídos; encerre o contrato.")
    s.tbl("contracts").delete().eq("org_id", s.org_id).eq("id", str(contract_id)).execute()


# --- lifecycle ------------------------------------------------------------------------------------------------


def _transition(s: Scope, current: Mapping[str, Any], to: ContractStatus, extra: Mapping[str, Any]) -> dict:
    if to.value not in _ALLOWED.get(current["status"], ()):
        raise conflict(TRANSICAO_INVALIDA, f"Não é possível passar de '{current['status']}' para '{to.value}'.",
                       **{"from": current["status"], "to": to.value})
    patch = {**extra, "status": to.value, "updated_at": now_iso()}
    s.tbl("contracts").update(patch).eq("org_id", s.org_id).eq("id", str(current["id"])).execute()
    return {**current, **patch}


def _bump(s: Scope, contract: dict, kind: VersionKind, *, summary: str, changes: Optional[dict] = None,
          effective_on: Optional[date] = None, user_id: Optional[str] = None) -> dict:
    n = int(contract.get("version_n") or 1) + 1
    s.tbl("contracts").update({"version_n": n}).eq("org_id", s.org_id).eq("id", str(contract["id"])).execute()
    contract = {**contract, "version_n": n}
    _record_version(s, contract, kind=kind, version_n=n, summary=summary, changes=changes, effective_on=effective_on,
                    user_id=user_id, lines=contract_lines(s, contract["id"]))
    return contract


def activate_contract(s: Scope, contract_id: Any, *, billing: Any, on: Optional[date] = None) -> dict:
    """draft -> active: stamps `activated_at`, starts the cursor, and books the first receivables."""
    from .billing_run import bill_contract

    current = get_contract(s, contract_id)
    on = on or today()
    extra: dict[str, Any] = {"activated_at": now_iso()}
    if not current.get("start_date"):
        extra["start_date"] = iso(on)
    if current["billing_model"] in _OPEN_ENDED:
        extra["next_period_on"] = current["first_due_date"]
    activated = _transition(s, current, ContractStatus.ACTIVE, extra)
    bill_contract(s, activated, billing, on=on)
    return get_contract(s, contract_id)


def suspend_contract(s: Scope, contract_id: Any, reason: str, *, user_id: Optional[str] = None) -> dict:
    current = get_contract(s, contract_id)
    out = _transition(s, current, ContractStatus.SUSPENDED, {"suspended_at": now_iso(), "suspension_reason": reason.strip()})
    return _bump(s, out, VersionKind.SUSPENSION, summary=reason.strip(), user_id=user_id, effective_on=today())


def resume_contract(s: Scope, contract_id: Any, *, billing: Any, user_id: Optional[str] = None, on: Optional[date] = None) -> dict:
    """suspended -> active. Periods whose due date fell INSIDE the suspension are skipped, never billed retroactively."""
    from .billing_run import bill_contract

    current = get_contract(s, contract_id)
    on = on or today()
    extra: dict[str, Any] = {"suspended_at": None, "suspension_reason": None}
    cursor = to_date(current.get("next_period_on"))
    if current["billing_model"] in _OPEN_ENDED and cursor is not None:
        while cursor < on:
            cursor = sched.next_due(current, cursor)
        extra["next_period_on"] = iso(cursor)
    out = _transition(s, current, ContractStatus.ACTIVE, extra)
    out = _bump(s, out, VersionKind.RESUMPTION, summary="Contrato retomado", user_id=user_id, effective_on=on)
    bill_contract(s, out, billing, on=on)
    return get_contract(s, contract_id)


def terminate_contract(s: Scope, contract_id: Any, body: Mapping[str, Any], *, billing: Any, user_id: Optional[str] = None,
                       on: Optional[date] = None) -> dict:
    """Terminate with notice. `effective_on` defaults to today + `notice_days`; an earlier date needs
    `waive_notice` and then the penalty (fixed + basis points of the value still to bill) applies unless `waive_penalty`.
    Unsettled receivables due AFTER the effective date are cancelled; settled ones are kept.
    """
    from .billing_run import book_penalty, cancel_after

    current = get_contract(s, contract_id)
    on = on or today()
    notice_until = on + timedelta(days=int(current.get("notice_days") or 0))
    effective = to_date(body.get("effective_on")) or notice_until
    if effective < on:
        raise invalid("effective_on", "A data de encerramento não pode estar no passado.")
    short_notice = effective < notice_until
    if short_notice and not body.get("waive_notice"):
        raise conflict(AVISO_PREVIO, f"O aviso prévio de {current['notice_days']} dias não foi cumprido.",
                       terminable_from=iso(notice_until))
    penalty = 0
    if short_notice and not body.get("waive_penalty"):
        remaining = sched.remaining_value(current, effective)
        penalty = int(current.get("penalty_cents") or 0) + (remaining * int(current.get("penalty_bp") or 0) + 5000) // 10000
    reason = str(body["reason"]).strip()
    out = _transition(s, current, ContractStatus.TERMINATED, {
        "terminated_on": iso(effective), "termination_reason": reason, "next_period_on": None,
        "penalty_applied_cents": penalty or None,
    })
    cancel_after(s, out, billing, effective)
    if penalty:
        book_penalty(s, out, billing, penalty, due=max(effective, on))
    return _bump(s, out, VersionKind.TERMINATION, summary=reason, effective_on=effective, user_id=user_id,
                 changes={"penalty_applied_cents": {"from": None, "to": penalty}} if penalty else None)


def expire_contract(s: Scope, contract: Mapping[str, Any]) -> dict:
    return _transition(s, contract, ContractStatus.EXPIRED, {})


def renew_contract(s: Scope, contract: dict, *, user_id: Optional[str] = None) -> dict:
    """auto_renew: push `end_date` by `renewal_months` (a `renewal` version records it)."""
    old = to_date(contract["end_date"])
    new_end = add_months(old, int(contract.get("renewal_months") or 12))
    s.tbl("contracts").update({"end_date": iso(new_end), "updated_at": now_iso()}).eq("org_id", s.org_id).eq("id", str(contract["id"])).execute()
    out = {**contract, "end_date": iso(new_end)}
    return _bump(s, out, VersionKind.RENEWAL, summary=f"Renovação automática por {contract.get('renewal_months') or 12} meses",
                 changes={"end_date": {"from": iso(old), "to": iso(new_end)}}, effective_on=old, user_id=user_id)


# --- amendments / readjustment --------------------------------------------------------------------------------


def amend_contract(s: Scope, contract_id: Any, body: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """A vigente contract's terms change ONLY through an amendment (new version, with a `changes` diff)."""
    current = get_contract(s, contract_id)
    _ensure_editable(current)
    if current["status"] == ContractStatus.DRAFT.value:
        raise conflict(CONTRATO_NAO_RASCUNHO, "Rascunho: edite o contrato diretamente (sem aditivo).")
    raw = _clean(body["changes"])
    raw = {k: v for k, v in raw.items() if v is not None}
    lines = raw.pop("lines", None)
    if not raw and lines is None:
        raise invalid("changes", "Informe ao menos um termo a alterar.")
    if (lines is not None or "amount_cents" in raw) and current["billing_model"] in _FINITE:
        raise conflict(PERIODO_JA_FATURADO, "O valor de um contrato avulso/parcelado já foi faturado; não pode ser aditado.")
    merged = {**current, **raw}
    if lines is not None:
        lines = [dict(ln) for ln in lines]
        _check_items(s, lines)
        merged["amount_cents"] = raw["amount_cents"] = _lines_total(lines)
    _normalize_model_fields(merged)
    changes = _diff(current, merged, TERM_FIELDS)
    if lines is not None:
        changes["lines"] = {"from": None, "to": len(lines)}
    patch = {k: merged[k] for k in raw}
    patch["updated_at"] = now_iso()
    s.tbl("contracts").update(patch).eq("org_id", s.org_id).eq("id", str(contract_id)).execute()
    if lines is not None:
        _write_lines(s, str(contract_id), lines)
    return _bump(s, {**current, **patch}, VersionKind.AMENDMENT, summary=str(body["summary"]).strip(), changes=changes,
                 effective_on=to_date(body.get("effective_on")) or today(), user_id=user_id)


def _bp_apply(cents: int, bp: int) -> int:
    return (cents * (10000 + bp) + 5000) // 10000


def readjust_contract(s: Scope, contract_id: Any, body: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """Preview (`apply=false`) or apply a readjustment to the recurring fee (and the retainer's excess rate).

    Returns `{applied, index, percent_bp, amount_cents_before/after, excess_rate_cents_before/after}`. Finite models
    (`one_time` / `installments`) are fixed at signing: 422 `reajuste_nao_aplicavel`.
    """
    current = get_contract(s, contract_id)
    _ensure_editable(current)
    if current["billing_model"] not in _OPEN_ENDED:
        raise invalid("billing_model", "Só contratos recorrentes e retainers são reajustáveis.", code=REAJUSTE_NAO_APLICAVEL)
    index = _plain(body.get("index")) or current.get("readjustment_index")
    if index in (None, ReadjustmentIndex.NONE.value):
        raise invalid("index", "Defina o índice de reajuste do contrato.", code=REAJUSTE_NAO_APLICAVEL)
    bp = body.get("percent_bp")
    if bp is None and index == ReadjustmentIndex.FIXED.value:
        bp = current.get("readjustment_percent_bp")
    if bp is None:
        raise invalid("percent_bp", f"Informe o percentual do {index} (pontos-base).")
    bp = int(bp)
    before, rate_before = int(current["amount_cents"]), current.get("excess_rate_cents")
    after = _bp_apply(before, bp)
    rate_after = _bp_apply(int(rate_before), bp) if rate_before else rate_before
    effective = to_date(body.get("effective_on")) or today()
    result = {"applied": False, "index": index, "percent_bp": bp, "effective_on": iso(effective),
              "amount_cents_before": before, "amount_cents_after": after,
              "excess_rate_cents_before": rate_before, "excess_rate_cents_after": rate_after}
    if not body.get("apply"):
        return result
    patch = {"amount_cents": after, "last_readjusted_on": iso(effective), "readjustment_index": index, "updated_at": now_iso()}
    if rate_before:
        patch["excess_rate_cents"] = rate_after
    s.tbl("contracts").update(patch).eq("org_id", s.org_id).eq("id", str(contract_id)).execute()
    changes = {"amount_cents": {"from": before, "to": after}, "percent_bp": {"from": None, "to": bp}}
    pct = f"{bp / 100:.2f}".replace(".", ",")
    out = _bump(s, {**current, **patch}, VersionKind.READJUSTMENT, summary=f"Reajuste {index} de {pct}%",
                changes=changes, effective_on=effective, user_id=user_id)
    return {**result, "applied": True, "contract": out}


# --- retainer usage -------------------------------------------------------------------------------------------


def add_usage(s: Scope, contract_id: Any, body: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    from .billing_run import billed_map

    current = get_contract(s, contract_id)
    if current["billing_model"] != BillingModel.RETAINER.value:
        raise invalid("billing_model", "Apenas retainers registram horas.", code=USO_NAO_APLICAVEL)
    _ensure_editable(current)
    month = (to_date(body.get("period")) or today()).replace(day=1)
    key = f"{month.year}-{month.month:02d}"
    if (key, "excess") in billed_map(s, contract_id):
        raise conflict(PERIODO_JA_FATURADO, "O excedente deste mês já foi faturado.")
    row = {"id": new_id(), "org_id": s.org_id, "contract_id": str(contract_id), "period_month": iso(month),
           "minutes": int(body["minutes"]), "description": body.get("description"), "created_by": user_id, "created_at": now_iso()}
    return first(s.tbl("contract_usage").insert(row).execute()) or row


def usage_by_month(s: Scope, contract_id: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in s.rows("contract_usage", eq={"contract_id": str(contract_id)}):
        key = str(r["period_month"])[:7]
        out[key] = out.get(key, 0) + int(r["minutes"])
    return out


def usage_summary(s: Scope, contract_id: Any) -> list[dict]:
    c = get_contract(s, contract_id)
    return [{"month": key, "minutes": minutes, "included_minutes": c.get("retainer_minutes"),
             "excess_cents": sched.excess_cents(c, minutes)}
            for key, minutes in sorted(usage_by_month(s, contract_id).items())]


def list_versions(s: Scope, contract_id: Any) -> list[dict]:
    get_contract(s, contract_id)
    rows = s.rows("contract_versions", eq={"contract_id": str(contract_id)})
    rows.sort(key=lambda r: int(r["version_n"]))
    return rows


__all__ = [
    "DESCRIPTIVE_FIELDS", "STRUCTURE_FIELDS", "TERM_FIELDS", "activate_contract", "add_usage", "amend_contract",
    "contract_lines", "create_contract", "delete_contract", "expire_contract", "get_contract", "list_contracts",
    "list_versions", "present_contract", "readjust_contract", "renew_contract", "resume_contract", "suspend_contract",
    "terminate_contract", "update_contract", "usage_by_month", "usage_summary",
]
