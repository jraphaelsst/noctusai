"""
Real-DB integration tests for the NoctusAI Core backend.

These tests hit a real Supabase instance to verify SQL filtering, FK constraints,
unique constraints, and PostgREST error handling that mocks cannot cover.

Run: pytest tests/realdb/ -v
Skip: auto-skips when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set.
"""
from __future__ import annotations

import uuid

import pytest
from postgrest.exceptions import APIError

pytestmark = pytest.mark.realdb


class TestOrganizationCRUD:
    """Full CRUD cycle on the organizations table."""

    def test_organization_crud(self, admin_db, cleanup):
        slug = f"test-crud-{uuid.uuid4().hex[:8]}"

        # Create
        created = admin_db.table("organizations").insert({
            "nome": "Test Org CRUD",
            "slug": slug,
            "plano": "free",
            "category": "test",
        }).execute().data[0]
        cleanup.append(("organizations", created["id"]))
        assert created["nome"] == "Test Org CRUD"
        assert created["slug"] == slug

        # Read
        fetched = admin_db.table("organizations") \
            .select("*").eq("id", created["id"]).single().execute().data
        assert fetched["id"] == created["id"]

        # Update
        admin_db.table("organizations") \
            .update({"nome": "Updated Org"}).eq("id", created["id"]).execute()
        updated = admin_db.table("organizations") \
            .select("nome").eq("id", created["id"]).single().execute().data
        assert updated["nome"] == "Updated Org"

        # Delete
        admin_db.table("organizations").delete().eq("id", created["id"]).execute()
        check = admin_db.table("organizations") \
            .select("id").eq("id", created["id"]).execute().data
        assert check == []
        # Remove from cleanup since already deleted
        cleanup.pop()

    def test_organization_slug_uniqueness(self, admin_db, cleanup):
        slug = f"test-uniq-{uuid.uuid4().hex[:8]}"
        org1 = admin_db.table("organizations").insert({
            "nome": "Org A", "slug": slug, "plano": "free", "category": "test",
        }).execute().data[0]
        cleanup.append(("organizations", org1["id"]))

        with pytest.raises(APIError):
            admin_db.table("organizations").insert({
                "nome": "Org B", "slug": slug, "plano": "free", "category": "test",
            }).execute()


class TestProductAndLicenseCRUD:
    """Verify product + license FK chain."""

    def test_product_and_license_crud(self, admin_db, test_org, cleanup):
        # Create product
        product = admin_db.table("products").insert({
            "nome": "Test Product",
            "slug": f"test-prod-{uuid.uuid4().hex[:8]}",
            "url_base": "http://localhost:9999",
        }).execute().data[0]
        cleanup.append(("products", product["id"]))

        # Create license linking org → product
        lic = admin_db.table("licenses").insert({
            "org_id": test_org["id"],
            "product_id": product["id"],
            "status": "active",
        }).execute().data[0]
        cleanup.append(("licenses", lic["id"]))

        assert lic["org_id"] == test_org["id"]
        assert lic["product_id"] == product["id"]
        assert lic["status"] == "active"

        # Verify read-back
        fetched = admin_db.table("licenses") \
            .select("*").eq("id", lic["id"]).single().execute().data
        assert fetched["org_id"] == test_org["id"]


class TestNoctusUserCRUD:
    """Profile CRUD in the noctus_users table."""

    def test_noctus_user_crud(self, admin_db, test_org, cleanup):
        user_id = str(uuid.uuid4())
        user = admin_db.table("noctus_users").insert({
            "id": user_id,
            "email": f"user-{user_id[:8]}@realdb.test",
            "nome": "Test User",
            "org_id": test_org["id"],
            "role": "user",
        }).execute().data[0]
        cleanup.append(("noctus_users", user["id"]))

        assert user["nome"] == "Test User"
        assert user["org_id"] == test_org["id"]

        # Update
        admin_db.table("noctus_users") \
            .update({"nome": "Updated User"}).eq("id", user_id).execute()
        updated = admin_db.table("noctus_users") \
            .select("nome").eq("id", user_id).single().execute().data
        assert updated["nome"] == "Updated User"


class TestNotificationCRUD:
    """Insert, read, mark-read, and delete a notification."""

    def test_notification_crud(self, admin_db, test_org, cleanup):
        # Need a noctus_user for FK
        user_id = str(uuid.uuid4())
        user = admin_db.table("noctus_users").insert({
            "id": user_id,
            "email": f"notif-{user_id[:8]}@realdb.test",
            "nome": "Notif User",
            "org_id": test_org["id"],
            "role": "user",
        }).execute().data[0]
        cleanup.append(("noctus_users", user_id))

        notif = admin_db.table("notifications").insert({
            "user_id": user_id,
            "org_id": test_org["id"],
            "type": "system",
            "title": "Test Notification",
            "message": "Real-DB test notification",
        }).execute().data[0]
        cleanup.append(("notifications", notif["id"]))

        assert notif["read"] is False

        # Mark as read
        admin_db.table("notifications") \
            .update({"read": True}).eq("id", notif["id"]).execute()
        updated = admin_db.table("notifications") \
            .select("read").eq("id", notif["id"]).single().execute().data
        assert updated["read"] is True


class TestAuditLogInsertAndFilter:
    """Insert audit entries and verify filtering by action."""

    def test_audit_log_insert_and_filter(self, admin_db, test_org, cleanup):
        entries = []
        for action in ["create", "update", "delete"]:
            entry = admin_db.table("audit_logs").insert({
                "org_id": test_org["id"],
                "action": action,
                "resource_type": "realdb_test",
                "resource_id": str(uuid.uuid4()),
            }).execute().data[0]
            entries.append(entry)
            cleanup.append(("audit_logs", entry["id"]))

        # Filter by action
        creates = admin_db.table("audit_logs") \
            .select("*") \
            .eq("org_id", test_org["id"]) \
            .eq("action", "create") \
            .eq("resource_type", "realdb_test") \
            .execute().data
        assert len(creates) == 1
        assert creates[0]["action"] == "create"


class TestPostgRESTErrors:
    """.single() on 0 rows raises a real APIError (PGRST116)."""

    def test_single_not_found_raises_pgrst116(self, admin_db):
        fake_id = str(uuid.uuid4())
        with pytest.raises(APIError) as exc_info:
            admin_db.table("organizations") \
                .select("*").eq("id", fake_id).single().execute()
        # PGRST116 = "The result contains 0 rows"
        assert "PGRST116" in str(exc_info.value) or "0 rows" in str(exc_info.value)
