"""Tests for SSO cache invalidation helpers.

compliance-audit-reconciliation Phase 6 (finding 9 — stale access window).
Verifies TTL + per-user invalidation + per-org invalidation.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.routers import sso as sso_module


def _reset_cache():
    sso_module._session_cache.clear()


class TestInvalidateSSOCacheForUser:
    def test_invalidate_missing_returns_false(self):
        _reset_cache()
        assert sso_module.invalidate_sso_cache_for_user("none@example.com") is False

    def test_invalidate_existing_returns_true(self):
        _reset_cache()
        sso_module._session_cache.set("a@example.com", {"access_token": "x"})
        assert sso_module.invalidate_sso_cache_for_user("a@example.com") is True
        assert sso_module._session_cache.get("a@example.com") is None

    def test_empty_email_returns_false(self):
        _reset_cache()
        assert sso_module.invalidate_sso_cache_for_user("") is False


class TestInvalidateSSOCacheForOrg:
    def test_empty_org_returns_zero(self):
        _reset_cache()
        db = MagicMock()
        assert sso_module.invalidate_sso_cache_for_org(db, "") == 0

    def test_invalidate_all_users_in_org(self):
        _reset_cache()
        sso_module._session_cache.set("a@example.com", {"t": 1})
        sso_module._session_cache.set("b@example.com", {"t": 2})
        sso_module._session_cache.set("c@example.com", {"t": 3})  # different org

        db = MagicMock()
        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.execute.return_value = MagicMock(data=[
            {"email": "a@example.com"},
            {"email": "b@example.com"},
        ])
        db.table.return_value = table

        invalidated = sso_module.invalidate_sso_cache_for_org(db, "org-1")
        assert invalidated == 2
        assert sso_module._session_cache.get("a@example.com") is None
        assert sso_module._session_cache.get("b@example.com") is None
        # Other-org user kept
        assert sso_module._session_cache.get("c@example.com") is not None

    def test_invalidate_silently_handles_db_error(self):
        _reset_cache()
        sso_module._session_cache.set("a@example.com", {"t": 1})

        db = MagicMock()
        db.table.side_effect = RuntimeError("db unavailable")

        invalidated = sso_module.invalidate_sso_cache_for_org(db, "org-1")
        assert invalidated == 0
        # Cache entry should still exist since nothing was invalidated
        assert sso_module._session_cache.get("a@example.com") is not None


class TestCacheTTL:
    def test_ttl_is_five_minutes(self):
        """Phase 6 decision: TTL reduced from 3500s (58min) to 300s (5min)."""
        assert sso_module._CACHE_TTL == 300
