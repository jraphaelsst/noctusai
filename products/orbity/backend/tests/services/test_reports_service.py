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

from noctusai_lib.api.token_link import TokenLinkGone, TokenLinkNotFound, resolve_token_link

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
            {"id": str(uuid.uuid4()), "temperature": "hot", "created_at": in_period, "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "temperature": "warm", "created_at": in_period, "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "temperature": "cold", "created_at": in_period, "org_id": str(ORG)},
        ])
        db.set_table_data("revenues", [
            {"id": str(uuid.uuid4()), "amount": 5000, "status": "paid", "paid_at": "2026-05-10T00:00:00+00:00", "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "amount": 3000, "status": "paid", "paid_at": "2026-05-20T00:00:00+00:00", "org_id": str(ORG)},
        ])
        db.set_table_data("expenses", [{"id": str(uuid.uuid4()), "amount": 2000, "due_date": "2026-05-15", "org_id": str(ORG)}])

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
            {"id": str(uuid.uuid4()), "temperature": "hot", "created_at": in_period, "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "temperature": "hot", "created_at": in_period, "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "temperature": "warm", "created_at": in_period, "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "temperature": None, "created_at": in_period, "org_id": str(ORG)},
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
            {"id": str(uuid.uuid4()), "amount": "5000.00", "status": "paid", "paid_at": "2026-05-10T00:00:00+00:00", "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "amount": "3000.00", "status": "paid", "paid_at": "2026-05-20T00:00:00+00:00", "org_id": str(ORG)},
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
    """The public read: token -> report (resolve_token_link) -> latest snapshot INSIDE the report's org."""

    @staticmethod
    def _open(pub, token):
        return resolve_token_link(token, pub.fetch_published_report)

    def test_unknown_token_is_not_found(self):
        db, pub = _pub_svc([])
        db.set_table_data("reports", [])
        with pytest.raises(TokenLinkNotFound):
            self._open(pub, str(uuid.uuid4()))

    def test_draft_report_is_not_found(self):
        row = _report(status="draft")
        db, pub = _pub_svc([row])
        db.set_table_data("reports", [row])
        with pytest.raises(TokenLinkNotFound):
            self._open(pub, row["public_token"])

    def test_expired_published_report_is_gone(self):
        row = _report(status="published", expires_at="2026-01-01T00:00:00+00:00")
        db, pub = _pub_svc([row])
        db.set_table_data("reports", [row])
        with pytest.raises(TokenLinkGone):
            self._open(pub, row["public_token"])

    def test_a_report_link_without_an_expiry_fails_closed(self):
        for bad in (None, "garbage"):
            row = _report(status="published", expires_at=bad)
            db, pub = _pub_svc([row])
            db.set_table_data("reports", [row])
            with pytest.raises(TokenLinkGone):
                self._open(pub, row["public_token"])

    def test_published_with_future_expiry_opens_with_its_snapshot(self):
        row = _report(status="published", expires_at="2099-01-01T00:00:00+00:00")
        snap = _snapshot(row["id"])
        db, pub = _pub_svc([snap])
        db.set_table_data("reports", [row])
        db.set_table_data("report_snapshots", [snap])
        report = self._open(pub, row["public_token"])
        assert pub.latest_snapshot(report)["report_id"] == row["id"]

    def test_published_without_snapshot_has_no_snapshot(self):
        row = _report(status="published", expires_at="2099-01-01T00:00:00+00:00")
        db, pub = _pub_svc([])
        db.set_table_data("reports", [row])
        db.set_table_data("report_snapshots", [])
        assert pub.latest_snapshot(self._open(pub, row["public_token"])) is None

    def test_a_snapshot_of_org_a_pointing_at_the_report_of_org_b_never_shows(self):
        """LEAK (security review round 3): the snapshot is read inside the report's own org."""
        row = _report(status="published", expires_at="2099-01-01T00:00:00+00:00")  # org A
        stray = {**_snapshot(row["id"]), "org_id": "00000000-0000-0000-0000-0000000000bb"}  # org B row, same report_id
        db, pub = _pub_svc([stray])
        db.set_table_data("reports", [row])
        db.set_table_data("report_snapshots", [stray])
        assert pub.latest_snapshot(self._open(pub, row["public_token"])) is None


class _FinanceDeniedDb:
    """The user's JWT client as prod serves it: `revenues` / `expenses` are security-invoker views over the service-only
    finance tables, so reading them under the user's role is `permission denied`. Everything else is the shared mock."""

    def __init__(self, inner):
        self._inner = inner

    def table(self, name):
        if name in ("revenues", "expenses"):
            raise PermissionError(f"permission denied for view {name}")
        return self._inner.table(name)


class TestGenerateReadsFinanceThroughTheAdminClient:
    def test_generate_with_revenue_no_longer_fails(self):
        report = _report(id_="report-9", period_start="2026-05-01", period_end="2026-05-31")
        user_db = MockSupabaseClient(data=[_snapshot("report-9")], schema="orbity")
        user_db.set_table_data("reports", [report])
        user_db.set_table_data("leads", [])
        admin_db = MockSupabaseClient(schema="orbity")
        admin_db.set_table_data("revenues", [
            {"id": str(uuid.uuid4()), "amount": 5000, "status": "paid", "paid_at": "2026-05-10T00:00:00+00:00", "org_id": str(ORG)},
            {"id": str(uuid.uuid4()), "amount": 700, "status": "paid", "paid_at": "2026-05-12T00:00:00+00:00", "org_id": "00000000-0000-0000-0000-0000000000bb"},
        ])
        admin_db.set_table_data("expenses", [{"id": str(uuid.uuid4()), "amount": 2000, "due_date": "2026-05-15", "org_id": str(ORG)}])
        svc = ReportsService(_FinanceDeniedDb(user_db), org_id=ORG, admin_db=admin_db)
        svc.generate_snapshot("report-9")  # was a 502 (PermissionError) before
        payload = user_db.table("report_snapshots").inserted_payloads[-1]["payload"]
        assert payload["revenues"] == {"total": 5000.0, "count": 1}  # the other org's 700 is excluded by .eq(org_id)
        assert payload["expenses"]["total"] == 2000.0


class TestPublishedLinkExpiry:
    def test_publishing_without_an_expiry_gets_a_default_one(self):
        db, svc = _svc([_report(status="draft", expires_at=None)])
        svc.update_report(db.table("reports").select("*").execute().data[0]["id"], {"status": "published"})
        payload = db.table("reports").updated_payloads[-1]
        assert payload["expires_at"]  # now + REPORT_LINK_TTL_DAYS

    def test_creating_a_published_report_gets_a_default_expiry(self):
        db, svc = _svc([])
        svc.create_report({"name": "R", "period_start": "2026-01-01", "period_end": "2026-01-31", "status": "published"})
        assert db.table("reports").inserted_payloads[-1]["expires_at"]

    def test_an_expiry_ten_years_out_is_clamped_to_90_days_on_create(self):
        from datetime import timedelta

        db, svc = _svc([])
        svc.create_report({"name": "R", "period_start": "2026-01-01", "period_end": "2026-01-31", "status": "published",
                           "expires_at": (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()})
        got = datetime.fromisoformat(db.table("reports").inserted_payloads[-1]["expires_at"])
        assert abs((got - (datetime.now(timezone.utc) + timedelta(days=90))).total_seconds()) < 60

    def test_an_expiry_ten_years_out_is_clamped_to_90_days_on_update(self):
        from datetime import timedelta

        row = _report(status="published", expires_at="2026-12-01T00:00:00+00:00")
        db, svc = _svc([row])
        svc.update_report(row["id"], {"expires_at": (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()})
        got = datetime.fromisoformat(db.table("reports").updated_payloads[-1]["expires_at"])
        assert abs((got - (datetime.now(timezone.utc) + timedelta(days=90))).total_seconds()) < 60

    def test_an_expiry_inside_the_ceiling_is_kept_on_update(self):
        row = _report(status="published", expires_at="2026-12-01T00:00:00+00:00")
        db, svc = _svc([row])
        soon = (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=10)).isoformat()
        svc.update_report(row["id"], {"expires_at": soon})
        assert db.table("reports").updated_payloads[-1]["expires_at"] == soon

    def test_an_explicit_expiry_is_kept(self):
        db, svc = _svc([])
        soon = (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=20)).isoformat()
        svc.create_report({"name": "R", "period_start": "2026-01-01", "period_end": "2026-01-31", "status": "published",
                           "expires_at": soon})
        assert db.table("reports").inserted_payloads[-1]["expires_at"] == soon


# ---------------------------------------------------------------------------
# Client-scoped reports must not leak org-wide data; failures must not be zeros
# ---------------------------------------------------------------------------

CLIENT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CLIENT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _row(**kw) -> dict:
    return {"id": str(uuid.uuid4()), "org_id": str(ORG), **kw}


class TestClientScopedSnapshot:
    def _seed(self, report_client):
        report = _report(id_="rep-c", period_start="2026-05-01", period_end="2026-05-31")
        report["client_id"] = report_client
        db, svc = _svc([_snapshot("rep-c")])
        d = "2026-05-15T00:00:00+00:00"
        db.set_table_data("reports", [report])
        db.set_table_data("leads", [
            _row(temperature="hot", created_at=d, client_id=CLIENT_A),
            _row(temperature="hot", created_at=d, client_id=CLIENT_B),
            _row(temperature="cold", created_at=d, client_id=CLIENT_B),
        ])
        db.set_table_data("revenues", [
            _row(amount=100, status="paid", paid_at=d, client_id=CLIENT_A),
            _row(amount=900, status="paid", paid_at=d, client_id=CLIENT_B),
        ])
        db.set_table_data("expenses", [_row(amount=555, due_date="2026-05-10")])
        db.set_table_data("ad_accounts", [_row(client_id=CLIENT_A), _row(client_id=CLIENT_B)])
        return db, svc

    def test_client_report_only_counts_that_clients_leads_and_revenue(self):
        db, svc = self._seed(CLIENT_A)
        svc.generate_snapshot("rep-c")
        payload = db.table("report_snapshots").inserted_payloads[0]["payload"]
        assert payload["leads"]["total"] == 1
        assert payload["revenues"]["total"] == 100.0
        assert payload["scope"] == {"client_id": CLIENT_A}

    def test_client_report_does_not_leak_org_expenses(self):
        db, svc = self._seed(CLIENT_A)
        svc.generate_snapshot("rep-c")
        expenses = db.table("report_snapshots").inserted_payloads[0]["payload"]["expenses"]
        assert expenses["available"] is False
        assert "total" not in expenses

    def test_org_wide_report_keeps_org_totals(self):
        db, svc = self._seed(None)
        svc.generate_snapshot("rep-c")
        payload = db.table("report_snapshots").inserted_payloads[0]["payload"]
        assert payload["leads"]["total"] == 3
        assert payload["revenues"]["total"] == 1000.0
        assert payload["expenses"]["total"] == 555.0
        assert payload["scope"] == {"org_wide": True}

    def test_meta_ads_scoped_to_client_directly_and_via_ad_account(self):
        db, svc = self._seed(CLIENT_A)
        acct_a, acct_b = "acct-a", "acct-b"
        db.set_table_data("ad_accounts", [
            _row(id=acct_a, client_id=CLIENT_A), _row(id=acct_b, client_id=CLIENT_B),
        ])
        db.set_table_data("campaigns", [
            _row(id="c-direct", client_id=CLIENT_A, ad_account_id="x", status="active"),
            _row(id="c-via", client_id=None, ad_account_id=acct_a, status="paused"),
            _row(id="c-other", client_id=CLIENT_B, ad_account_id=acct_b, status="active"),
        ])
        d = "2026-05-12"
        db.set_table_data("campaign_metrics", [
            _row(campaign_id="c-direct", date=d, spend=40, leads=2),
            _row(campaign_id="c-via", date=d, spend=60, leads=3),
            _row(campaign_id="c-other", date=d, spend=1000, leads=50),
        ])
        out = svc._aggregate_meta_ads("2026-05-01", "2026-05-31", CLIENT_A)
        assert out["spend"] == 100.0
        assert out["leads"] == 5
        assert out["cpl"] == 20.0
        assert out["active_campaigns"] == 1

    def test_revenue_query_failure_raises_not_zero(self):
        db, _ = self._seed(CLIENT_A)
        svc = ReportsService(_Boom(db, "revenues"), org_id=ORG)
        with pytest.raises(RuntimeError, match="revenues unavailable"):
            svc.generate_snapshot("rep-c")


class _Boom:
    """Wraps a client; `.table(name)` raises for one table (real failure path)."""

    def __init__(self, inner, bad):
        self._inner, self._bad = inner, bad

    def table(self, name):
        if name == self._bad:
            raise RuntimeError(f"{name} unavailable")
        return self._inner.table(name)
