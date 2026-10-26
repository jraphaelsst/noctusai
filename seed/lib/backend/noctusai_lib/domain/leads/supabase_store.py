"""`SupabaseLeadsStore` -- the real `LeadsStore` over a service-role PostgREST client, plus `build_leads_store`.

`client` is a schema-scoped client (`get_admin_client()` of the product) OR a root client plus `schema=`;
every query is filtered by `org_id` (RLS is the floor, never the only check). `position` is sent as a
string so the driver cannot round a `Decimal` through float.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.domain._organ_common import like_term
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from .errors import LeadConflictError
from .store import FakeLeadsStore, LeadFilters, LeadsStore, parse_search

def _number(d: Decimal):
    """A position as a JSON number when that is LOSSLESS (every midpoint of dyadic positions is, for ~50 halvings);
    otherwise a string, which PostgREST casts to `numeric` without a float round-trip."""
    as_float = float(d)
    return as_float if Decimal(as_float) == d else str(d)


def _wire(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = _number(v)
        else:
            out[k] = v
    return out


class SupabaseLeadsStore:
    def __init__(self, client: Any, *, table: str = "leads", schema: Optional[str] = None) -> None:
        self._client = client
        self._table = table
        self._schema = schema

    def _t(self):
        base = self._client.schema(self._schema) if self._schema else self._client
        return base.table(self._table)

    @staticmethod
    def _first(resp: Any) -> Optional[dict]:
        data = getattr(resp, "data", None)
        if isinstance(data, list):
            return dict(data[0]) if data else None
        return dict(data) if isinstance(data, dict) else None

    def _scoped(self, org_id: str):
        return self._t().select("*").eq("org_id", str(org_id))

    def _filtered(self, q: Any, f: LeadFilters) -> Any:
        if f.stage:
            q = q.eq("stage", f.stage)
        if f.origin:
            q = q.eq("origin", f.origin)
        if f.stage_not_in is not None and len(f.stage_not_in):
            q = q.not_.in_("stage", list(f.stage_not_in))
        if f.first_from:
            q = q.gte("first_contact_at", f.first_from.isoformat())
        if f.first_to:
            q = q.lt("first_contact_at", f.first_to.isoformat())
        text, digits = parse_search(f.q)
        if text:
            term = like_term(text)
            clauses = [f'name.ilike."{term}"', f'email.ilike."{term}"', f'notes.ilike."{term}"'] if term.strip("%").strip() else []
            if digits:
                clauses.append(f'phone.ilike."%{digits}%"')
            if clauses:
                q = q.or_(",".join(clauses))
        return q

    def get(self, org_id: str, lead_id: str) -> Optional[dict]:
        return self._first(self._scoped(org_id).eq("id", str(lead_id)).limit(1).execute())

    def find_by_chat(self, org_id: str, connection_id: str, chat_id: str) -> Optional[dict]:
        q = self._scoped(org_id).eq("whatsapp_connection_id", str(connection_id)).eq("whatsapp_chat_id", chat_id)
        return self._first(q.limit(1).execute())

    def insert(self, org_id: str, row: dict) -> dict:
        payload = _wire({**row, "org_id": str(org_id)})
        try:
            saved = self._first(self._t().insert(payload).execute())
        except Exception as exc:  # noqa: BLE001 -- only the UNIQUE violation is translated; everything else propagates
            if is_unique_violation(exc):
                raise LeadConflictError(str(exc)) from exc
            raise
        if saved is None:
            raise RuntimeError("leads insert returned no row")
        return saved

    def update(self, org_id: str, lead_id: str, patch: dict) -> Optional[dict]:
        return self._first(
            self._t().update(_wire(patch)).eq("org_id", str(org_id)).eq("id", str(lead_id)).execute()
        )

    def delete(self, org_id: str, lead_id: str) -> bool:
        resp = self._t().delete().eq("org_id", str(org_id)).eq("id", str(lead_id)).execute()
        return bool(getattr(resp, "data", None))

    def query(self, org_id: str, filters: LeadFilters, *, limit: int, offset: int = 0) -> list[dict]:
        q = self._filtered(self._scoped(org_id), filters)
        q = q.order("first_contact_at", desc=True).order("id", desc=True).range(offset, offset + limit - 1)
        return [dict(r) for r in (q.execute().data or [])]

    def count(self, org_id: str, filters: LeadFilters) -> int:
        q = self._filtered(self._t().select("id", count="exact").eq("org_id", str(org_id)), filters)
        resp = q.limit(1).execute()
        total = getattr(resp, "count", None)
        return int(total if total is not None else len(resp.data or []))

    def column(self, org_id: str, stage: str, filters: LeadFilters, *, limit: int, exclude_id: Optional[str] = None) -> list[dict]:
        q = self._filtered(self._scoped(org_id), LeadFilters(**{**filters.__dict__, "stage": stage}))
        if exclude_id:
            q = q.neq("id", str(exclude_id))
        q = q.order("position").order("created_at").order("id").limit(limit)
        return [dict(r) for r in (q.execute().data or [])]

    def purge_from_connection(self, org_id: str, connection_id: str, *, origin: str) -> tuple[int, int]:
        # Delete first (untouched automatic leads), then detach whatever is left of the connection: the second
        # statement therefore only ever sees human-touched rows. A crash between them leaves rows attached to a
        # connection the caller is about to remove; re-running the purge finishes it.
        gone = (
            self._t().delete().eq("org_id", str(org_id)).eq("whatsapp_connection_id", str(connection_id))
            .eq("origin", origin).is_("created_by", "null").is_("edited_at", "null").execute()
        )
        kept = (
            self._t()
            .update({"whatsapp_connection_id": None, "whatsapp_chat_id": None, "last_message_preview": None})
            .eq("org_id", str(org_id)).eq("whatsapp_connection_id", str(connection_id)).execute()
        )
        return len(getattr(gone, "data", None) or []), len(getattr(kept, "data", None) or [])


def build_leads_store(
    client: Any = None, *, table: str = "leads", schema: Optional[str] = None, fake: bool = False
) -> LeadsStore:
    """Factory. `fake=True` builds the in-memory store (tests / local); otherwise a client is REQUIRED --
    a missing client is a configuration error, never a silent fall back to memory."""
    if fake:
        return FakeLeadsStore()
    if client is None:
        raise ValueError("build_leads_store needs a PostgREST client (pass fake=True for the in-memory store)")
    return SupabaseLeadsStore(client, table=table, schema=schema)


__all__ = ["SupabaseLeadsStore", "build_leads_store"]
