"""Tests for license expiry enforcement in dependencies.py.

Verifies that check_org_license() and get_licensed_product_ids()
correctly filter out expired licenses (fim <= now()).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from app.dependencies import check_org_license, get_licensed_product_ids


ORG_ID = "org-1"
PRODUCT_ID = "prod-1"


def _make_db(licenses_data):
    """Create a mock DB client that returns given license data."""
    mock_response = MagicMock()
    mock_response.data = licenses_data

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.execute.return_value = mock_response

    db = MagicMock()
    db.table.return_value = mock_query
    return db


class TestCheckOrgLicense:
    def test_no_licenses_returns_false(self):
        db = _make_db([])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is False

    def test_permanent_license_returns_true(self):
        db = _make_db([{"id": "lic-1", "fim": None}])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is True

    def test_future_expiry_returns_true(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        db = _make_db([{"id": "lic-1", "fim": future}])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is True

    def test_past_expiry_returns_false(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db = _make_db([{"id": "lic-1", "fim": past}])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is False

    def test_expired_yesterday_returns_false(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        db = _make_db([{"id": "lic-1", "fim": yesterday}])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is False

    def test_one_expired_one_permanent_returns_true(self):
        past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        db = _make_db([
            {"id": "lic-1", "fim": past},
            {"id": "lic-2", "fim": None},
        ])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is True

    def test_all_expired_returns_false(self):
        past1 = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        past2 = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db = _make_db([
            {"id": "lic-1", "fim": past1},
            {"id": "lic-2", "fim": past2},
        ])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is False

    def test_supabase_timestamp_format(self):
        """Supabase returns timestamps like '2026-04-09 00:00:00+00'."""
        past = "2020-01-01 00:00:00+00"
        db = _make_db([{"id": "lic-1", "fim": past}])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is False

    def test_supabase_future_timestamp(self):
        future = "2099-12-31 23:59:59+00"
        db = _make_db([{"id": "lic-1", "fim": future}])
        assert check_org_license(db, ORG_ID, PRODUCT_ID) is True


class TestGetLicensedProductIds:
    def test_empty_returns_empty(self):
        db = _make_db([])
        assert get_licensed_product_ids(db, ORG_ID) == []

    def test_permanent_license_included(self):
        db = _make_db([{"product_id": "p1", "fim": None}])
        assert get_licensed_product_ids(db, ORG_ID) == ["p1"]

    def test_expired_license_excluded(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db = _make_db([{"product_id": "p1", "fim": past}])
        assert get_licensed_product_ids(db, ORG_ID) == []

    def test_mix_of_valid_and_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        db = _make_db([
            {"product_id": "p1", "fim": past},
            {"product_id": "p2", "fim": None},
            {"product_id": "p3", "fim": future},
        ])
        result = get_licensed_product_ids(db, ORG_ID)
        assert "p1" not in result
        assert "p2" in result
        assert "p3" in result

    def test_multiple_permanent(self):
        db = _make_db([
            {"product_id": "p1", "fim": None},
            {"product_id": "p2", "fim": None},
        ])
        assert sorted(get_licensed_product_ids(db, ORG_ID)) == ["p1", "p2"]
