"""Supabase-backed ``EditorialStore`` (the Real half of Protocol + Fake + Real +
factory). Reads go through bare table names on a schema-pinned client; every
write goes through the SECURITY DEFINER functions emitted by
``sql_templates.editorial_tables`` — the only path the DB guards allow.

Two layers refuse an illegal transition: ``decide_transition`` here (a clean,
typed denial without a round trip) and ``editorial_transition`` in the DB (so a
caller that skips this class and calls the RPC directly is still refused).
A DB refusal surfaces as the SAME ``EditorialDenied(code)``.

``client`` is a Supabase client already scoped to the product schema (the house
admin client re-pins its schema on every ``.table()``/``.rpc()`` call —
``KB § PATTERNS/backend/admin-client-schema-pinning.md``); table names are BARE
(``KB § PATTERNS/backend/postgrest-schema-targeting.md``).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable, Mapping
from uuid import UUID

from noctusai_lib.domain.editorial.store import (
    EditorialConflict,
    EditorialDenied,
    EditorialEvent,
    EditorialItem,
    EditorialNotFound,
    EditorialVersion,
    TransitionResult,
    content_sha_of,
    round_approvals,
)
from noctusai_lib.domain.editorial.workflow import (
    DEFAULT_WORKFLOW,
    Action,
    Code,
    EditorialWorkflow,
    decide_transition,
)
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

_ERR_RE = re.compile(r"editorial_([a-z_]+)")
_DENIAL_CODES = {c.value for c in Code} - {Code.OK.value}


def _dt(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _item(r: Mapping[str, Any]) -> EditorialItem:
    return EditorialItem(
        UUID(str(r["id"])), UUID(str(r["org_id"])), r["kind"], r["ref"], r["state"],
        r["published_version_n"], r["current_version_n"], _dt(r["created_at"]), _dt(r["updated_at"]),
    )


def _version(r: Mapping[str, Any]) -> EditorialVersion:
    return EditorialVersion(
        UUID(str(r["item_id"])), r["n"], r["content"], r["content_sha"],
        UUID(str(r["author_id"])), _dt(r["created_at"]),
    )


def _event(r: Mapping[str, Any]) -> EditorialEvent:
    return EditorialEvent(
        r["id"], UUID(str(r["item_id"])), r["version_n"], r["action"], r["from_state"], r["to_state"],
        UUID(str(r["actor_id"])), r["grant_name"], r["motivo"], _dt(r["created_at"]),
    )


def map_db_error(exc: BaseException) -> Exception:
    """Translate a PostgREST/DB error carrying an ``editorial_<code>`` message
    into the typed store error; anything else is returned unchanged."""
    text = str(exc)
    m = _ERR_RE.search(text)
    if m:
        code = m.group(1)
        if code in _DENIAL_CODES:
            return EditorialDenied(code, text)
        if code == "item_not_found":
            return EditorialNotFound(text)
        if code in ("write_via_transition_only", "version_immutable", "event_append_only"):
            return EditorialDenied(code, text)
    if "editorial_items_org_kind_ref_key" in text or "23505" in text:
        return EditorialConflict(text)
    return exc if isinstance(exc, Exception) else RuntimeError(text)


class SupabaseEditorialStore:
    def __init__(
        self, client: Any, *, schema: str, workflow: EditorialWorkflow = DEFAULT_WORKFLOW
    ) -> None:
        self._client = client
        self.schema = schema
        self._wf = workflow

    # -- plumbing --------------------------------------------------------
    def _rpc(self, name: str, params: dict[str, Any]) -> Any:
        try:
            return self._client.rpc(name, params).execute().data
        except Exception as exc:  # noqa: BLE001 — re-raised typed below, never swallowed
            raise map_db_error(exc) from exc

    def _scalar(self, data: Any) -> Any:
        return data[0] if isinstance(data, list) and data else data

    # -- writes ----------------------------------------------------------
    def create_item(self, *, org_id, kind, ref, content, actor_id, grants) -> TransitionResult:
        grants = list(grants)
        d = decide_transition(
            self._wf, action=Action.CREATE, state=None, actor_id=actor_id, grants=grants,
            has_content=content is not None,
        )
        if not d.allowed:
            raise EditorialDenied(d.code, d.detail)
        item_id = self._scalar(self._rpc("editorial_create_item", {
            "p_org_id": str(org_id), "p_kind": kind, "p_ref": ref, "p_actor_id": str(actor_id),
            "p_grants": grants, "p_content": dict(content), "p_content_sha": content_sha_of(content),
        }))
        item_id = UUID(str(item_id))
        item = self.get_item(org_id, item_id)
        return TransitionResult(item, self.list_events(org_id, item_id)[-1], self.list_versions(org_id, item_id)[0])

    def apply(self, *, org_id, item_id, action, actor_id, grants, motivo=None, content=None) -> TransitionResult:
        grants = list(grants)
        item = self.get_item(org_id, item_id)
        n = item.current_version_n
        versions = self.list_versions(org_id, item_id)
        author = next(v.author_id for v in versions if v.n == n)
        d = decide_transition(
            self._wf, action=action, state=item.state, actor_id=actor_id, grants=grants,
            author_id=author, approvals=round_approvals(self.list_events(org_id, item_id), n),
            motivo=motivo, has_content=content is not None,
        )
        if not d.allowed:
            raise EditorialDenied(d.code, d.detail)
        event_id = self._scalar(self._rpc("editorial_transition", {
            "p_org_id": str(org_id), "p_item_id": str(item_id), "p_action": str(getattr(action, "value", action)),
            "p_actor_id": str(actor_id), "p_grants": grants, "p_motivo": motivo,
            "p_content": None if content is None else dict(content),
            "p_content_sha": None if content is None else content_sha_of(content),
        }))
        item = self.get_item(org_id, item_id)
        event = next(e for e in self.list_events(org_id, item_id) if e.id == int(event_id))
        minted = next((v for v in self.list_versions(org_id, item_id) if v.n == event.version_n), None)
        return TransitionResult(item, event, minted if d.transition.creates_version else None)

    # -- reads -----------------------------------------------------------
    def get_item(self, org_id, item_id) -> EditorialItem:
        rows = (
            self._client.table("editorial_items").select("*")
            .eq("org_id", str(org_id)).eq("id", str(item_id)).limit(1).execute().data
        )
        if not rows:
            raise EditorialNotFound(f"editorial item {item_id} not found")
        return _item(rows[0])

    def list_items(self, org_id, *, state=None, kind=None) -> list[EditorialItem]:
        def page(start: int, end: int) -> list[dict[str, Any]]:
            q = self._client.table("editorial_items").select("*").eq("org_id", str(org_id))
            if state is not None:
                q = q.eq("state", state)
            if kind is not None:
                q = q.eq("kind", kind)
            return q.order("id").range(start, end).execute().data

        return [_item(r) for r in iter_paged_rows(page, label=f"editorial_items org_id={org_id}")]

    def list_versions(self, org_id, item_id) -> list[EditorialVersion]:
        self.get_item(org_id, item_id)

        def page(start: int, end: int) -> list[dict[str, Any]]:
            return (
                self._client.table("editorial_versions").select("*").eq("item_id", str(item_id))
                .order("n").range(start, end).execute().data
            )

        return [_version(r) for r in iter_paged_rows(page, id_key="n", label=f"editorial_versions {item_id}")]

    def list_events(self, org_id, item_id) -> list[EditorialEvent]:
        self.get_item(org_id, item_id)

        def page(start: int, end: int) -> list[dict[str, Any]]:
            return (
                self._client.table("editorial_events").select("*").eq("item_id", str(item_id))
                .order("id").range(start, end).execute().data
            )

        return [_event(r) for r in iter_paged_rows(page, label=f"editorial_events {item_id}")]

    def get_published_version(self, org_id, item_id) -> EditorialVersion | None:
        item = self.get_item(org_id, item_id)
        if item.published_version_n is None:
            return None
        return next(v for v in self.list_versions(org_id, item_id) if v.n == item.published_version_n)


__all__ = ["SupabaseEditorialStore", "map_db_error"]
