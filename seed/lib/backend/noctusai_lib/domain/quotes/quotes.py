"""Quotes -- create / edit (draft only) / list / get / revise (versions) / delete / expire.

* **Versions.** One row per version; `root_id` ties the revisions of one quote together and `number` is shared.
  Exactly one version is `is_current` (a partial unique index). A revision is the ONLY way to change a quote that
  left `draft` (the database freezes it); it supersedes the previous open version.
* **Money** is integer cents and SERVER-computed from the lines (`money.compute_totals`); the client never sends a
  total. Quantities are `Decimal`.
* **Lines are snapshots.** A line that names an item defaults its description / unit / price / kind from the item,
  but stores its own copy: editing the catalogue later never changes an issued quote.
* **Expiry** is lazy and persisted: reading an open (`sent` / `viewed`) quote past `valid_until` flips it to `expired`
  (tabs, filters and the accept path then agree); `expire_due` is the same flip for a scheduled job.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import in_batched_rows

from ._common import Scope, dec, first, like_term, local_today, new_id, now_iso, to_date
from .errors import (
    CLIENTE_INVALIDO,
    ITEM_INVALIDO,
    LINHA_INVALIDA,
    NUMERACAO_FALHOU,
    ORCAMENTO_BLOQUEADO,
    ORCAMENTO_SUBSTITUIDO,
    TRANSICAO_INVALIDA,
    VALIDADE_INVALIDA,
    QuotesError,
    conflict,
    invalid,
)
from .money import compute_totals, line_total_cents
from .types import ConvertTo, EventKind, LineKind, OPEN_STATUSES, QuoteStatus, REVISABLE_STATUSES, values

logger = logging.getLogger(__name__)

_QUOTES, _LINES, _EVENTS = "quotes", "lines", "events"
WHAT = "Orçamento"

#: Columns a draft edit may write (everything else is owned by the lifecycle).
_EDITABLE = ("party_id", "title", "valid_until", "notes", "terms", "convert_to")


# ─── events ──────────────────────────────────────────────────────────────────


def record_event(
    s: Scope, quote_id: Any, kind: EventKind, *, from_status: Optional[str] = None, to_status: Optional[str] = None,
    actor: Any = None, detail: Optional[Mapping[str, Any]] = None,
) -> None:
    """Append one audit row. A failure is logged loudly (the primary write already happened) -- never swallowed."""
    row = {
        "id": new_id(), "org_id": s.org_id, "quote_id": str(quote_id), "kind": kind.value, "from_status": from_status,
        "to_status": to_status, "actor": str(actor) if actor else None, "detail": dict(detail or {}), "at": now_iso(),
    }
    try:
        s.tbl(_EVENTS).insert(row).execute()
    except Exception:  # noqa: BLE001 - audit trail write must not mask the committed business write
        logger.exception("quotes: could not append event %s for quote %s (org %s)", kind.value, quote_id, s.org_id)


def list_events(s: Scope, quote_id: Any) -> list[dict]:
    get_row(s, quote_id)  # 404 for a foreign / missing quote
    return s.rows(_EVENTS, eq={"quote_id": str(quote_id)}, order_col="seq")


# ─── lookups ─────────────────────────────────────────────────────────────────


def get_row(s: Scope, quote_id: Any) -> dict:
    return s.get(_QUOTES, quote_id, what=WHAT)


def quote_lines(s: Scope, quote_id: Any) -> list[dict]:
    rows = s.rows(_LINES, eq={"quote_id": str(quote_id)})
    rows.sort(key=lambda r: (int(r.get("position") or 0), str(r["id"])))
    return rows


def _party_rows(s: Scope, ids: Iterable[Any]) -> dict[str, dict]:
    wanted = sorted({str(i) for i in ids if i})
    if not wanted or not s.cfg.with_parties:
        return {}
    rows = in_batched_rows(s.db, s.cfg.parties_table, s.org_id, "id", wanted, select="id, legal_name, trade_name, email, is_active")
    return {str(r["id"]): r for r in rows}


def get_party(s: Scope, party_id: Any) -> Optional[dict]:
    return _party_rows(s, [party_id]).get(str(party_id))


def _require_party(s: Scope, party_id: Any) -> dict:
    if not s.cfg.with_parties:
        return {}
    party = get_party(s, party_id)
    if party is None:
        raise invalid("party_id", "Cliente não encontrado.", CLIENTE_INVALIDO)
    if party.get("is_active") is False:
        raise invalid("party_id", "O cadastro do cliente está arquivado.", CLIENTE_INVALIDO)
    return party


# ─── lines ───────────────────────────────────────────────────────────────────


def _item_rows(s: Scope, ids: Iterable[Any]) -> dict[str, dict]:
    wanted = sorted({str(i) for i in ids if i})
    if not wanted or not s.cfg.with_items:
        return {}
    rows = in_batched_rows(
        s.db, s.cfg.items_table, s.org_id, "id", wanted, select="id, name, unit, item_type, price_cents, is_active"
    )
    return {str(r["id"]): r for r in rows}


def normalize_lines(s: Scope, raw: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Validated, priced line dicts (position, snapshot fields, `total_cents`), items resolved IN THIS ORG."""
    raw = [dict(r) for r in raw]
    items = _item_rows(s, (r.get("item_id") for r in raw))
    out: list[dict] = []
    for i, r in enumerate(raw):
        field = f"lines[{i}]"
        item = None
        if r.get("item_id"):
            item = items.get(str(r["item_id"]))
            if s.cfg.with_items and (item is None or item.get("is_active") is False):
                raise invalid(f"{field}.item_id", "Item não encontrado ou inativo.", ITEM_INVALIDO)
        description = (r.get("description") or (item or {}).get("name") or "").strip()
        if not description:
            raise invalid(f"{field}.description", "Informe a descrição da linha (ou escolha um item).", LINHA_INVALIDA)
        price = r.get("unit_price_cents")
        if price is None:
            price = (item or {}).get("price_cents")
        if price is None:
            raise invalid(f"{field}.unit_price_cents", "Informe o preço unitário da linha.", LINHA_INVALIDA)
        kind = r.get("kind") or ("service" if (item or {}).get("item_type") == "service" else "goods")
        if kind not in values(LineKind):
            raise invalid(f"{field}.kind", "Tipo de linha inválido.", LINHA_INVALIDA)
        qty = dec(r.get("qty"))
        if qty <= 0:
            raise invalid(f"{field}.qty", "A quantidade deve ser maior que zero.", LINHA_INVALIDA)
        discount = int(r.get("discount_cents") or 0)
        out.append({
            "position": i,
            "item_id": str(r["item_id"]) if r.get("item_id") else None,
            "description": description,
            "unit": (r.get("unit") or (item or {}).get("unit") or "UN").strip() or "UN",
            "kind": kind,
            "qty": qty,
            "unit_price_cents": int(price),
            "discount_cents": discount,
            "total_cents": line_total_cents(qty, int(price), discount, index=i),
        })
    return out


def _line_rows(s: Scope, quote_id: str, lines: list[dict]) -> list[dict]:
    return [{**ln, "id": new_id(), "org_id": s.org_id, "quote_id": quote_id, "qty": format(ln["qty"], "f")} for ln in lines]


def _replace_lines(s: Scope, quote_id: str, lines: list[dict]) -> None:
    s.tbl(_LINES).delete().eq("org_id", s.org_id).eq("quote_id", quote_id).execute()
    if lines:
        s.tbl(_LINES).insert(_line_rows(s, quote_id, lines)).execute()


def effective_convert_to(quote: Mapping[str, Any], lines: Iterable[Mapping[str, Any]]) -> str:
    """The explicit `convert_to`, else derived: all goods -> order, all services -> contract, anything else -> none."""
    if quote.get("convert_to"):
        return str(quote["convert_to"])
    kinds = {ln.get("kind") for ln in lines}
    if kinds == {LineKind.GOODS.value}:
        return ConvertTo.ORDER.value
    if kinds == {LineKind.SERVICE.value}:
        return ConvertTo.CONTRACT.value
    return ConvertTo.NONE.value


# ─── presentation ────────────────────────────────────────────────────────────


def present_line(row: Mapping[str, Any]) -> dict:
    out = {k: row.get(k) for k in (
        "id", "position", "item_id", "description", "unit", "kind", "unit_price_cents", "discount_cents", "total_cents"
    )}
    out["qty"] = float(dec(row.get("qty")))
    return out


def present_quote(row: Mapping[str, Any], lines: Optional[list[dict]] = None, party: Optional[Mapping[str, Any]] = None) -> dict:
    """The staff view: the row, its lines, `party` (name / e-mail), and the derived `effective_convert_to`."""
    out = dict(row)
    if lines is not None:
        out["lines"] = [present_line(ln) for ln in lines]
        out["effective_convert_to"] = effective_convert_to(row, lines)
    if party is not None:
        out["party"] = {k: party.get(k) for k in ("id", "legal_name", "trade_name", "email")}
    return out


def quote_valid_until(row: Mapping[str, Any]) -> Optional[date]:
    return to_date(row.get("valid_until"))


# ─── expiry ──────────────────────────────────────────────────────────────────


def is_past_validity(s: Scope, row: Mapping[str, Any], *, at: Optional[datetime] = None) -> bool:
    day = quote_valid_until(row)
    return day is not None and day < local_today(s.cfg, at)


def transition(
    s: Scope, row: Mapping[str, Any], to_status: str, *, expect: Iterable[str], extra: Optional[Mapping[str, Any]] = None
) -> Optional[dict]:
    """Conditional status flip: only succeeds while the row is STILL in one of `expect` (the lost-race guard).

    Returns the updated row, or `None` when someone else got there first. This conditional UPDATE is the lock the
    accept / reject / expire / send paths take -- the second writer matches zero rows.
    """
    patch = {"status": to_status, "updated_at": now_iso(), **dict(extra or {})}
    # postgrest-unbounded-ok: `expect` is a fixed tuple of <= 4 status words, never a data-sized collection
    resp = (
        s.tbl(_QUOTES).update(patch).eq("org_id", s.org_id).eq("id", str(row["id"])).in_("status", list(expect)).execute()
    )
    return first(resp)


def expire_if_due(s: Scope, row: dict, *, at: Optional[datetime] = None) -> dict:
    """Persist `expired` for an open quote past its validity; returns the (possibly refreshed) row."""
    if row.get("status") not in OPEN_STATUSES or not is_past_validity(s, row, at=at):
        return row
    flipped = transition(
        s, row, QuoteStatus.EXPIRED.value, expect=OPEN_STATUSES, extra={"expired_at": (at or datetime.now(timezone.utc)).isoformat()}
    )
    if flipped is None:  # someone decided it first: the truth is whatever is stored now
        return get_row(s, row["id"])
    record_event(s, row["id"], EventKind.EXPIRED, from_status=row["status"], to_status=QuoteStatus.EXPIRED.value)
    return flipped


def expire_due(s: Scope, *, at: Optional[datetime] = None) -> int:
    """Flip EVERY open past-validity quote of this org to `expired` (the scheduled-job entry point). Returns the count."""
    today = local_today(s.cfg, at).isoformat()
    # postgrest-unbounded-ok: OPEN_STATUSES is the fixed 2-word tuple ('sent','viewed'); rows() pages the result
    due = s.rows(_QUOTES, refine=lambda q: q.in_("status", list(OPEN_STATUSES)).lt("valid_until", today))
    flipped = 0
    for row in due:
        if expire_if_due(s, row, at=at).get("status") == QuoteStatus.EXPIRED.value:
            flipped += 1
    return flipped


# ─── numbering ───────────────────────────────────────────────────────────────


def next_number(s: Scope) -> str:
    """The next per-org human number (`ORC-00042`), from the atomic `next_number` RPC."""
    data = s.db.rpc(s.cfg.rpc("next_number"), {"p_org": s.org_id}).execute().data
    if isinstance(data, list):
        data = data[0] if data else None
    if isinstance(data, dict):
        data = next(iter(data.values()), None)
    try:
        n = int(data)
    except (TypeError, ValueError) as exc:
        raise QuotesError(NUMERACAO_FALHOU, "Não foi possível gerar o número do orçamento.", 500) from exc
    return s.cfg.format_number(n)


def _party_ids_matching(s: Scope, term: str) -> list[str]:
    """Up to 50 party ids whose name matches `term` (so `q` finds a quote by its customer's name)."""
    if not s.cfg.with_parties:
        return []
    resp = s.db.table(s.cfg.parties_table).select("id").eq("org_id", s.org_id).ilike("legal_name", term).limit(50).execute()
    return [str(r["id"]) for r in (resp.data or [])]


# ─── read ────────────────────────────────────────────────────────────────────


def get_quote(s: Scope, quote_id: Any) -> dict:
    """One quote with lines + party. An open quote past its validity is flipped to `expired` first."""
    row = expire_if_due(s, get_row(s, quote_id))
    return present_quote(row, quote_lines(s, row["id"]), get_party(s, row["party_id"]))


def list_quotes(
    s: Scope, *, status: Optional[str] = None, party_id: Optional[str] = None, q: Optional[str] = None,
    include_versions: bool = False, page: int = 1, page_size: int = 20,
) -> tuple[list[dict], int, int, int]:
    """One page of quotes (newest first), each with `party` (name). Only the CURRENT version of each quote unless asked."""
    if status is not None and status not in values(QuoteStatus):
        raise invalid("status", "Situação inválida.")
    expire_due(s)  # tabs and filters see the same truth as the accept path
    term = like_term(q) if q and q.strip() else None
    party_hits = _party_ids_matching(s, term) if term else []

    def refine(query):
        if status:
            query = query.eq("status", status)
        if party_id:
            query = query.eq("party_id", str(party_id))
        if not include_versions:
            query = query.eq("is_current", True)
        if term:
            clauses = [f'number.ilike."{term}"', f'title.ilike."{term}"']
            if party_hits:
                clauses.append(f"party_id.in.({','.join(party_hits)})")
            query = query.or_(",".join(clauses))
        return query

    rows, total, page, size = s.page(_QUOTES, page=page, page_size=page_size, refine=refine, order=(("created_at", True), ("id", False)))
    parties = _party_rows(s, (r["party_id"] for r in rows))
    return [present_quote(r, None, parties.get(str(r["party_id"]))) for r in rows], total, page, size


# ─── write ───────────────────────────────────────────────────────────────────


def _check_validity(s: Scope, day: Optional[date]) -> None:
    if day is not None and day < local_today(s.cfg):
        raise invalid("valid_until", "A validade não pode estar no passado.", VALIDADE_INVALIDA)


def _default_validity(s: Scope) -> date:
    return local_today(s.cfg) + timedelta(days=s.cfg.default_valid_days)


def calculate(s: Scope, data: Mapping[str, Any]) -> dict:
    """Preview: normalized lines + totals, NOTHING written (the editor's live totals)."""
    lines = normalize_lines(s, data.get("lines") or [])
    totals = compute_totals(lines, int(data.get("discount_cents") or 0))
    return {**totals, "lines": [present_line(ln) for ln in lines], "effective_convert_to": effective_convert_to({}, lines)}


def create_quote(s: Scope, data: Mapping[str, Any], *, user_id: Any = None) -> dict:
    """A new draft, version 1. Validates party + items in THIS org, computes the totals, numbers it."""
    _require_party(s, data["party_id"])
    valid_until = to_date(data.get("valid_until")) or _default_validity(s)
    _check_validity(s, valid_until)
    lines = normalize_lines(s, data.get("lines") or [])
    totals = compute_totals(lines, int(data.get("discount_cents") or 0))
    quote_id = new_id()
    now = now_iso()
    row = {
        "id": quote_id, "org_id": s.org_id, "number": next_number(s), "root_id": quote_id, "version": 1, "is_current": True,
        "party_id": str(data["party_id"]), "title": _blank(data.get("title")), "status": QuoteStatus.DRAFT.value,
        "currency": s.cfg.currency, "valid_until": valid_until.isoformat(), "notes": _blank(data.get("notes")),
        "terms": _blank(data.get("terms")), "convert_to": data.get("convert_to"), **totals,
        "conversion_status": "none", "created_by": str(user_id) if user_id else None, "created_at": now, "updated_at": now,
    }
    saved = first(s.tbl(_QUOTES).insert(row).execute()) or row
    try:
        if lines:
            s.tbl(_LINES).insert(_line_rows(s, quote_id, lines)).execute()
    except Exception:
        s.tbl(_QUOTES).delete().eq("org_id", s.org_id).eq("id", quote_id).execute()  # a draft with no lines half-written
        raise
    record_event(s, quote_id, EventKind.CREATED, to_status=QuoteStatus.DRAFT.value, actor=user_id, detail={"number": row["number"]})
    return get_quote(s, saved["id"])


def _blank(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def update_quote(s: Scope, quote_id: Any, patch: Mapping[str, Any], *, user_id: Any = None) -> dict:
    """Edit a DRAFT in place. Anything past draft is a new version (409 `orcamento_bloqueado`)."""
    row = get_row(s, quote_id)
    if row["status"] != QuoteStatus.DRAFT.value:
        raise conflict(ORCAMENTO_BLOQUEADO, "Só é possível editar um orçamento em rascunho: crie uma nova versão.", status=row["status"])
    changes: dict[str, Any] = {}
    for key in _EDITABLE:
        if key in patch and key != "party_id":
            changes[key] = _blank(patch[key]) if key in ("title", "notes", "terms") else patch[key]
    if patch.get("party_id") is not None:
        _require_party(s, patch["party_id"])
        changes["party_id"] = str(patch["party_id"])
    if "valid_until" in patch:
        day = to_date(patch["valid_until"])
        _check_validity(s, day)
        changes["valid_until"] = day.isoformat() if day else None
    lines_changed = patch.get("lines") is not None
    if lines_changed or patch.get("discount_cents") is not None:
        lines = normalize_lines(s, patch["lines"]) if lines_changed else [
            {"qty": dec(ln["qty"]), "unit_price_cents": ln["unit_price_cents"], "discount_cents": ln["discount_cents"]}
            for ln in quote_lines(s, row["id"])
        ]
        discount = patch["discount_cents"] if patch.get("discount_cents") is not None else row["discount_cents"]
        changes.update(compute_totals(lines, int(discount)))
        if lines_changed:
            _replace_lines(s, str(row["id"]), lines)
    if not changes:
        return get_quote(s, row["id"])
    changes["updated_at"] = now_iso()
    saved = s.tbl(_QUOTES).update(changes).eq("org_id", s.org_id).eq("id", str(row["id"])).eq("status", "draft").execute()
    if first(saved) is None:
        raise conflict(ORCAMENTO_BLOQUEADO, "O orçamento mudou de situação durante a edição.", status="changed")
    record_event(s, row["id"], EventKind.UPDATED, actor=user_id, detail={"fields": sorted(k for k in changes if k != "updated_at")})
    return get_quote(s, row["id"])


def delete_quote(s: Scope, quote_id: Any, *, user_id: Any = None) -> None:
    """Hard-delete a DRAFT (lines cascade). Everything else stays: it is evidence."""
    row = get_row(s, quote_id)
    if row["status"] != QuoteStatus.DRAFT.value:
        raise conflict(ORCAMENTO_BLOQUEADO, "Só é possível excluir um orçamento em rascunho.", status=row["status"])
    s.tbl(_QUOTES).delete().eq("org_id", s.org_id).eq("id", str(row["id"])).eq("status", "draft").execute()
    record_event(s, row["id"], EventKind.DELETED, from_status="draft", actor=user_id, detail={"number": row["number"], "version": row["version"]})


def new_version(s: Scope, quote_id: Any, *, valid_until: Optional[date] = None, user_id: Any = None) -> dict:
    """Revise: a new DRAFT version (copied lines), the previous open version becomes `superseded` and non-current."""
    row = expire_if_due(s, get_row(s, quote_id))
    if not row.get("is_current"):
        raise conflict(ORCAMENTO_SUBSTITUIDO, "Esta versão já foi substituída por uma mais recente.", status=row["status"])
    if row["status"] not in REVISABLE_STATUSES:
        raise conflict(TRANSICAO_INVALIDA, "Só é possível revisar um orçamento enviado, recusado ou expirado.", status=row["status"])
    day = to_date(valid_until) or _default_validity(s)
    _check_validity(s, day)
    old_status = row["status"]
    superseded = QuoteStatus.SUPERSEDED.value if old_status in OPEN_STATUSES else old_status
    # 1) retire the old version (conditional on it still being what we read: the lost-race guard).
    flipped = (
        s.tbl(_QUOTES).update({"is_current": False, "status": superseded, "updated_at": now_iso()})
        .eq("org_id", s.org_id).eq("id", str(row["id"])).eq("is_current", True).eq("status", old_status).execute()
    )
    if first(flipped) is None:
        raise conflict(TRANSICAO_INVALIDA, "O orçamento mudou de situação: recarregue e tente de novo.")
    # 2) insert the new draft + its copied lines; undo (1) if that fails.
    new_id_ = new_id()
    now = now_iso()
    new_row = {
        "id": new_id_, "org_id": s.org_id, "number": row["number"], "root_id": row["root_id"], "version": int(row["version"]) + 1,
        "is_current": True, "party_id": row["party_id"], "title": row.get("title"), "status": QuoteStatus.DRAFT.value,
        "currency": row["currency"], "valid_until": day.isoformat(), "notes": row.get("notes"), "terms": row.get("terms"),
        "convert_to": row.get("convert_to"), "subtotal_cents": row["subtotal_cents"], "discount_cents": row["discount_cents"],
        "total_cents": row["total_cents"], "conversion_status": "none", "created_by": str(user_id) if user_id else None,
        "created_at": now, "updated_at": now,
    }
    try:
        s.tbl(_QUOTES).insert(new_row).execute()
        copied = [
            {**{k: ln.get(k) for k in ("position", "item_id", "description", "unit", "kind", "unit_price_cents", "discount_cents", "total_cents")},
             "qty": format(dec(ln["qty"]), "f"), "id": new_id(), "org_id": s.org_id, "quote_id": new_id_}
            for ln in quote_lines(s, row["id"])
        ]
        if copied:
            s.tbl(_LINES).insert(copied).execute()
    except Exception:
        s.tbl(_QUOTES).delete().eq("org_id", s.org_id).eq("id", new_id_).execute()
        s.tbl(_QUOTES).update({"is_current": True, "status": old_status, "updated_at": now_iso()}).eq("org_id", s.org_id).eq("id", str(row["id"])).execute()
        raise
    record_event(s, row["id"], EventKind.SUPERSEDED, from_status=old_status, to_status=superseded, actor=user_id, detail={"by": new_id_})
    record_event(s, new_id_, EventKind.VERSIONED, to_status="draft", actor=user_id, detail={"from": str(row["id"]), "version": new_row["version"]})
    return get_quote(s, new_id_)


__all__ = [
    "calculate", "create_quote", "delete_quote", "effective_convert_to", "expire_due", "expire_if_due", "get_party",
    "get_quote", "get_row", "is_past_validity", "list_events", "list_quotes", "new_version", "next_number",
    "normalize_lines", "present_line", "present_quote", "quote_lines", "quote_valid_until", "record_event",
    "transition", "update_quote",
]
