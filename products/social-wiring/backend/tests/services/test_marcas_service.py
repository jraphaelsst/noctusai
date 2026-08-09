"""Tests for MarcaService — per-org marcas CRUD.

Exercised against a real SQLite client so the tests catch actual
write→read propagation, UNIQUE constraints, and round-trips.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.services.marcas_service import (
    Marca,
    MarcaNotFound,
    MarcaService,
    build_marca_service,
)
from app.sqlite_client import SQLiteClient

_ORG_A = UUID("00000000-0000-4000-8000-000000000001")
_ORG_B = UUID("00000000-0000-4000-8000-000000000002")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS marcas (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'real_estate_agent',
    notes       TEXT,
    created_by  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (org_id, slug)
);
"""


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "marcas.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def svc(sqlite_db: SQLiteClient) -> MarcaService:
    return build_marca_service(sqlite_db)


def _make(svc: MarcaService, *, org_id=_ORG_A, slug="agent-1", name="Agent One", kind="real_estate_agent", notes=None) -> Marca:
    return svc.create_marca(org_id=org_id, slug=slug, name=name, kind=kind, notes=notes)


# ─── create ──────────────────────────────────────────────────────────────────
class TestCreate:
    def test_returns_client(self, svc):
        c = _make(svc)
        assert isinstance(c, Marca)
        assert c.slug == "agent-1"
        assert c.name == "Agent One"
        assert c.org_id == _ORG_A
        assert isinstance(c.id, UUID)

    def test_default_kind(self, svc):
        c = _make(svc)
        assert c.kind == "real_estate_agent"

    def test_notes_none_by_default(self, svc):
        c = _make(svc)
        assert c.notes is None

    def test_notes_stored(self, svc):
        c = _make(svc, notes="VIP client")
        assert c.notes == "VIP client"


# ─── list / get ───────────────────────────────────────────────────────────────
class TestListGet:
    def test_list_empty(self, svc):
        assert svc.list_marcas(org_id=_ORG_A) == []

    def test_list_returns_created(self, svc):
        _make(svc, slug="a", name="A")
        _make(svc, slug="b", name="B")
        marcas = svc.list_marcas(org_id=_ORG_A)
        assert len(marcas) == 2

    def test_org_isolation(self, svc):
        _make(svc, org_id=_ORG_B, slug="b-client")
        assert svc.list_marcas(org_id=_ORG_A) == []

    def test_get_existing(self, svc):
        c = _make(svc)
        fetched = svc.get_marca(c.id, _ORG_A)
        assert fetched is not None
        assert fetched.id == c.id

    def test_get_nonexistent_returns_none(self, svc):
        assert svc.get_marca(uuid4(), _ORG_A) is None

    def test_get_wrong_org_returns_none(self, svc):
        c = _make(svc, org_id=_ORG_B)
        assert svc.get_marca(c.id, _ORG_A) is None


# ─── update ──────────────────────────────────────────────────────────────────
class TestUpdate:
    def test_update_name(self, svc):
        c = _make(svc, name="Old")
        updated = svc.update_marca(c.id, _ORG_A, name="New")
        assert updated.name == "New"

    def test_update_slug(self, svc):
        c = _make(svc, slug="old-slug")
        updated = svc.update_marca(c.id, _ORG_A, slug="new-slug")
        assert updated.slug == "new-slug"

    def test_update_notes(self, svc):
        c = _make(svc)
        updated = svc.update_marca(c.id, _ORG_A, notes="Important")
        assert updated.notes == "Important"

    def test_no_op_returns_current(self, svc):
        c = _make(svc, name="Stable")
        result = svc.update_marca(c.id, _ORG_A)
        assert result.name == "Stable"

    def test_update_wrong_org_raises(self, svc):
        c = _make(svc, org_id=_ORG_B)
        with pytest.raises(MarcaNotFound):
            svc.update_marca(c.id, _ORG_A, name="Hijack")


# ─── delete ──────────────────────────────────────────────────────────────────
class TestDelete:
    def test_delete_existing(self, svc):
        c = _make(svc)
        assert svc.delete_marca(c.id, _ORG_A) is True
        assert svc.get_marca(c.id, _ORG_A) is None

    def test_delete_nonexistent_returns_false(self, svc):
        assert svc.delete_marca(uuid4(), _ORG_A) is False

    def test_delete_wrong_org_returns_false(self, svc):
        c = _make(svc, org_id=_ORG_B)
        assert svc.delete_marca(c.id, _ORG_A) is False


# ─── build_marca_service ──────────────────────────────────────────────────────
class TestBuildService:
    def test_returns_client_service(self, sqlite_db):
        svc = build_marca_service(sqlite_db)
        assert isinstance(svc, MarcaService)
