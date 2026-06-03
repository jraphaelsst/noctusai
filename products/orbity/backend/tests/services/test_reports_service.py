"""
Tests for ReportsService and ReportsPublicService.

No monkeypatching of our own code.
Read-side: MockSupabaseClient(data=[...]) or set_table_data per table.
Write-side: inserted_payloads.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timezone

import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.services.reports_service import (
    ReportsPublicService,
    ReportsService,
    _to_iso_date,
    _parse_dt,
)

ORG = uuid.UUID("00000000-0000-0000-0000-000000000999")
NOW = datetime.now(tz=timezone.utc).isoformat()


def _report(
    id_: str | None = None,
    status: str = "draft",
    expires_at=None,
    period_start: str = "2026-05-01",
    period_end: str = "2026-05-31",
) -> dict:
    return {
        "id": id_ or str(uuid.uuid4()),
        "org_id": str(ORG),
        "client_id": None,
        "name": "Relatório Teste",
        "public_token": str(uuid.uuid4()),
        "period_start": period_start,
        "period_end": period_end,
        "config": {},
        "status": status,
        "expires_at": expires_at,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _snapshot(report_id: str, payload: dict | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "org_id": str(ORG),
        "report_id": report_id,
        "generated_at": NOW,
        "payload": payload or {"leads": {"total": 5}},
    }


def _svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    return db, ReportsService(db, org_id=ORG)


def _pub_svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    return db, ReportsPublicService(db)


# ---------------------------------------------------------------------------
# Helpers unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_to_iso_date_from_string(self):
        assert _to_iso_date("2026-05-01T10:00:00+00:00") == "2026-05-01"

    def test_to_iso_date_from_date_obj(self):
        assert _to_iso_date(date(2026, 5, 1)) == "2026-05-01"

    def test_parse_dt_from_string_with_z(self):
        dt = _parse_dt("2026-01-01T00:00:00Z")
        assert dt.tzinfo is not None

    def test_parse_dt_from_string_with_offset(self):
        dt = _parse_dt("2026-01-01T00:00:00+00:00")
        assert dt.tzinfo is not None

    def test_parse_dt_from_datetime_naive_becomes_utc(self):
        naive = datetime(2026, 1, 1, 0, 0, 0)
        dt = _parse_dt(naive)
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# ReportsService — CRUD
# ---------------------------------------------------------------------------

class TestReportsServiceCRUD:
    def test_list_reports_returns_rows(self):
        row = _report()
        db, svc = _svc([row])
        db.set_table_data("reports", [row])
        result = svc.list_reports()
        assert result == [row]

    def test_list_reports_empty(self):
        db, svc = _svc([])
        db.set_table_data("reports", [])
        result = svc.list_reports()
        assert result == []

    def test_get_report_found(self):
        row = _report()
        db, svc = _svc([row])
        db.set_table_data("reports", [row])
        result = svc.get_report(row["id"])
        assert result == row

    def test_get_report_not_found(self):
        db, svc = _svc([])
        db.set_table_data("reports", [])
        result = svc.get_report("nonexistent")
        assert result is None

    def test_create_report_returns_row(self):
        db, svc = _svc([])
        result = svc.create_report({
            "name": "Relatório Teste",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
        })
        # org_id must be injected into the insert payload
        inserted = db.table("reports").inserted_payloads
        assert inserted[0]["org_id"] == str(ORG)
        # Mock insert returns auto-id row (mock-reports-1)
        assert result["id"] is not None
        assert result["name"] == "Relatório Teste"

    def test_create_report_raises_if_no_data(self):
        """Simulate insert returning empty data via sequential response queue."""
        from noctusai_lib.testing import MockSupabaseResponse
        db, svc = _svc([])
        # Queue an empty response so insert().execute().data == []
        db.set_sequential_responses("reports", [MockSupabaseResponse(data=[])])
        with pytest.raises(RuntimeError):
            svc.create_report({"name": "X", "period_start": "2026-05-01", "period_end": "2026-05-31"})

    def test_update_report_prevents_org_id_escalation(self):
        row = _report()
        db, svc = _svc([row])
        db.set_table_data("reports", [row])
        svc.update_report(row["id"], {"org_id": "evil-org", "name": "OK"})
        # org_id must NOT appear in the update payload
        updated = db.table("reports").updated_payloads
        assert "org_id" not in updated[0]

    def test_update_report_strips_public_token(self):
        row = _report()
        db, svc = _svc([row])
        db.set_table_data("reports", [row])
        svc.update_report(row["id"], {"public_token": str(uuid.uuid4()), "name": "OK"})
        updated = db.table("reports").updated_payloads
        assert "public_token" not in updated[0]

    def test_update_report_not_found_returns_none(self):
        db, svc = _svc([])
        db.set_table_data("reports", [])
        result = svc.update_report("nonexistent", {"name": "X"})
        assert result is None

    def test_delete_report_found(self):
        row = _report()
        db, svc = _svc([row])
        db.set_table_data("reports", [row])
        ok = svc.delete_report(row["id"])
        assert ok is True

    def test_delete_report_not_found(self):
        db, svc = _svc([])
        db.set_table_data("reports", [])
        ok = svc.delete_report("nonexistent")
        assert ok is False

    def test_list_snapshots_returns_rows(self):
        row = _report()
        snap = _snapshot(row["id"])
        db, svc = _svc([snap])
        db.set_table_data("report_snapshots", [snap])
        result = svc.list_snapshots(row["id"])
        assert result == [snap]


# ---------------------------------------------------------------------------
# ReportsService — generate_snapshot (aggregation)
# ---------------------------------------------------------------------------

class TestGenerateSnapshot:
    def test_generate_raises_lookup_if_report_not_found(self):
        db, svc = _svc([])
        db.set_table_data("reports", [])
        with pytest.raises(LookupError):
            svc.generate_snapshot("nonexistent")

    def test_generate_produces_correct_payload_shape(self):
        """The generated payload must carry period + leads + revenues + expenses."""
        report = _report(id_="report-1", period_start="2026-05-01", period_end="2026-05-31")
        snap = _snapshot("report-1")

        db, svc = _svc([snap])
        # Seed all tables the service queries
        db.set_table_data("reports", [report])
        in_period = "2026-05-15T00:00:00+00:00"
        db.set_table_data("leads", [
            {"temperature": "hot", "created_at": in_period, "org_id": str(ORG)},
            {"temperature": "warm", "created_at": in_period, "org_id": str(ORG)},
            {"temperature": "cold", "created_at": in_period, "org_id": str(ORG)},
        ])
        db.set_table_data("revenues", [
            {"amount": 5000, "status": "paid", "paid_at": "2026-05-10T00:00:00+00:00", "org_id": str(ORG)},
            {"amount": 3000, "status": "paid", "paid_at": "2026-05-20T00:00:00+00:00", "org_id": str(ORG)},
        ])
        db.set_table_data("expenses", [{"amount": 2000, "due_date": "2026-05-15", "org_id": str(ORG)}])

        result = svc.generate_snapshot("report-1")

        # The mock returns snap (seeded via _svc([snap])) so insert returns that row
        assert result["report_id"] == "report-1"
        # Verify the service did write a snapshot with the right shape
        inserted = db.table("report_snapshots").inserted_payloads
        assert len(inserted) == 1
        payload = inserted[0]["payload"]
        assert "period" in payload
        assert "leads" in payload
        assert "revenues" in payload
        assert "expenses" in payload
        assert "generated_at" in payload

    def test_generate_aggregates_leads_by_temperature(self):
        report = _report(id_="report-2", period_start="2026-05-01", period_end="2026-05-31")
        snap = _snapshot("report-2")

        db, svc = _svc([snap])
        db.set_table_data("reports", [report])
        # Include created_at so gte/lte predicates in _aggregate_leads match the rows
        in_period = "2026-05-15T00:00:00+00:00"
        db.set_table_data("leads", [
            {"temperature": "hot", "created_at": in_period, "org_id": str(ORG)},
            {"temperature": "hot", "created_at": in_period, "org_id": str(ORG)},
            {"temperature": "warm", "created_at": in_period, "org_id": str(ORG)},
            {"temperature": None, "created_at": in_period, "org_id": str(ORG)},
        ])
        db.set_table_data("revenues", [])
        db.set_table_data("expenses", [])

        svc.generate_snapshot("report-2")

        inserted = db.table("report_snapshots").inserted_payloads
        leads = inserted[0]["payload"]["leads"]
        assert leads["total"] == 4
        assert leads["hot"] == 2
        assert leads["warm"] == 1
        assert leads["cold"] == 0

    def test_generate_aggregates_revenues(self):
        report = _report(id_="report-3", period_start="2026-05-01", period_end="2026-05-31")
        snap = _snapshot("report-3")

        db, svc = _svc([snap])
        db.set_table_data("reports", [report])
        db.set_table_data("leads", [])
        # revenues rows: status=paid + paid_at in period (columns from migration 006)
        db.set_table_data("revenues", [
            {"amount": "5000.00", "status": "paid", "paid_at": "2026-05-10T00:00:00+00:00", "org_id": str(ORG)},
            {"amount": "3000.00", "status": "paid", "paid_at": "2026-05-20T00:00:00+00:00", "org_id": str(ORG)},
        ])
        db.set_table_data("expenses", [])

        svc.generate_snapshot("report-3")

        inserted = db.table("report_snapshots").inserted_payloads
        revenues = inserted[0]["payload"]["revenues"]
        assert revenues["total"] == 8000.0
        assert revenues["count"] == 2

    def test_generate_snapshot_raises_if_insert_returns_no_data(self):
        """Simulate snapshot insert returning empty data → RuntimeError."""
        from noctusai_lib.testing import MockSupabaseResponse
        report = _report(id_="report-4")
        db, svc = _svc([])
        db.set_table_data("reports", [report])
        db.set_table_data("leads", [])
        db.set_table_data("revenues", [])
        db.set_table_data("expenses", [])
        # Queue empty response so the insert returns no data
        db.set_sequential_responses("report_snapshots", [MockSupabaseResponse(data=[])])
        with pytest.raises(RuntimeError):
            svc.generate_snapshot("report-4")


# ---------------------------------------------------------------------------
# ReportsPublicService — token-gated read
# ---------------------------------------------------------------------------

class TestReportsPublicService:
    def test_unknown_token_returns_none(self):
        db, pub = _pub_svc([])
        db.set_table_data("reports", [])
        result = pub.get_published_report_by_token("nonexistent-token")
        assert result is None

    def test_draft_report_returns_none(self):
        row = _report(status="draft")
        db, pub = _pub_svc([row])
        db.set_table_data("reports", [row])
        result = pub.get_published_report_by_token(row["public_token"])
        assert result is None

    def test_expired_published_report_returns_none(self):
        row = _report(status="published", expires_at="2026-01-01T00:00:00+00:00")
        db, pub = _pub_svc([row])
        db.set_table_data("reports", [row])
        result = pub.get_published_report_by_token(row["public_token"])
        assert result is None

    def test_published_not_expired_returns_dict(self):
        row = _report(status="published")
        snap = _snapshot(row["id"])
        db, pub = _pub_svc([snap])
        db.set_table_data("reports", [row])
        db.set_table_data("report_snapshots", [snap])
        result = pub.get_published_report_by_token(row["public_token"])
        assert result is not None
        assert result["report"]["status"] == "published"
        assert result["snapshot"]["report_id"] == row["id"]

    def test_published_with_future_expiry_returns_dict(self):
        row = _report(status="published", expires_at="2099-01-01T00:00:00+00:00")
        snap = _snapshot(row["id"])
        db, pub = _pub_svc([snap])
        db.set_table_data("reports", [row])
        db.set_table_data("report_snapshots", [snap])
        result = pub.get_published_report_by_token(row["public_token"])
        assert result is not None

    def test_published_without_snapshot_returns_none_snapshot(self):
        row = _report(status="published")
        db, pub = _pub_svc([])
        db.set_table_data("reports", [row])
        db.set_table_data("report_snapshots", [])
        result = pub.get_published_report_by_token(row["public_token"])
        assert result is not None
        assert result["snapshot"] is None
