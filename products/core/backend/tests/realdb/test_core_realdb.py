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


class TestLicenseProvisioningTrigger:
    """Verify the on_license_change trigger fires successfully end-to-end.

    Regression guard for the 2026-04-09 → 2026-05-05 outage where the trigger
    referenced products.name (column is `nome`). PL/pgSQL parses function
    bodies lazily, so the bad column was only surfaced on the first license
    INSERT after deploy. This test seeds a real noctus_user (so the trigger's
    INSERT...SELECT into notifications has rows to scan), then asserts the
    notification was created — proving the COALESCE subquery resolved.
    """

    def test_grant_fires_notification_with_product_nome(self, admin_db, test_org, cleanup):
        # Seed a noctus_user in the org — required so the trigger's
        # INSERT INTO notifications SELECT ... FROM noctus_users WHERE org_id = ...
        # has at least one row, which forces the COALESCE subquery to evaluate.
        user_id = str(uuid.uuid4())
        admin_db.table("noctus_users").insert({
            "id": user_id,
            "email": f"trigger-{user_id[:8]}@realdb.test",
            "nome": "Trigger Test User",
            "org_id": test_org["id"],
            "role": "user",
        }).execute()
        cleanup.append(("noctus_users", user_id))

        product_nome = f"Trigger Product {uuid.uuid4().hex[:6]}"
        product = admin_db.table("products").insert({
            "nome": product_nome,
            "slug": f"trigger-prod-{uuid.uuid4().hex[:8]}",
            "url_base": "http://localhost:9999",
        }).execute().data[0]
        cleanup.append(("products", product["id"]))

        # The trigger fires on this insert. If the PL/pgSQL body has a bad
        # column ref (e.g. `name` instead of `nome`), the API call raises.
        lic = admin_db.table("licenses").insert({
            "org_id": test_org["id"],
            "product_id": product["id"],
            "status": "active",
        }).execute().data[0]
        cleanup.append(("licenses", lic["id"]))

        # Verify the trigger composed a notification using products.nome.
        notifs = admin_db.table("notifications") \
            .select("title, message, metadata") \
            .eq("user_id", user_id) \
            .eq("org_id", test_org["id"]) \
            .eq("type", "system") \
            .execute().data

        granted = [n for n in notifs if (n.get("metadata") or {}).get("license_id") == lic["id"]]
        assert len(granted) == 1, f"expected 1 grant notification for license {lic['id']}, got {len(granted)}: {notifs}"
        assert product_nome in granted[0]["message"], \
            f"notification message {granted[0]['message']!r} should include product nome {product_nome!r}"
        # Cleanup the notification (cascade may have left it)
        for n in granted:
            try:
                admin_db.table("notifications").delete().eq("user_id", user_id).execute()
                break
            except Exception:
                pass

    def test_revoke_does_not_raise(self, admin_db, test_org, cleanup):
        """Revoke path goes through deprovision_product — separate codepath."""
        user_id = str(uuid.uuid4())
        admin_db.table("noctus_users").insert({
            "id": user_id,
            "email": f"revoke-{user_id[:8]}@realdb.test",
            "nome": "Revoke Test User",
            "org_id": test_org["id"],
            "role": "user",
        }).execute()
        cleanup.append(("noctus_users", user_id))

        product = admin_db.table("products").insert({
            "nome": "Revoke Trigger Product",
            "slug": f"revoke-prod-{uuid.uuid4().hex[:8]}",
            "url_base": "http://localhost:9999",
        }).execute().data[0]
        cleanup.append(("products", product["id"]))

        lic = admin_db.table("licenses").insert({
            "org_id": test_org["id"],
            "product_id": product["id"],
            "status": "active",
        }).execute().data[0]
        cleanup.append(("licenses", lic["id"]))

        # The UPDATE → revoked branch invokes deprovision_product(v_org_id, v_slug).
        admin_db.table("licenses") \
            .update({"status": "revoked"}) \
            .eq("id", lic["id"]) \
            .execute()
        # Best assert is "no exception raised" — the API call would have raised
        # if the trigger errored. Re-read to confirm state.
        after = admin_db.table("licenses") \
            .select("status").eq("id", lic["id"]).single().execute().data
        assert after["status"] == "revoked"

        admin_db.table("notifications").delete().eq("user_id", user_id).execute()


class TestPostgRESTErrors:
    """.single() on 0 rows raises a real APIError (PGRST116)."""

    def test_single_not_found_raises_pgrst116(self, admin_db):
        fake_id = str(uuid.uuid4())
        with pytest.raises(APIError) as exc_info:
            admin_db.table("organizations") \
                .select("*").eq("id", fake_id).single().execute()
        # PGRST116 = "The result contains 0 rows"
        assert "PGRST116" in str(exc_info.value) or "0 rows" in str(exc_info.value)
