"""Entries -- payables / receivables, installment groups, listing, cancel.

`overdue` is computed on read (never stored). `settled_cents` and `status` are
owned by `settlements.recompute_entry`; this module only reads them, except for
the amount edit which re-derives the status through `status_for`.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Mapping, Optional

from noctusai_lib.domain._organ_common import mask_doc
from noctusai_lib.integrations.persistence.table_reads import IN_FILTER_BATCH
from noctusai_lib.primitives.identificador import cnpj_dv_valido, cpf_dv_valido
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import (
    Scope,
    add_months,
    first,
    iso,
    like_term,
    month_start,
    new_id,
    now_iso,
    to_date,
    today,
)
from .categories import descendant_ids, ensure_default_categories
from .errors import (
    DOCUMENTO_INVALIDO,
    LANCAMENTO_CANCELADO,
    LANCAMENTO_COM_BAIXA,
    LANCAMENTO_DUPLICADO,
    conflict,
    invalid,
)
from .types import CategoryDirection, EntryDirection, EntrySource, EntryStatus, values

logger = logging.getLogger(__name__)

MAX_INSTALLMENTS = 120
_OPEN_STATUSES = (EntryStatus.OPEN.value, EntryStatus.PARTIAL.value)
#: Sources a caller of the HTTP API may stamp. The rest belong to the organ / the bridges.
API_SOURCES = (EntrySource.MANUAL.value, EntrySource.EXTERNAL.value)


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


# ─── LGPD: counterparty_doc ──────────────────────────────────────────────────


def normalize_doc(raw: Optional[str]) -> Optional[str]:
    """CPF (11 digits) or CNPJ (14, numeric or alphanumeric) with valid check digits; `None` for blank."""
    if raw is None or not str(raw).strip():
        return None
    cleaned = "".join(ch for ch in str(raw).upper() if ch.isalnum())
    if len(cleaned) == 11 and cleaned.isdigit() and cpf_dv_valido(cleaned):
        return cleaned
    if len(cleaned) == 14 and cnpj_dv_valido(cleaned):
        return cleaned
    raise invalid("counterparty_doc", "CPF ou CNPJ inválido.", code=DOCUMENTO_INVALIDO)


def present_entry(row: dict, *, is_admin: bool, on: Optional[date] = None) -> dict:
    """The wire shape of an entry: `overdue` computed, `counterparty_doc` masked for non-admins."""
    out = dict(row)
    on = on or today()
    due = to_date(out.get("due_date"))
    out["overdue"] = bool(out.get("status") in _OPEN_STATUSES and due is not None and due < on)
    if not is_admin:
        out["counterparty_doc"] = mask_doc(out.get("counterparty_doc"))
    return out


def status_for(amount_cents: int, settled_cents: int) -> str:
    if settled_cents <= 0:
        return EntryStatus.OPEN.value
    if settled_cents >= amount_cents:
        return EntryStatus.PAID.value
    return EntryStatus.PARTIAL.value


# ─── references ──────────────────────────────────────────────────────────────


def check_refs(s: Scope, data: Mapping[str, Any], direction: str) -> None:
    """Every referenced id belongs to the caller's org (beyond RLS) and fits the entry."""
    if data.get("category_id"):
        ensure_default_categories(s)
        cat = s.require_owned("categories", data["category_id"], what="Categoria", field="category_id")
        wanted = CategoryDirection.INCOME.value if direction == EntryDirection.RECEIVABLE.value else CategoryDirection.EXPENSE.value
        if cat["direction"] != wanted:
            raise invalid("category_id", "A direção da categoria não combina com o lançamento.", code="categoria_direcao_invalida")
        if not cat.get("active", True):
            raise invalid("category_id", "A categoria está inativa.", code="categoria_inativa")
    if data.get("cost_center_id"):
        cc = s.require_owned("cost_centers", data["cost_center_id"], what="Centro de custo", field="cost_center_id")
        if not cc.get("active", True):
            raise invalid("cost_center_id", "O centro de custo está inativo.", code="centro_custo_inativo")
    if data.get("expected_account_id"):
        s.require_owned("accounts", data["expected_account_id"], what="Conta", field="expected_account_id")


def find_by_source(s: Scope, source: str, source_ref: str) -> Optional[dict]:
    resp = (
        s.tbl("entries").select("*").eq("org_id", s.org_id).eq("source", source).eq("source_ref", source_ref).limit(1).execute()
    )
    return first(resp)


# ─── create ──────────────────────────────────────────────────────────────────


def _base_row(s: Scope, data: Mapping[str, Any], direction: str) -> dict:
    due = to_date(data["due_date"])
    return {
        "org_id": s.org_id,
        "direction": direction,
        "status": EntryStatus.OPEN.value,
        "description": str(data["description"]).strip(),
        "counterparty_name": (str(data["counterparty_name"]).strip() or None) if data.get("counterparty_name") else None,
        "counterparty_doc": normalize_doc(data.get("counterparty_doc")),
        "category_id": str(data["category_id"]) if data.get("category_id") else None,
        "cost_center_id": str(data["cost_center_id"]) if data.get("cost_center_id") else None,
        "expected_account_id": str(data["expected_account_id"]) if data.get("expected_account_id") else None,
        "competence_month": iso(month_start(data.get("competence_month") or due)),
        "due_date": iso(due),
        "settled_cents": 0,
        "notes": data.get("notes") or None,
    }


def split_installments(total_cents: int, n: int) -> list[int]:
    """Integer division; the last installment absorbs the remainder (contract §3.3)."""
    each = total_cents // n
    return [each] * (n - 1) + [total_cents - each * (n - 1)]


def create_entry(s: Scope, data: Mapping[str, Any]) -> list[dict]:
    """Create one entry, or an installment group when `installments >= 2`. Returns the new rows."""
    direction = _plain(data["direction"])
    source = _plain(data.get("source") or EntrySource.MANUAL.value)
    source_ref = data.get("source_ref") or None
    n = int(data.get("installments") or 1)
    amount = int(data["amount_cents"])
    if amount <= 0:
        raise invalid("amount_cents", "O valor deve ser maior que zero.")
    if not 1 <= n <= MAX_INSTALLMENTS:
        raise invalid("installments", f"O número de parcelas deve ficar entre 1 e {MAX_INSTALLMENTS}.")
    if n > 1 and amount < n:
        raise invalid("amount_cents", "O valor total é menor que o número de parcelas.")
    if n > 1 and source_ref:
        raise invalid("source_ref", "Lançamentos parcelados não aceitam referência externa.")
    if source not in values(EntrySource):
        raise invalid("source", "Origem inválida.")
    check_refs(s, data, direction)
    base = _base_row(s, data, direction)
    now = now_iso()
    if n == 1:
        if source_ref and find_by_source(s, source, source_ref):
            raise conflict(LANCAMENTO_DUPLICADO, "Já existe um lançamento com esta origem e referência.")
        rows = [{**base, "id": new_id(), "amount_cents": amount, "source": source, "source_ref": source_ref,
                 "created_at": now, "updated_at": now}]
    else:
        group = new_id()
        due0, comp0 = to_date(base["due_date"]), to_date(base["competence_month"])
        rows = []
        for i, part in enumerate(split_installments(amount, n)):
            rows.append({
                **base,
                "id": new_id(),
                "description": f"{base['description']} ({i + 1}/{n})",
                "due_date": iso(add_months(due0, i, anchor_day=due0.day)),
                "competence_month": iso(add_months(comp0, i)),
                "amount_cents": part,
                "source": EntrySource.INSTALLMENT.value,
                "source_ref": f"{group}:{i + 1}",
                "installment_group_id": group,
                "installment_n": i + 1,
                "installment_total": n,
                "created_at": now,
                "updated_at": now,
            })
    try:
        saved = s.tbl("entries").insert(rows).execute().data
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(LANCAMENTO_DUPLICADO, "Já existe um lançamento com esta origem e referência.") from exc
        raise
    return [dict(r) for r in (saved or rows)]


# ─── read ────────────────────────────────────────────────────────────────────


def get_entry(s: Scope, entry_id: Any) -> dict:
    return s.get("entries", entry_id, what="Lançamento")


def get_entry_detail(s: Scope, entry_id: Any) -> dict:
    """The entry plus its settlements (reversed ones included -- they are history) and attachment metadata."""
    entry = get_entry(s, entry_id)
    sett = s.rows("settlements", eq={"entry_id": str(entry_id)})
    sett.sort(key=lambda r: (str(r.get("settled_on")), str(r.get("created_at")), str(r["id"])))
    atts = s.rows("attachments", eq={"entry_id": str(entry_id)})
    atts = [{k: v for k, v in a.items() if k != "storage_path"} for a in atts]
    atts.sort(key=lambda r: (str(r.get("at")), str(r["id"])))
    return {**entry, "settlements": sett, "attachments": atts}


def list_entries(
    s: Scope,
    *,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    overdue: Optional[bool] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[Any] = None,
    cost_center_id: Optional[Any] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int, int, int]:
    if direction is not None and direction not in values(EntryDirection):
        raise invalid("direction", "Direção inválida.")
    if status is not None and status not in values(EntryStatus):
        raise invalid("status", "Status inválido.")
    category_ids = descendant_ids(s, category_id) if category_id else None
    if category_ids and len(category_ids) > IN_FILTER_BATCH:
        raise invalid("category_id", "A categoria tem subcategorias demais para filtrar de uma vez.", code="categoria_ampla_demais")
    on = today().isoformat()
    term = like_term(q) if q and q.strip() else None

    def refine(query):
        if direction:
            query = query.eq("direction", direction)
        if status:
            query = query.eq("status", status)
        if date_from:
            query = query.gte("due_date", date_from.isoformat())
        if date_to:
            query = query.lte("due_date", date_to.isoformat())
        if category_ids:
            # postgrest-unbounded-ok: a category subtree, capped at IN_FILTER_BATCH just above (422 beyond it)
            query = query.in_("category_id", category_ids)
        if cost_center_id:
            query = query.eq("cost_center_id", str(cost_center_id))
        if overdue is True:
            # postgrest-unbounded-ok: two literal enum values
            query = query.in_("status", list(_OPEN_STATUSES)).lt("due_date", on)
        elif overdue is False:
            query = query.or_(f"status.in.(paid,cancelled),due_date.gte.{on}")
        if term:
            query = query.or_(f'description.ilike."{term}",counterparty_name.ilike."{term}"')
        return query

    return s.page("entries", page=page, page_size=page_size, refine=refine, order=(("due_date", False), ("id", False)))


# ─── update / cancel ─────────────────────────────────────────────────────────

_EDITABLE = (
    "description", "counterparty_name", "counterparty_doc", "category_id", "cost_center_id",
    "expected_account_id", "competence_month", "due_date", "amount_cents", "notes",
)


_NOT_NULL = ("description", "competence_month", "due_date", "amount_cents")


def update_entry(s: Scope, entry_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_entry(s, entry_id)
    if current["status"] == EntryStatus.CANCELLED.value:
        raise conflict(LANCAMENTO_CANCELADO, "O lançamento está cancelado.")
    patch = {k: data[k] for k in _EDITABLE if k in data}
    for key in _NOT_NULL:
        if key in patch and patch[key] is None:
            raise invalid(key, "Este campo não pode ficar vazio.")
    if not patch:
        return current
    check_refs(s, {k: v for k, v in patch.items() if k in ("category_id", "cost_center_id", "expected_account_id")}, current["direction"])
    if "description" in patch:
        patch["description"] = str(patch["description"]).strip()
    if "counterparty_doc" in patch:
        patch["counterparty_doc"] = normalize_doc(patch["counterparty_doc"])
    for key in ("category_id", "cost_center_id", "expected_account_id"):
        if key in patch:
            patch[key] = str(patch[key]) if patch[key] else None
    if "due_date" in patch:
        patch["due_date"] = iso(patch["due_date"])
    if "competence_month" in patch:
        patch["competence_month"] = iso(month_start(patch["competence_month"]))
    if "amount_cents" in patch:
        amount = int(patch["amount_cents"])
        if amount < int(current.get("settled_cents") or 0):
            raise invalid("amount_cents", "O valor não pode ficar abaixo do que já foi baixado.", code="valor_abaixo_baixado")
        patch["amount_cents"] = amount
        patch["status"] = status_for(amount, int(current.get("settled_cents") or 0))
    patch["updated_at"] = now_iso()
    s.tbl("entries").update(patch).eq("org_id", s.org_id).eq("id", str(entry_id)).execute()
    return {**current, **patch}


def cancel_entry(s: Scope, entry_id: Any) -> dict:
    """Cancel an entry. Refused (409 `lancamento_com_baixa`) while it has unreversed settlements."""
    current = get_entry(s, entry_id)
    if current["status"] == EntryStatus.CANCELLED.value:
        return current
    live = (
        s.tbl("settlements").select("id").eq("org_id", s.org_id).eq("entry_id", str(entry_id))
        .is_("reversed_at", "null").limit(1).execute()
    )
    if live.data:
        raise conflict(LANCAMENTO_COM_BAIXA, "O lançamento tem baixas; estorne-as antes de cancelar.")
    patch = {"status": EntryStatus.CANCELLED.value, "updated_at": now_iso()}
    s.tbl("entries").update(patch).eq("org_id", s.org_id).eq("id", str(entry_id)).execute()
    return {**current, **patch}


__all__ = [
    "API_SOURCES",
    "check_refs",
    "MAX_INSTALLMENTS",
    "cancel_entry",
    "create_entry",
    "find_by_source",
    "get_entry",
    "get_entry_detail",
    "list_entries",
    "mask_doc",
    "normalize_doc",
    "present_entry",
    "split_installments",
    "status_for",
    "update_entry",
]
