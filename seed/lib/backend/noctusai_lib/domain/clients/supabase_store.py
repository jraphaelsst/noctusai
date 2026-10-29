"""`SupabaseClientsStore` -- the real `ClientsStore` over a service-role PostgREST client, plus `build_clients_store`.

`client` is a schema-scoped client (`get_admin_client()` of the product) OR a root client plus `schema=`; every query
is filtered by `org_id` (RLS is the floor, never the only check). Multi-row reads page past the 1 000-row cap and
batch `in_()` lists (`table_reads`), so a big org never silently loses rows.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from noctusai_lib.domain._organ_common import like_term
from noctusai_lib.domain.leads.store import parse_search
from noctusai_lib.integrations.persistence.table_reads import batched, in_batched_rows, paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from .config import ClientsConfig
from .errors import ClientConflictError
from .store import ClientFilters, ClientsStore, FakeClientsStore, session_sort_key


class _Db:
    """Exposes the schema-scoped client the `table_reads` helpers take (`.table(name)`)."""

    def __init__(self, client: Any, schema: Optional[str]) -> None:
        self._base = client.schema(schema) if schema else client

    def table(self, name: str):
        return self._base.table(name)


class SupabaseClientsStore:
    def __init__(self, client: Any, config: Optional[ClientsConfig] = None, *, schema: Optional[str] = None) -> None:
        cfg = config or ClientsConfig()
        self._db = _Db(client, schema)
        self._names = {
            "clients": cfg.clients_table,
            "schedules": cfg.schedules_table,
            "sessions": cfg.sessions_table,
            "payments": cfg.payments_table,
        }

    # -- plumbing
    def _t(self, table: str):
        return self._db.table(self._names[table])

    @staticmethod
    def _first(resp: Any) -> Optional[dict]:
        data = getattr(resp, "data", None)
        if isinstance(data, list):
            return dict(data[0]) if data else None
        return dict(data) if isinstance(data, dict) else None

    def _get(self, table: str, org_id: str, row_id: str) -> Optional[dict]:
        return self._first(self._t(table).select("*").eq("org_id", str(org_id)).eq("id", str(row_id)).limit(1).execute())

    def _insert(self, table: str, org_id: str, row: dict) -> dict:
        saved = self._first(self._t(table).insert({**row, "org_id": str(org_id)}).execute())
        if saved is None:
            raise RuntimeError(f"clients: insert into {self._names[table]} returned no row")
        return saved

    def _update(self, table: str, org_id: str, row_id: str, patch: dict) -> Optional[dict]:
        return self._first(self._t(table).update(patch).eq("org_id", str(org_id)).eq("id", str(row_id)).execute())

    def _all(self, table: str, org_id: str, *, eq: Optional[dict] = None, refine=None) -> list[dict]:
        return paged_rows(self._db, self._names[table], org_id, eq_filters=eq, refine=refine)

    # -- clients
    def get_client(self, org_id: str, client_id: str) -> Optional[dict]:
        return self._get("clients", org_id, client_id)

    def client_by_lead(self, org_id: str, lead_id: str) -> Optional[dict]:
        q = self._t("clients").select("*").eq("org_id", str(org_id)).eq("lead_id", str(lead_id)).limit(1)
        return self._first(q.execute())

    def insert_client(self, org_id: str, row: dict) -> dict:
        try:
            return self._insert("clients", org_id, row)
        except Exception as exc:  # noqa: BLE001 -- only the UNIQUE violation is translated; everything else propagates
            if is_unique_violation(exc):
                raise ClientConflictError(str(exc)) from exc
            raise

    def update_client(self, org_id: str, client_id: str, patch: dict) -> Optional[dict]:
        try:
            return self._update("clients", org_id, client_id, patch)
        except Exception as exc:  # noqa: BLE001 -- only the UNIQUE violation is translated; everything else propagates
            if is_unique_violation(exc):
                raise ClientConflictError(str(exc)) from exc
            raise

    def delete_client(self, org_id: str, client_id: str) -> bool:
        resp = self._t("clients").delete().eq("org_id", str(org_id)).eq("id", str(client_id)).execute()
        return bool(getattr(resp, "data", None))

    def _filtered(self, q: Any, f: ClientFilters) -> Any:
        if f.status:
            q = q.eq("status", f.status)
        if f.tag:
            q = q.contains("tags", [f.tag])
        if f.lead_id:
            q = q.eq("lead_id", str(f.lead_id))
        text, digits = parse_search(f.q)
        if text:
            term = like_term(text)
            clauses = [f'name.ilike."{term}"', f'email.ilike."{term}"', f'phone.ilike."{term}"'] if term.strip("%").strip() else []
            if digits:
                clauses.append(f'phone.ilike."%{digits}%"')
            if clauses:
                q = q.or_(",".join(clauses))
        return q

    def query_clients(self, org_id: str, filters: ClientFilters, *, limit: int, offset: int = 0) -> list[dict]:
        q = self._filtered(self._t("clients").select("*").eq("org_id", str(org_id)), filters)
        q = q.order("name").order("id").range(offset, offset + limit - 1)
        return [dict(r) for r in (q.execute().data or [])]

    def clients_by_ids(self, org_id: str, client_ids: Iterable[str]) -> list[dict]:
        return in_batched_rows(self._db, self._names["clients"], org_id, "id", [str(i) for i in client_ids])

    def all_tags(self, org_id: str) -> list[str]:
        rows = paged_rows(self._db, self._names["clients"], org_id, select="id,tags")
        return sorted({t for r in rows for t in (r.get("tags") or [])})

    # -- schedules
    def get_schedule(self, org_id: str, schedule_id: str) -> Optional[dict]:
        return self._get("schedules", org_id, schedule_id)

    def insert_schedule(self, org_id: str, row: dict) -> dict:
        return self._insert("schedules", org_id, row)

    def update_schedule(self, org_id: str, schedule_id: str, patch: dict) -> Optional[dict]:
        return self._update("schedules", org_id, schedule_id, patch)

    def delete_schedule(self, org_id: str, schedule_id: str) -> bool:
        # The FK is ON DELETE SET NULL; detaching first states it explicitly (the generated history stays, unlinked).
        self._t("sessions").update({"schedule_id": None}).eq("org_id", str(org_id)).eq("schedule_id", str(schedule_id)).execute()
        resp = self._t("schedules").delete().eq("org_id", str(org_id)).eq("id", str(schedule_id)).execute()
        return bool(getattr(resp, "data", None))

    def schedules_of_client(self, org_id: str, client_id: str) -> list[dict]:
        rows = self._all("schedules", org_id, eq={"client_id": str(client_id)})
        return sorted(rows, key=lambda r: (str(r.get("created_at")), str(r["id"])))

    def schedules_due(self, org_id: str, through: str, *, client_id: Optional[str] = None) -> list[dict]:
        eq = {"active": True, **({"client_id": str(client_id)} if client_id else {})}
        rows = self._all(
            "schedules", org_id, eq=eq,
            refine=lambda q: q.or_(f"materialized_until.is.null,materialized_until.lt.{through}"),
        )
        # the same predicate in Python: the cursor test is the contract, whatever the backend evaluated
        return [r for r in rows if r.get("materialized_until") is None or str(r["materialized_until"]) < through]

    # -- sessions
    def get_session(self, org_id: str, session_id: str) -> Optional[dict]:
        return self._get("sessions", org_id, session_id)

    def insert_session(self, org_id: str, row: dict) -> dict:
        return self._insert("sessions", org_id, row)

    def insert_generated_sessions(self, org_id: str, rows: Sequence[dict]) -> list[dict]:
        out: list[dict] = []
        for chunk in batched([{**r, "org_id": str(org_id)} for r in rows]):
            resp = self._t("sessions").upsert(chunk, on_conflict="schedule_id,starts_at", ignore_duplicates=True).execute()
            out.extend(dict(r) for r in (resp.data or []))
        return out

    def update_session(self, org_id: str, session_id: str, patch: dict) -> Optional[dict]:
        return self._update("sessions", org_id, session_id, patch)

    def delete_sessions(self, org_id: str, session_ids: Sequence[str]) -> int:
        n = 0
        for chunk in batched(sorted({str(i) for i in session_ids})):
            resp = self._t("sessions").delete().eq("org_id", str(org_id)).in_("id", chunk).execute()
            n += len(getattr(resp, "data", None) or [])
        return n

    def sessions_between(
        self, org_id: str, start: str, end: str, *, client_id: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        eq = {**({"client_id": str(client_id)} if client_id else {}), **({"status": status} if status else {})}
        rows = self._all("sessions", org_id, eq=eq, refine=lambda q: q.gte("starts_at", start).lt("starts_at", end))
        return sorted(rows, key=session_sort_key)

    def sessions_of_clients(self, org_id: str, client_ids: Sequence[str]) -> list[dict]:
        rows = in_batched_rows(self._db, self._names["sessions"], org_id, "client_id", [str(i) for i in client_ids])
        return sorted(rows, key=session_sort_key)

    def sessions_of_schedule_after(self, org_id: str, schedule_id: str, after: str) -> list[dict]:
        rows = self._all("sessions", org_id, eq={"schedule_id": str(schedule_id)}, refine=lambda q: q.gt("starts_at", after))
        return sorted(rows, key=session_sort_key)

    def booked_sessions_of_client(self, org_id: str, client_id: str) -> list[dict]:
        rows = self._all("sessions", org_id, eq={"client_id": str(client_id)}, refine=lambda q: q.not_.is_("entry_id", "null"))
        return sorted((r for r in rows if r.get("entry_id")), key=session_sort_key)

    # -- payments
    def insert_payment(self, org_id: str, row: dict) -> dict:
        return self._insert("payments", org_id, row)

    def update_payment(self, org_id: str, payment_id: str, patch: dict) -> Optional[dict]:
        return self._update("payments", org_id, payment_id, patch)

    def delete_payment(self, org_id: str, payment_id: str) -> bool:
        resp = self._t("payments").delete().eq("org_id", str(org_id)).eq("id", str(payment_id)).execute()
        return bool(getattr(resp, "data", None))


def build_clients_store(
    client: Any = None, config: Optional[ClientsConfig] = None, *, schema: Optional[str] = None, fake: bool = False
) -> ClientsStore:
    """Factory. `fake=True` builds the in-memory store (tests / local); otherwise a client is REQUIRED --
    a missing client is a configuration error, never a silent fall back to memory."""
    if fake:
        return FakeClientsStore()
    if client is None:
        raise ValueError("build_clients_store needs a PostgREST client (pass fake=True for the in-memory store)")
    return SupabaseClientsStore(client, config, schema=schema)


__all__ = ["SupabaseClientsStore", "build_clients_store"]
