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
        sso_module._session_cache.set("a@example.com", {"access_token": "x"}, org_id="org-1", product_slug="p1")
        assert sso_module.invalidate_sso_cache_for_user("a@example.com") is True
        assert sso_module._session_cache.get("a@example.com", org_id="org-1", product_slug="p1") is None

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
        sso_module._session_cache.set("a@example.com", {"t": 1}, org_id="org-1", product_slug="p1")
        sso_module._session_cache.set("b@example.com", {"t": 2}, org_id="org-1", product_slug="p1")
        sso_module._session_cache.set("c@example.com", {"t": 3}, org_id="org-1", product_slug="p1")  # different org

        # members of the org = its ACTIVE memberships; emails live on the profiles
        from noctusai_lib.testing import MockSupabaseClient
        db = MockSupabaseClient()
        db.set_table_data("org_memberships", [
            {"user_id": "u-a", "org_id": "org-1", "status": "active"},
            {"user_id": "u-b", "org_id": "org-1", "status": "active"},
            {"user_id": "u-c", "org_id": "org-2", "status": "active"},
        ])
        db.set_table_data("noctus_users", [
            {"id": "u-a", "email": "a@example.com", "org_id": "org-9"},  # last-active org elsewhere
            {"id": "u-b", "email": "b@example.com", "org_id": "org-1"},
            {"id": "u-c", "email": "c@example.com", "org_id": "org-2"},
        ])

        invalidated = sso_module.invalidate_sso_cache_for_org(db, "org-1")
        assert invalidated == 2
        assert sso_module._session_cache.get("a@example.com", org_id="org-1", product_slug="p1") is None
        assert sso_module._session_cache.get("b@example.com", org_id="org-1", product_slug="p1") is None
        # Other-org user kept
        assert sso_module._session_cache.get("c@example.com", org_id="org-1", product_slug="p1") is not None

    def test_invalidate_silently_handles_db_error(self):
        _reset_cache()
        sso_module._session_cache.set("a@example.com", {"t": 1}, org_id="org-1", product_slug="p1")

        db = MagicMock()
        db.table.side_effect = RuntimeError("db unavailable")

        invalidated = sso_module.invalidate_sso_cache_for_org(db, "org-1")
        assert invalidated == 0
        # Cache entry should still exist since nothing was invalidated
        assert sso_module._session_cache.get("a@example.com", org_id="org-1", product_slug="p1") is not None


class TestCacheTTL:
    def test_ttl_is_five_minutes(self):
        """Phase 6 decision: TTL reduced from 3500s (58min) to 300s (5min)."""
        assert sso_module._CACHE_TTL == 300


class TestScopedSessionCache:
    """Cache is keyed (email, org_id, product_slug): no cross-origin / cross-org reuse."""

    def test_distinct_scopes_are_distinct_entries_and_one_flush_clears_all(self):
        _reset_cache()
        sso_module._session_cache.set("a@example.com", {"t": 1}, org_id="org-1", product_slug="p1")
        sso_module._session_cache.set("a@example.com", {"t": 2}, org_id="org-2", product_slug="p1")
        sso_module._session_cache.set("a@example.com", {"t": 3}, org_id="org-1", product_slug="p2")
        sso_module._session_cache.set("ab@example.com", {"t": 4}, org_id="org-1", product_slug="p1")

        assert sso_module._session_cache.get("a@example.com", org_id="org-1", product_slug="p1") == {"t": 1}
        assert sso_module._session_cache.get("a@example.com", org_id="org-2", product_slug="p1") == {"t": 2}
        assert sso_module._session_cache.get("a@example.com", org_id="org-1", product_slug="p2") == {"t": 3}

        assert sso_module.invalidate_sso_cache_for_user("a@example.com") is True
        assert sso_module._session_cache.get("a@example.com", org_id="org-1", product_slug="p1") is None
        assert sso_module._session_cache.get("a@example.com", org_id="org-2", product_slug="p1") is None
        assert sso_module._session_cache.get("a@example.com", org_id="org-1", product_slug="p2") is None
        # A different user whose email merely starts with the same text survives.
        assert sso_module._session_cache.get("ab@example.com", org_id="org-1", product_slug="p1") == {"t": 4}
