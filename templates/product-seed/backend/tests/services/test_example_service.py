"""
Tests for ``ExampleService`` — the canonical page-scoped-CRUD service.

These exercise the **real** CRUD logic against a data-seeded
``MockSupabaseClient`` (schema-bound to ``seed`` like the production
client) — no monkeypatching of our own code (the no-workarounds rule):
reads come from seeded rows, write side-effects are asserted via
``inserted_payloads`` / ``updated_payloads`` (the `MockRequestBuilder`
read-side seam).

The service methods are ``async``; we drive them with ``asyncio.run`` so
the suite needs no pytest-asyncio config.

This is the backend half of the product-internal-wiring rule's
page-scoped-CRUD reference. TODO(new-product): rename to your domain.
"""
import asyncio
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.example_service import ExampleService, ExampleServiceError

ORG = UUID("00000000-0000-0000-0000-000000000123")


def _row(**over) -> dict:
    base = {
        "id": "ex-1",
        "org_id": str(ORG),
        "title": "Exemplo A",
        "description": None,
        "ativo": True,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="{{SCHEMA_NAME}}")
    return db, ExampleService(db, org_id=ORG)


class TestExampleServiceRead:
    def test_list_returns_seeded_active_rows(self):
        db, svc = _svc([_row(title="Visível")])
        result = asyncio.run(svc.list())
        assert result["next_cursor"] is None
        assert [r["title"] for r in result["items"]] == ["Visível"]

    def test_list_empty_returns_empty_items(self):
        _db, svc = _svc([])
        result = asyncio.run(svc.list())
        assert result["items"] == []

    def test_get_existing_returns_row(self):
        _db, svc = _svc([_row(id="ex-9", title="Achável")])
        row = asyncio.run(svc.get(example_id="ex-9"))
        assert row is not None
        assert row["title"] == "Achável"

    def test_get_missing_returns_none(self):
        _db, svc = _svc([])
        assert asyncio.run(svc.get(example_id="nope")) is None


class TestExampleServiceWrite:
    def test_create_inserts_with_org_id_stamped(self):
        db, svc = _svc([])
        row = asyncio.run(svc.create(payload={"title": "Novo", "description": "d"}))
        assert row["title"] == "Novo"
        inserted = db.table("examples").inserted_payloads
        assert any(
            p.get("org_id") == str(ORG) and p.get("title") == "Novo"
            for p in inserted
        ), inserted

    def test_update_patches_and_returns_row(self):
        db, svc = _svc([_row(id="ex-1", title="Antigo")])
        updated = asyncio.run(svc.update(example_id="ex-1", payload={"title": "Renomeado"}))
        assert updated is not None
        assert updated["title"] == "Renomeado"
        assert any(p.get("title") == "Renomeado" for p in db.table("examples").updated_payloads)

    def test_update_missing_returns_none(self):
        _db, svc = _svc([])
        assert asyncio.run(svc.update(example_id="ghost", payload={"title": "X"})) is None

    def test_delete_soft_deletes_via_ativo_false(self):
        db, svc = _svc([_row(id="ex-1")])
        ok = asyncio.run(svc.delete(example_id="ex-1"))
        assert ok is True
        assert any(p.get("ativo") is False for p in db.table("examples").updated_payloads)

    def test_delete_missing_returns_false(self):
        _db, svc = _svc([])
        assert asyncio.run(svc.delete(example_id="ghost")) is False
