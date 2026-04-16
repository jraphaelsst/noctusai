"""Unit tests for ContactService."""
from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.services.contact_service import ContactService

ORG = "org-test-001"


# ---------------------------------------------------------------------------
# list_contacts()
# ---------------------------------------------------------------------------

class TestListContacts:
    def test_returns_paginated_results(self):
        contacts = [
            {"id": "c1", "email": "a@test.com", "org_id": ORG},
            {"id": "c2", "email": "b@test.com", "org_id": ORG},
        ]
        db = MockSupabaseClient()
        db.set_table_data("contacts", contacts)

        svc = ContactService(db, ORG)
        data, total = svc.list_contacts(page=1, page_size=20)

        assert len(data) == 2
        assert total == 2

    def test_returns_empty_when_no_contacts(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [])

        svc = ContactService(db, ORG)
        data, total = svc.list_contacts()

        assert data == []
        assert total == 0

    def test_accepts_status_filter(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [{"id": "c1", "status": "active"}])

        svc = ContactService(db, ORG)
        data, total = svc.list_contacts(status="active")

        assert len(data) == 1

    def test_accepts_search_filter(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [{"id": "c1", "nome": "Maria"}])

        svc = ContactService(db, ORG)
        data, _ = svc.list_contacts(search="Maria")

        # Mock does not filter — we just verify the call chain works
        assert isinstance(data, list)

    def test_accepts_tags_filter(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [{"id": "c1", "tags": ["vip"]}])

        svc = ContactService(db, ORG)
        data, _ = svc.list_contacts(tags=["vip"])

        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# create_contact()
# ---------------------------------------------------------------------------

class TestCreateContact:
    def test_sets_org_id(self):
        db = MockSupabaseClient()
        created = {"id": "c1", "email": "new@test.com", "org_id": ORG}
        db.set_table_data("contacts", [created])

        svc = ContactService(db, ORG)
        data = {"email": "new@test.com", "nome": "Novo"}
        result = svc.create_contact(data)

        assert data["org_id"] == ORG
        assert result is not None

    def test_returns_created_contact(self):
        db = MockSupabaseClient()
        contact = {"id": "c1", "email": "a@test.com", "org_id": ORG, "nome": "A"}
        db.set_table_data("contacts", [contact])

        svc = ContactService(db, ORG)
        result = svc.create_contact({"email": "a@test.com", "nome": "A"})

        assert result["id"] == "c1"


# ---------------------------------------------------------------------------
# update_contact()
# ---------------------------------------------------------------------------

class TestUpdateContact:
    def test_partial_update(self):
        db = MockSupabaseClient()
        updated = {"id": "c1", "nome": "Updated", "org_id": ORG}
        db.set_table_data("contacts", [updated])

        svc = ContactService(db, ORG)
        data = {"nome": "Updated"}
        result = svc.update_contact("c1", data)

        assert result is not None
        assert result["nome"] == "Updated"
        assert data["updated_at"] == "now()"

    def test_returns_none_when_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [])

        svc = ContactService(db, ORG)
        result = svc.update_contact("missing", {"nome": "X"})

        assert result is None


# ---------------------------------------------------------------------------
# delete_contact()
# ---------------------------------------------------------------------------

class TestDeleteContact:
    def test_removes_by_id_and_org(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [])

        svc = ContactService(db, ORG)
        result = svc.delete_contact("c1")

        assert result is True


# ---------------------------------------------------------------------------
# import_contacts()
# ---------------------------------------------------------------------------

class TestImportContacts:
    def test_batch_upsert_sets_source_import(self):
        db = MockSupabaseClient()
        imported = {"id": "c1", "email": "a@test.com", "org_id": ORG, "source": "import"}
        db.set_table_data("contacts", [imported])

        svc = ContactService(db, ORG)
        contacts = [
            {"email": "a@test.com", "nome": "A"},
            {"email": "b@test.com", "nome": "B"},
        ]
        result = svc.import_contacts(contacts)

        assert result["total"] == 2
        # All contacts should have source set to 'import'
        for c in contacts:
            assert c["source"] == "import"
            assert c["org_id"] == ORG

    def test_import_sets_org_id_on_all_contacts(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [{"id": "c1"}])

        svc = ContactService(db, ORG)
        contacts = [{"email": "x@test.com"}]
        svc.import_contacts(contacts)

        assert contacts[0]["org_id"] == ORG

    def test_import_returns_count(self):
        db = MockSupabaseClient()
        db.set_table_data("contacts", [{"id": "c1"}])

        svc = ContactService(db, ORG)
        contacts = [
            {"email": "a@test.com"},
            {"email": "b@test.com"},
            {"email": "c@test.com"},
        ]
        result = svc.import_contacts(contacts)

        assert result["total"] == 3
        # Each upsert returns mock data with 1 row, so imported == total
        assert result["imported"] == 3

    def test_import_empty_list(self):
        db = MockSupabaseClient()
        svc = ContactService(db, ORG)
        result = svc.import_contacts([])

        assert result == {"imported": 0, "total": 0}
