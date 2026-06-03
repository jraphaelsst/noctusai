"""
Tests for ClientsService — CRUD against MockSupabaseClient (no monkeypatching).

read-side: seeded via MockSupabaseClient(data=[...])
write-side: asserted via table.inserted_payloads / table.updated_payloads
"""
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.clients_service import ClientsService

ORG = UUID("00000000-0000-0000-0000-000000000abc")


def _row(**over) -> dict:
    base = {
        "id": "c-1",
        "org_id": str(ORG),
        "name": "Cliente Teste",
        "email": "t@t.com",
        "phone": None,
        "company": None,
        "monthly_value": 1500.0,
        "due_date": 10,
        "active": True,
        "default_billing_type": "manual",
        "billing_automation_enabled": False,
        "report_token": "tok-abc",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    return db, ClientsService(db, org_id=ORG)


class TestClientsList:
    def test_list_returns_seeded_rows(self):
        _db, svc = _svc([_row()])
        result = svc.list()
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "Cliente Teste"

    def test_list_empty(self):
        _db, svc = _svc([])
        result = svc.list()
        assert result["items"] == []

    def test_list_pagination_shape(self):
        rows = [_row(id=f"c-{i}", name=f"C{i}") for i in range(5)]
        _db, svc = _svc(rows)
        result = svc.list(page=1, page_size=50)
        assert result["page"] == 1
        assert result["page_size"] == 50


class TestClientsGet:
    def test_get_existing(self):
        _db, svc = _svc([_row(id="c-9")])
        row = svc.get("c-9")
        assert row is not None
        assert row["id"] == "c-9"

    def test_get_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.get("nope") is None


class TestClientsCreate:
    def test_create_stamps_org_id(self):
        db, svc = _svc([])
        row = svc.create({"name": "Novo Cliente"})
        assert row["name"] == "Novo Cliente"
        inserted = db.table("clients").inserted_payloads
        assert any(p.get("org_id") == str(ORG) and p.get("name") == "Novo Cliente" for p in inserted), inserted

    def test_create_includes_all_fields(self):
        db, svc = _svc([])
        svc.create({"name": "X", "email": "x@x.com", "monthly_value": 999.0})
        inserted = db.table("clients").inserted_payloads
        assert any(p.get("email") == "x@x.com" for p in inserted)


class TestClientsUpdate:
    def test_update_patches_row(self):
        db, svc = _svc([_row(id="c-1", name="Old")])
        updated = svc.update("c-1", {"name": "New"})
        assert updated is not None
        assert any(p.get("name") == "New" for p in db.table("clients").updated_payloads)

    def test_update_missing_returns_none(self):
        _db, svc = _svc([])
        assert svc.update("ghost", {"name": "x"}) is None

    def test_update_strips_org_id_escalation(self):
        db, svc = _svc([_row(id="c-1")])
        svc.update("c-1", {"name": "ok", "org_id": "attacker-org"})
        # org_id should not appear in updated payload
        updated = db.table("clients").updated_payloads
        assert not any(p.get("org_id") == "attacker-org" for p in updated)


class TestClientsArchive:
    def test_archive_sets_active_false(self):
        db, svc = _svc([_row(id="c-1")])
        ok = svc.archive("c-1")
        assert ok is True
        assert any(p.get("active") is False for p in db.table("clients").updated_payloads)

    def test_archive_missing_returns_false(self):
        _db, svc = _svc([])
        assert svc.archive("ghost") is False
