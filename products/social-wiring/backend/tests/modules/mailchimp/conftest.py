"""Mailchimp module test fixtures.

DI-seam based (no patching of our own code). Two overrides:

  ``get_mailchimp_store``   → SQLite-backed MailchimpConnectionStore
  ``get_mailchimp_client_factory`` → ContractFakeMailchimpClient producer

The ``client`` fixture from the top-level conftest provides auth + MockSupabase.

ContractFakeMailchimpClient
─────────────────────────────
test double for the normative Protocol in plan §2;
integration may swap to seed FakeMailchimpClient once slice A lands.

It implements every Protocol method used by slice B routers with fully
in-memory deterministic semantics, mirroring the contract semantics:
  - ping() succeeds silently
  - list/get/create/update/delete for audiences, members, segments, templates, campaigns
  - set_member_tags: declarative (replaces active tag set)
  - archive_member: sets status='archived'
  - send_campaign: sets status='sent'
  - schedule_campaign: sets status='schedule'
  - unschedule_campaign: sets status='save'
  - send_test: no-op
  - add_segment_member raises MailchimpRejectedError for unknown emails

Error classes are re-defined locally here (not imported from the seed lib):
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from app.modules.mailchimp.errors import (
    MailchimpAuthError,
    MailchimpError,
    MailchimpNotFoundError,
    MailchimpRateLimitedError,
    MailchimpRejectedError,
    MailchimpUnreachableError,
)
from app.modules.mailchimp.store import MailchimpConnectionStore
from app.sqlite_client import SQLiteClient

# Error classes imported from errors.py (the normative §2 Protocol hierarchy).
# The fake raises these exact classes; translate_mailchimp_errors() catches them.
# Once slice A ships, both here and errors.py will import from
# noctusai_lib.integrations.mailchimp instead.


# ── Simple data objects (used internally by the fake) ────────────────────────

def _subscriber_hash(email: str) -> str:
    """Mirror `noctusai_lib...client.subscriber_hash` — the REAL client hashes
    the email itself, so the double must take an email and hash it too. A
    double that accepted a pre-hashed value let every member route ship
    double-hashing bugs that only showed up against live Mailchimp."""
    return hashlib.md5(email.strip().lower().encode("utf-8"), usedforsecurity=False).hexdigest()  # noqa: S324


@dataclass
class _Page:
    items: list
    total: int


@dataclass
class _Audience:
    id: str
    name: str
    member_count: int


@dataclass
class _Member:
    email: str
    status: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    tags: list = field(default_factory=list)
    vip: bool = False
    last_changed: Any = None


@dataclass
class _Segment:
    id: int
    name: str
    member_count: int
    created_at: Any = None
    updated_at: Any = None
    _members: set = field(default_factory=set)


@dataclass
class _Template:
    id: int
    name: str
    category: Optional[str] = None
    type: Optional[str] = "user"
    drag_and_drop: bool = False
    preview_image: Optional[str] = None
    date_created: Any = None
    date_edited: Any = None
    html: str = ""


@dataclass
class _Campaign:
    id: str
    web_id: Optional[int] = None
    title: Optional[str] = None
    status: str = "save"
    subject_line: Optional[str] = None
    preview_text: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    segment_id: Optional[int] = None
    template_id: Optional[int] = None
    send_time: Any = None
    create_time: Any = None
    emails_sent: Optional[int] = None
    report_summary: dict = field(default_factory=dict)
    archive_url: Optional[str] = None


# ── ContractFakeMailchimpClient ───────────────────────────────────────────────

class ContractFakeMailchimpClient:
    """In-memory Mailchimp client test double.

    test double for the normative Protocol in plan §2;
    integration may swap to seed FakeMailchimpClient once slice A lands.

    Seeded with one default audience "fake-audience-1". Deterministic ids.
    """

    def __init__(self, *, api_key: Optional[str] = None, server_prefix: str = "us6"):
        self._server_prefix = server_prefix
        self._audiences: list[_Audience] = [
            _Audience(id="fake-audience-1", name="Test Audience", member_count=0)
        ]
        self._members: dict[str, dict[str, _Member]] = {
            "fake-audience-1": {}
        }  # audience_id → {hash: Member}
        self._segments: dict[str, dict[int, _Segment]] = {
            "fake-audience-1": {}
        }
        self._templates: dict[int, _Template] = {}
        self._campaigns: dict[str, _Campaign] = {}
        self._next_segment_id: int = 1
        self._next_template_id: int = 1
        self._next_campaign_web_id: int = 1
        self._next_campaign_seq: int = 1

    # ── Audiences ─────────────────────────────────────────────────────────

    async def ping(self) -> None:
        pass

    async def list_audiences(self, count: int = 25, offset: int = 0) -> _Page:
        items = self._audiences[offset: offset + count]
        return _Page(items=items, total=len(self._audiences))

    async def get_audience(self, audience_id: str) -> _Audience:
        for a in self._audiences:
            if a.id == audience_id:
                return a
        raise MailchimpNotFoundError(f"Audience {audience_id!r} not found")

    # ── Members ───────────────────────────────────────────────────────────

    def _ensure_audience_members(self, audience_id: str) -> dict[str, _Member]:
        if audience_id not in self._members:
            self._members[audience_id] = {}
        return self._members[audience_id]

    async def list_members(
        self,
        audience_id: str,
        *,
        status: Optional[str] = None,
        count: int = 25,
        offset: int = 0,
    ) -> _Page:
        members_map = self._ensure_audience_members(audience_id)
        items = list(members_map.values())
        if status:
            items = [m for m in items if m.status == status]
        return _Page(items=items[offset: offset + count], total=len(items))

    async def get_member(self, audience_id: str, email: str) -> _Member:
        members_map = self._ensure_audience_members(audience_id)
        m = members_map.get(_subscriber_hash(email))
        if m is None:
            raise MailchimpNotFoundError(f"Member {email!r} not found")
        return m

    async def upsert_member(
        self,
        audience_id: str,
        email: str,
        *,
        status: str = "subscribed",
        first_name: str = "",
        last_name: str = "",
        status_if_new: str = "subscribed",
    ) -> _Member:
        subscriber_hash = _subscriber_hash(email)
        members_map = self._ensure_audience_members(audience_id)
        existing = members_map.get(subscriber_hash)
        if existing:
            existing.status = status
            if first_name is not None:
                existing.first_name = first_name
            if last_name is not None:
                existing.last_name = last_name
            return existing
        m = _Member(
            email=email, status=status, first_name=first_name, last_name=last_name
        )
        members_map[subscriber_hash] = m
        return m

    async def set_member_tags(
        self,
        audience_id: str,
        email: str,
        *,
        active_tags: list[str],
        inactive_tags: Optional[list[str]] = None,
    ) -> None:
        members_map = self._ensure_audience_members(audience_id)
        m = members_map.get(_subscriber_hash(email))
        if m:
            m.tags = list(active_tags)

    async def archive_member(self, audience_id: str, email: str) -> None:
        members_map = self._ensure_audience_members(audience_id)
        m = members_map.get(_subscriber_hash(email))
        if m:
            m.status = "archived"
        else:
            raise MailchimpNotFoundError(f"Member {email!r} not found")

    # ── Segments ──────────────────────────────────────────────────────────

    def _ensure_audience_segments(self, audience_id: str) -> dict[int, _Segment]:
        if audience_id not in self._segments:
            self._segments[audience_id] = {}
        return self._segments[audience_id]

    async def list_segments(
        self, audience_id: str, count: int = 25, offset: int = 0
    ) -> _Page:
        segs = list(self._ensure_audience_segments(audience_id).values())
        return _Page(items=segs[offset: offset + count], total=len(segs))

    async def create_static_segment(self, audience_id: str, *, name: str) -> _Segment:
        segs = self._ensure_audience_segments(audience_id)
        seg_id = self._next_segment_id
        self._next_segment_id += 1
        seg = _Segment(id=seg_id, name=name, member_count=0)
        segs[seg_id] = seg
        return seg

    async def update_segment(
        self, audience_id: str, segment_id: int, *, name: str
    ) -> _Segment:
        segs = self._ensure_audience_segments(audience_id)
        if segment_id not in segs:
            raise MailchimpNotFoundError(f"Segment {segment_id} not found")
        segs[segment_id].name = name
        return segs[segment_id]

    async def delete_segment(self, audience_id: str, segment_id: int) -> None:
        segs = self._ensure_audience_segments(audience_id)
        if segment_id not in segs:
            raise MailchimpNotFoundError(f"Segment {segment_id} not found")
        del segs[segment_id]

    async def list_segment_members(
        self, audience_id: str, segment_id: int, count: int = 25, offset: int = 0
    ) -> _Page:
        segs = self._ensure_audience_segments(audience_id)
        if segment_id not in segs:
            raise MailchimpNotFoundError(f"Segment {segment_id} not found")
        seg = segs[segment_id]
        members_map = self._ensure_audience_members(audience_id)
        items = [members_map[h] for h in seg._members if h in members_map]
        return _Page(items=items[offset: offset + count], total=len(items))

    async def add_segment_member(
        self, audience_id: str, segment_id: int, *, email: str
    ) -> _Member:
        """Raises MailchimpRejectedError if email is not in the audience."""
        import hashlib
        h = hashlib.md5(email.strip().lower().encode()).hexdigest()
        members_map = self._ensure_audience_members(audience_id)
        if h not in members_map:
            raise MailchimpRejectedError(
                f"Email {email!r} is not subscribed to the audience. "
                "Add them as a contact first."
            )
        segs = self._ensure_audience_segments(audience_id)
        if segment_id not in segs:
            raise MailchimpNotFoundError(f"Segment {segment_id} not found")
        segs[segment_id]._members.add(h)
        segs[segment_id].member_count = len(segs[segment_id]._members)
        return members_map[h]

    async def remove_segment_member(
        self, audience_id: str, segment_id: int, email: str
    ) -> None:
        segs = self._ensure_audience_segments(audience_id)
        if segment_id not in segs:
            raise MailchimpNotFoundError(f"Segment {segment_id} not found")
        segs[segment_id]._members.discard(_subscriber_hash(email))
        segs[segment_id].member_count = len(segs[segment_id]._members)

    # ── Templates ─────────────────────────────────────────────────────────

    async def list_templates(
        self,
        *,
        count: int = 25,
        offset: int = 0,
    ) -> _Page:
        # Signature MUST mirror `MailchimpClient.list_templates` exactly. An
        # extra kwarg here (a `type=` filter the Protocol/Fake/Real never had)
        # let the router call `list_templates(type="user", ...)`, stayed green
        # in CI, and 500'd against the real client in prod (2026-09-01).
        items = list(self._templates.values())
        return _Page(items=items[offset: offset + count], total=len(items))

    async def get_template(self, template_id: int) -> _Template:
        t = self._templates.get(template_id)
        if t is None:
            raise MailchimpNotFoundError(f"Template {template_id} not found")
        return t

    async def create_template(self, *, name: str, html: str) -> _Template:
        tid = self._next_template_id
        self._next_template_id += 1
        t = _Template(id=tid, name=name, html=html, type="user")
        self._templates[tid] = t
        return t

    async def update_template(
        self,
        template_id: int,
        *,
        name: Optional[str] = None,
        html: Optional[str] = None,
    ) -> _Template:
        t = self._templates.get(template_id)
        if t is None:
            raise MailchimpNotFoundError(f"Template {template_id} not found")
        if name is not None:
            t.name = name
        if html is not None:
            t.html = html
        return t

    async def delete_template(self, template_id: int) -> None:
        if template_id not in self._templates:
            raise MailchimpNotFoundError(f"Template {template_id} not found")
        del self._templates[template_id]

    async def get_template_default_content(self, template_id: int) -> dict:
        return {}

    # ── Campaigns ─────────────────────────────────────────────────────────

    async def list_campaigns(self, count: int = 25, offset: int = 0) -> _Page:
        items = list(self._campaigns.values())
        return _Page(items=items[offset: offset + count], total=len(items))

    async def get_campaign(self, campaign_id: str) -> _Campaign:
        c = self._campaigns.get(campaign_id)
        if c is None:
            raise MailchimpNotFoundError(f"Campaign {campaign_id!r} not found")
        return c

    async def create_campaign(
        self,
        *,
        audience_id: str,
        title: str,
        subject_line: str,
        preview_text: Optional[str] = None,
        from_name: str,
        reply_to: str,
        segment_id: Optional[int] = None,
    ) -> _Campaign:
        cid = f"cmp{self._next_campaign_seq:04d}"
        self._next_campaign_seq += 1
        c = _Campaign(
            id=cid,
            web_id=self._next_campaign_web_id,
            title=title,
            status="save",
            subject_line=subject_line,
            preview_text=preview_text,
            from_name=from_name,
            reply_to=reply_to,
            segment_id=segment_id,
        )
        self._next_campaign_web_id += 1
        self._campaigns[cid] = c
        return c

    async def update_campaign(
        self,
        campaign_id: str,
        *,
        title: Optional[str] = None,
        subject_line: Optional[str] = None,
        preview_text: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        segment_id: Optional[int] = None,
        template_id: Optional[int] = None,
    ) -> _Campaign:
        c = self._campaigns.get(campaign_id)
        if c is None:
            raise MailchimpNotFoundError(f"Campaign {campaign_id!r} not found")
        if title is not None:
            c.title = title
        if subject_line is not None:
            c.subject_line = subject_line
        if preview_text is not None:
            c.preview_text = preview_text
        if from_name is not None:
            c.from_name = from_name
        if reply_to is not None:
            c.reply_to = reply_to
        if segment_id is not None:
            c.segment_id = segment_id
        return c

    async def delete_campaign(self, campaign_id: str) -> None:
        if campaign_id not in self._campaigns:
            raise MailchimpNotFoundError(f"Campaign {campaign_id!r} not found")
        del self._campaigns[campaign_id]

    async def set_campaign_content(
        self, campaign_id: str, *, template_id: Optional[int] = None
    ) -> None:
        c = self._campaigns.get(campaign_id)
        if c and template_id is not None:
            c.template_id = template_id

    async def send_campaign(self, campaign_id: str) -> None:
        c = self._campaigns.get(campaign_id)
        if c is None:
            raise MailchimpNotFoundError(f"Campaign {campaign_id!r} not found")
        c.status = "sent"

    async def schedule_campaign(self, campaign_id: str, *, schedule_time: str) -> None:
        c = self._campaigns.get(campaign_id)
        if c is None:
            raise MailchimpNotFoundError(f"Campaign {campaign_id!r} not found")
        c.status = "schedule"

    async def unschedule_campaign(self, campaign_id: str) -> None:
        c = self._campaigns.get(campaign_id)
        if c is None:
            raise MailchimpNotFoundError(f"Campaign {campaign_id!r} not found")
        c.status = "save"

    async def send_test(self, campaign_id: str, *, test_emails: list[str]) -> None:
        if campaign_id not in self._campaigns:
            raise MailchimpNotFoundError(f"Campaign {campaign_id!r} not found")


# ── SQLite schema for mailchimp_connections ───────────────────────────────────

_MAILCHIMP_SCHEMA = """
CREATE TABLE IF NOT EXISTS mailchimp_connections (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    marca_id     TEXT,
    encrypted_api_key TEXT NOT NULL,
    server_prefix TEXT NOT NULL,
    audience_id   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Mirror migration 019: at-most-one-per-scope via two partial unique indexes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_mc_conn_org_default
    ON mailchimp_connections (org_id) WHERE marca_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_mc_conn_org_client
    ON mailchimp_connections (org_id, marca_id) WHERE marca_id IS NOT NULL;
"""

# marcas table (subset of migration 007, renamed by 046) — lets the PUT route's
# client-ownership validation resolve a real cliente in tests.
_CLIENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS marcas (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'real_estate_agent',
    notes       TEXT,
    created_by  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ── Shared fixture: wired client + store + fake ───────────────────────────────

@pytest.fixture
def mailchimp_client(client, tmp_path: Path):
    """``client`` + SQLite-backed MailchimpConnectionStore + ContractFakeMailchimpClient.

    Overrides both DI seams:
      - ``get_mailchimp_store``          → SQLite store (real Fernet round-trip)
      - ``get_mailchimp_client_factory`` → ContractFakeMailchimpClient producer

    Yields ``(auth_client, store, fake_instance)`` so tests can inspect the
    in-memory fake state and pre-seed connection rows directly on the store.
    """
    from app.main import app
    from app.modules.mailchimp.deps import (
        get_mailchimp_client_factory,
        get_mailchimp_store,
    )

    db_path = tmp_path / "mailchimp_test.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_MAILCHIMP_SCHEMA)

    _fernet_key = Fernet.generate_key()
    store = MailchimpConnectionStore(
        SQLiteClient(db_path), fernet=Fernet(_fernet_key)
    )

    fake = ContractFakeMailchimpClient()

    def _fake_factory(*, api_key=None, server_prefix="us6"):
        return fake

    _prev_store = app.dependency_overrides.get(get_mailchimp_store)
    _prev_factory = app.dependency_overrides.get(get_mailchimp_client_factory)
    app.dependency_overrides[get_mailchimp_store] = lambda: store
    app.dependency_overrides[get_mailchimp_client_factory] = lambda: _fake_factory

    yield client, store, fake

    for dep, prev in (
        (get_mailchimp_store, _prev_store),
        (get_mailchimp_client_factory, _prev_factory),
    ):
        if prev is None:
            app.dependency_overrides.pop(dep, None)
        else:
            app.dependency_overrides[dep] = prev


@pytest.fixture
def mailchimp_client_with_clients(mailchimp_client, tmp_path: Path):
    """``mailchimp_client`` + a SQLite-backed ``MarcaService`` (migration 019).

    Overrides the ``get_marca_service`` DI seam so the connection PUT route's
    cliente-ownership validation resolves against a real ``marcas`` table.
    Seeds ONE cliente owned by the test org (``test-org-123`` → its coerced
    UUID) and ONE owned by a DIFFERENT org.

    Yields ``(auth_client, store, fake, org_marca_id, foreign_marca_id)``
    where ``org_marca_id`` belongs to the caller's org (validation passes) and
    ``foreign_marca_id`` belongs to another org (validation → 404).
    """
    from uuid import uuid4

    from app.dependencies import coerce_org_uuid
    from app.main import app
    from app.routers.marcas_router import get_marca_service
    from app.services.marcas_service import MarcaService

    org_id = coerce_org_uuid("test-org-123")
    org_client_id = uuid4()
    foreign_org_id = uuid4()
    foreign_client_id = uuid4()

    db_path = tmp_path / "mailchimp_clients_test.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_CLIENTS_SCHEMA)
        conn.executemany(
            "INSERT INTO marcas (id, org_id, slug, name, kind) VALUES (?,?,?,?,?)",
            [
                (str(org_client_id), str(org_id), "cliente-a", "Cliente A", "real_estate_agent"),
                (str(foreign_client_id), str(foreign_org_id), "cliente-x", "Cliente X", "real_estate_agent"),
            ],
        )
        conn.commit()

    svc = MarcaService(SQLiteClient(db_path))

    c, store, fake = mailchimp_client
    _prev = app.dependency_overrides.get(get_marca_service)
    app.dependency_overrides[get_marca_service] = lambda: svc

    yield c, store, fake, org_client_id, foreign_client_id

    if _prev is None:
        app.dependency_overrides.pop(get_marca_service, None)
    else:
        app.dependency_overrides[get_marca_service] = _prev


@pytest.fixture
def connected_mailchimp_client(mailchimp_client):
    """Like ``mailchimp_client`` but with a pre-seeded connection row.

    The store has an org_id=``"test-org-123"`` connection with
    server_prefix="us6", audience_id="fake-audience-1".
    """
    from uuid import UUID

    c, store, fake = mailchimp_client
    _fernet_key = Fernet.generate_key()
    # Re-build store with a known key for direct upsert
    import hashlib

    # Seed the connection via the API (PUT /connection) so the store
    # row is created normally.
    resp = c.put(
        "/api/mailchimp/connection",
        json={"api_key": "testkey-us6", "audience_id": "fake-audience-1"},
    )
    assert resp.status_code == 200, resp.text
    yield c, store, fake
