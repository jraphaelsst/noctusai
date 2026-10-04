"""Editorial store seam: value objects + ``EditorialStore`` Protocol + the Fake +
the ``make_editorial_store`` factory (Protocol + Fake + Real + factory, per
``KB § PATTERNS/backend/seed-fake-real-adapter.md``; the Real lives in
``store_supabase.py``).

Model (matches ``sql_templates.editorial_tables``):

- item     — one governed thing (``kind`` + ``ref`` unique per org). ``state`` is the
             state of the WORKING version; ``published_version_n`` is what keeps
             serving (None until first publish, and again after archive).
- version  — immutable (``n``, ``content``, ``content_sha``, ``author_id``).
             Editing never mutates: it mints version n+1. One working draft at a
             time — ``edit`` is only legal from rascunho/publicado, so a version
             under review cannot be silently replaced.
- event    — append-only (action, from/to state, actor, grant, motivo, version n).

Every state change goes through ``apply`` / ``create_item``, which ask the pure
``decide_transition`` first. The Real store additionally relies on the DB
function ``editorial_transition`` re-checking the same rules.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol
from uuid import UUID, uuid4

from noctusai_lib.domain.editorial.workflow import (
    DEFAULT_WORKFLOW,
    Action,
    Code,
    EditorialWorkflow,
    State,
    decide_transition,
)


class EditorialError(Exception):
    """Base for every editorial-store failure."""


class EditorialDenied(EditorialError):
    """A transition was refused. ``code`` is a ``workflow.Code`` value — the same
    string whether the pure check or the DB function refused it."""

    def __init__(self, code: Code | str, detail: str = "") -> None:
        self.code = code.value if isinstance(code, Code) else str(code)
        self.detail = detail
        super().__init__(f"{self.code}: {detail}" if detail else self.code)


class EditorialNotFound(EditorialError):
    pass


class EditorialConflict(EditorialError):
    """(org_id, kind, ref) already exists."""


@dataclass(frozen=True)
class EditorialItem:
    id: UUID
    org_id: UUID
    kind: str
    ref: str
    state: str
    published_version_n: int | None
    current_version_n: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EditorialVersion:
    item_id: UUID
    n: int
    content: Mapping[str, Any]
    content_sha: str
    author_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class EditorialEvent:
    id: int
    item_id: UUID
    version_n: int
    action: str
    from_state: str | None
    to_state: str
    actor_id: UUID
    grant: str | None
    motivo: str | None
    created_at: datetime


@dataclass(frozen=True)
class TransitionResult:
    item: EditorialItem
    event: EditorialEvent
    version: EditorialVersion | None = None  # set when the action minted a version


def content_sha_of(content: Mapping[str, Any]) -> str:
    """sha256 of the canonical JSON (sorted keys, no whitespace, UTF-8)."""
    raw = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def round_approvals(events: Iterable[EditorialEvent], version_n: int) -> dict[str, UUID]:
    """Who approved ``version_n`` THIS review round: the actor of each
    ``approve_*`` event after the version's latest ``submit`` (a send-back and
    re-submit therefore starts the round over)."""
    out: dict[str, UUID] = {}
    for e in events:
        if e.version_n != version_n:
            continue
        if e.action == Action.SUBMIT.value:
            out.clear()
        elif e.action in (Action.APPROVE_EDITORIAL.value, Action.APPROVE_SECURITY.value):
            out[e.action] = e.actor_id
    return out


class EditorialStore(Protocol):
    def create_item(
        self, *, org_id: UUID, kind: str, ref: str, content: Mapping[str, Any],
        actor_id: UUID, grants: Iterable[str],
    ) -> TransitionResult: ...

    def apply(
        self, *, org_id: UUID, item_id: UUID, action: str, actor_id: UUID,
        grants: Iterable[str], motivo: str | None = None,
        content: Mapping[str, Any] | None = None,
    ) -> TransitionResult: ...

    def get_item(self, org_id: UUID, item_id: UUID) -> EditorialItem: ...

    def list_items(
        self, org_id: UUID, *, state: str | None = None, kind: str | None = None
    ) -> list[EditorialItem]: ...

    def list_versions(self, org_id: UUID, item_id: UUID) -> list[EditorialVersion]: ...

    def list_events(self, org_id: UUID, item_id: UUID) -> list[EditorialEvent]: ...

    def get_published_version(self, org_id: UUID, item_id: UUID) -> EditorialVersion | None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeEditorialStore:
    """In-memory store with the SAME invariants the SQL template enforces:
    versions immutable (deep-copied in and out), events append-only (no API to
    change one), state only moved by a decided transition, one working draft,
    the published version keeps serving while a new draft is edited."""

    def __init__(
        self, workflow: EditorialWorkflow = DEFAULT_WORKFLOW, *, now: Callable[[], datetime] = _now
    ) -> None:
        self._wf = workflow
        self._now = now
        self._items: dict[UUID, EditorialItem] = {}
        self._versions: dict[tuple[UUID, int], EditorialVersion] = {}
        self._events: list[EditorialEvent] = []

    # -- internals -------------------------------------------------------
    def _item(self, org_id: UUID, item_id: UUID) -> EditorialItem:
        item = self._items.get(item_id)
        if item is None or item.org_id != org_id:
            raise EditorialNotFound(f"editorial item {item_id} not found")
        return item

    def _item_events(self, item_id: UUID) -> list[EditorialEvent]:
        return [e for e in self._events if e.item_id == item_id]

    def _mint_version(self, item_id: UUID, n: int, content: Mapping[str, Any], author: UUID) -> EditorialVersion:
        frozen = copy.deepcopy(dict(content))
        v = EditorialVersion(item_id, n, frozen, content_sha_of(frozen), author, self._now())
        self._versions[(item_id, n)] = v
        return v

    def _append(self, item_id, n, action, frm, to, actor, grant, motivo) -> EditorialEvent:
        e = EditorialEvent(
            len(self._events) + 1, item_id, n, action, frm, to, actor,
            grant, (motivo or "").strip() or None, self._now(),
        )
        self._events.append(e)
        return e

    @staticmethod
    def _out(v: EditorialVersion | None) -> EditorialVersion | None:
        return None if v is None else replace(v, content=copy.deepcopy(dict(v.content)))

    # -- writes ----------------------------------------------------------
    def create_item(self, *, org_id, kind, ref, content, actor_id, grants) -> TransitionResult:
        d = decide_transition(
            self._wf, action=Action.CREATE, state=None, actor_id=actor_id, grants=grants,
            has_content=content is not None,
        )
        if not d.allowed:
            raise EditorialDenied(d.code, d.detail)
        if any(i.org_id == org_id and i.kind == kind and i.ref == ref for i in self._items.values()):
            raise EditorialConflict(f"({kind}, {ref}) already exists for this org")
        now = self._now()
        item = EditorialItem(uuid4(), org_id, kind, ref, State.RASCUNHO.value, None, 1, now, now)
        self._items[item.id] = item
        v = self._mint_version(item.id, 1, content, actor_id)
        e = self._append(item.id, 1, Action.CREATE.value, None, item.state, actor_id, d.grant.value, None)
        return TransitionResult(item, e, self._out(v))

    def apply(self, *, org_id, item_id, action, actor_id, grants, motivo=None, content=None) -> TransitionResult:
        item = self._item(org_id, item_id)
        n = item.current_version_n
        author = self._versions[(item_id, n)].author_id
        d = decide_transition(
            self._wf, action=action, state=item.state, actor_id=actor_id, grants=grants,
            author_id=author, approvals=round_approvals(self._item_events(item_id), n),
            motivo=motivo, has_content=content is not None,
        )
        if not d.allowed:
            raise EditorialDenied(d.code, d.detail)
        t = d.transition
        version = None
        new_n = n
        if t.creates_version:
            new_n = n + 1
            version = self._mint_version(item_id, new_n, content, actor_id)
        published = item.published_version_n
        if t.action is Action.PUBLISH:
            published = n
        elif t.action is Action.ARCHIVE:
            published = None
        item = replace(
            item, state=d.to_state.value, current_version_n=new_n,
            published_version_n=published, updated_at=self._now(),
        )
        self._items[item_id] = item
        e = self._append(item_id, new_n, t.action.value, t.from_state.value, d.to_state.value,
                         actor_id, t.grant.value, motivo)
        return TransitionResult(item, e, self._out(version))

    # -- reads -----------------------------------------------------------
    def get_item(self, org_id, item_id) -> EditorialItem:
        return self._item(org_id, item_id)

    def list_items(self, org_id, *, state=None, kind=None) -> list[EditorialItem]:
        return [
            i for i in self._items.values()
            if i.org_id == org_id and (state is None or i.state == state) and (kind is None or i.kind == kind)
        ]

    def list_versions(self, org_id, item_id) -> list[EditorialVersion]:
        self._item(org_id, item_id)
        return [self._out(v) for (iid, _), v in sorted(self._versions.items(), key=lambda kv: kv[0][1]) if iid == item_id]

    def list_events(self, org_id, item_id) -> list[EditorialEvent]:
        self._item(org_id, item_id)
        return self._item_events(item_id)

    def get_published_version(self, org_id, item_id) -> EditorialVersion | None:
        item = self._item(org_id, item_id)
        if item.published_version_n is None:
            return None
        return self._out(self._versions[(item_id, item.published_version_n)])


def make_editorial_store(
    schema: str,
    *,
    use_fake: bool = False,
    client: Any | None = None,
    workflow: EditorialWorkflow = DEFAULT_WORKFLOW,
) -> EditorialStore:
    """Construct an ``EditorialStore`` for the product schema ``schema``.

    ``use_fake=True`` → ``FakeEditorialStore`` (dev/tests). Otherwise a
    Supabase client scoped to ``schema`` is REQUIRED — a missing client raises,
    it never silently degrades to the Fake.
    """
    if use_fake:
        return FakeEditorialStore(workflow)
    if client is None:
        raise RuntimeError("make_editorial_store: client is required when use_fake=False")
    from noctusai_lib.domain.editorial.store_supabase import SupabaseEditorialStore

    return SupabaseEditorialStore(client, schema=schema, workflow=workflow)


__all__ = [
    "EditorialConflict", "EditorialDenied", "EditorialError", "EditorialEvent", "EditorialItem",
    "EditorialNotFound", "EditorialStore", "EditorialVersion", "FakeEditorialStore",
    "TransitionResult", "content_sha_of", "make_editorial_store", "round_approvals",
]
