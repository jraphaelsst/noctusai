"""
Real-DB integration tests for the Orbity reports organ.

Tests hit a real Supabase instance to verify:
  - Table creation and RLS policy application (migration 012)
  - Full round-trip CRUD for reports + report_snapshots
  - CHECK constraints (status ∈ {draft, published})
  - public_token uniqueness (UNIQUE constraint)
  - RLS org isolation: org A reports are invisible to an anon/wrong-org client
  - Public token read round-trip (service_role fetch by token → validate → return)

Run only (requires migration 012 applied + Supabase credentials):
  pytest products/orbity/backend/tests/realdb/test_reports_realdb.py -v -m realdb

Skip condition: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set.

PENDING-MIGRATION-APPLY: migration 012_reports.sql must be applied to the
live Supabase project by the tech-lead before these tests are run.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from postgrest.exceptions import APIError

pytestmark = pytest.mark.realdb


# ---------------------------------------------------------------------------
# Reports — round-trip CRUD
# ---------------------------------------------------------------------------

class TestReportCRUD:
    """Full CRUD on orbity.reports."""

    def test_report_crud(self, orbity_db, test_org, cleanup):
        # Create
        report = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "Relatório Maio 2026",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "status": "draft",
        }).execute().data[0]
        cleanup.append(("reports", report["id"]))

        assert report["name"] == "Relatório Maio 2026"
        assert report["status"] == "draft"
        assert report["public_token"] is not None  # auto-generated UUID
        assert report["config"] == {}

        # Read
        fetched = orbity_db.table("reports") \
            .select("*").eq("id", report["id"]).single().execute().data
        assert fetched["org_id"] == test_org["id"]

        # Update — publish
        orbity_db.table("reports") \
            .update({"status": "published"}).eq("id", report["id"]).execute()
        updated = orbity_db.table("reports") \
            .select("status").eq("id", report["id"]).single().execute().data
        assert updated["status"] == "published"

        # Delete
        orbity_db.table("reports").delete().eq("id", report["id"]).execute()
        check = orbity_db.table("reports").select("id").eq("id", report["id"]).execute().data
        assert check == []
        cleanup.pop()


class TestReportConstraints:
    """CHECK constraints and UNIQUE on reports."""

    def test_invalid_status_rejected(self, orbity_db, test_org):
        with pytest.raises(APIError):
            orbity_db.table("reports").insert({
                "org_id": test_org["id"],
                "name": "Bad Status",
                "period_start": "2026-05-01",
                "period_end": "2026-05-31",
                "status": "archived",  # not in ('draft', 'published')
            }).execute()

    def test_public_token_unique_constraint(self, orbity_db, test_org, cleanup):
        """Two reports cannot share the same public_token."""
        shared_token = str(uuid.uuid4())

        r1 = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "Report 1",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "public_token": shared_token,
            "status": "draft",
        }).execute().data[0]
        cleanup.append(("reports", r1["id"]))

        with pytest.raises(APIError):
            orbity_db.table("reports").insert({
                "org_id": test_org["id"],
                "name": "Report 2",
                "period_start": "2026-05-01",
                "period_end": "2026-05-31",
                "public_token": shared_token,  # duplicate
                "status": "draft",
            }).execute()


# ---------------------------------------------------------------------------
# Report snapshots — round-trip
# ---------------------------------------------------------------------------

class TestReportSnapshotCRUD:
    """Full round-trip for report_snapshots."""

    def test_snapshot_crud(self, orbity_db, test_org, cleanup):
        # Create parent report
        report = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "Relatório com Snapshot",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "status": "draft",
        }).execute().data[0]
        cleanup.append(("reports", report["id"]))

        payload = {
            "period": {"start": "2026-05-01", "end": "2026-05-31"},
            "leads": {"total": 42, "hot": 10, "warm": 18, "cold": 14},
            "revenues": {"total": 15000.0, "count": 3},
            "expenses": {"total": 8000.0, "count": 5},
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        snap = orbity_db.table("report_snapshots").insert({
            "org_id": test_org["id"],
            "report_id": report["id"],
            "payload": payload,
        }).execute().data[0]
        cleanup.append(("report_snapshots", snap["id"]))

        assert snap["report_id"] == report["id"]
        assert snap["payload"]["leads"]["total"] == 42

        # Read back latest snapshot
        snaps = orbity_db.table("report_snapshots") \
            .select("*") \
            .eq("report_id", report["id"]) \
            .order("generated_at", desc=True) \
            .execute().data
        assert len(snaps) >= 1
        assert snaps[0]["payload"]["leads"]["hot"] == 10

    def test_snapshot_cascade_delete(self, orbity_db, test_org):
        """Deleting a report cascades to its snapshots (ON DELETE CASCADE)."""
        report = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "Report to delete",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "status": "draft",
        }).execute().data[0]

        snap = orbity_db.table("report_snapshots").insert({
            "org_id": test_org["id"],
            "report_id": report["id"],
            "payload": {"test": True},
        }).execute().data[0]

        # Delete parent → snapshot should cascade
        orbity_db.table("reports").delete().eq("id", report["id"]).execute()
        check = orbity_db.table("report_snapshots") \
            .select("id").eq("id", snap["id"]).execute().data
        assert check == []


# ---------------------------------------------------------------------------
# RLS isolation
# ---------------------------------------------------------------------------

class TestReportRLSIsolation:
    """Org A reports are invisible to anon/wrong-org clients."""

    def test_anon_cannot_see_org_reports(self, orbity_db, anon_fin_db, test_org, cleanup):
        """Service_role inserts a row; anon_key (no org claim) sees nothing."""
        report = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "RLS Test Report",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "status": "draft",
        }).execute().data[0]
        cleanup.append(("reports", report["id"]))

        # Anon client → current_org_id() returns NULL → RLS filters all rows
        rows = anon_fin_db.table("reports").select("id").execute().data
        assert all(r["id"] != report["id"] for r in rows)

    def test_anon_cannot_see_snapshots(self, orbity_db, anon_fin_db, test_org, cleanup):
        """Snapshot rows are RLS-protected too."""
        report = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "RLS Snapshot Test",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "status": "draft",
        }).execute().data[0]
        cleanup.append(("reports", report["id"]))

        snap = orbity_db.table("report_snapshots").insert({
            "org_id": test_org["id"],
            "report_id": report["id"],
            "payload": {"test": True},
        }).execute().data[0]
        cleanup.append(("report_snapshots", snap["id"]))

        rows = anon_fin_db.table("report_snapshots").select("id").execute().data
        assert all(r["id"] != snap["id"] for r in rows)


# ---------------------------------------------------------------------------
# Public token read round-trip
# ---------------------------------------------------------------------------

class TestPublicTokenRead:
    """Service_role fetch-by-token simulates the public endpoint's server-side path."""

    def test_public_token_lookup_returns_published_report(self, orbity_db, test_org, cleanup):
        """Validate token → published → not-expired → snapshot available."""
        report = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "Relatório Público",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "status": "published",
        }).execute().data[0]
        cleanup.append(("reports", report["id"]))

        token = report["public_token"]

        snap = orbity_db.table("report_snapshots").insert({
            "org_id": test_org["id"],
            "report_id": report["id"],
            "payload": {
                "period": {"start": "2026-05-01", "end": "2026-05-31"},
                "leads": {"total": 7, "hot": 2, "warm": 3, "cold": 2},
                "revenues": {"total": 5000.0, "count": 1},
                "expenses": {"total": 2000.0, "count": 2},
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            },
        }).execute().data[0]
        cleanup.append(("report_snapshots", snap["id"]))

        # Server-side token lookup (service_role — mirrors ReportsPublicService)
        reports = orbity_db.table("reports") \
            .select("*").eq("public_token", token).execute().data
        assert len(reports) == 1
        assert reports[0]["status"] == "published"
        assert reports[0]["expires_at"] is None  # not expired

        # Fetch latest snapshot
        snaps = orbity_db.table("report_snapshots") \
            .select("*") \
            .eq("report_id", reports[0]["id"]) \
            .order("generated_at", desc=True) \
            .limit(1) \
            .execute().data
        assert len(snaps) == 1
        assert snaps[0]["payload"]["leads"]["total"] == 7

    def test_draft_report_excluded_from_public_path(self, orbity_db, test_org, cleanup):
        """A draft report exists in DB but the service_role lookup by token finds it —
        the SERVICE (not DB) must reject it. This test verifies the status field
        is correctly stored for the server to check."""
        report = orbity_db.table("reports").insert({
            "org_id": test_org["id"],
            "name": "Draft — Not Public",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "status": "draft",
        }).execute().data[0]
        cleanup.append(("reports", report["id"]))

        token = report["public_token"]
        rows = orbity_db.table("reports").select("status").eq("public_token", token).execute().data
        assert len(rows) == 1
        # Service would check status == "published" → reject this row
        assert rows[0]["status"] == "draft"
