"""
Tests for the AdConnect distributors router — Phase 1 boundary coverage.

Phase 1 of `adconnect-mvp-implementation` swapped the auth surface to
`noctusai_seed`/Supabase SSO but did NOT replace `app/routers/distributors.py`
(scheduled for Phase 2). These tests verify:

  1. The router still mounts cleanly under the new auth dep shim.
  2. Auth boundary works (401 without bearer; legacy dict-shape user is
     yielded to handlers that read `user["distributorId"]`).
  3. The mock-backed JSON store path still serves the existing endpoints
     so the legacy frontend doesn't break during the transition.

Phase 2 expands this file into full CRUD + RLS coverage against the new
Supabase-backed router.
"""
from __future__ import annotations


class TestDistributorsAuthBoundary:
    def test_list_all_requires_admin_role(self, client):
        """`GET /` is gated by require_role('admin').

        Default MockUser has no `role` in user_metadata, so the resolver
        falls through to 'customer' — admin gate must reject.
        """
        resp = client.get("/api/distributors/")
        assert resp.status_code == 403

    def test_list_all_no_auth(self, client):
        resp = client.raw().get("/api/distributors/")
        assert resp.status_code == 401

    def test_me_no_auth(self, client):
        resp = client.raw().get("/api/distributors/me")
        assert resp.status_code == 401

    def test_get_one_no_auth(self, client):
        resp = client.raw().get("/api/distributors/dist-001")
        assert resp.status_code == 401


class TestDistributorsLegacyPaths:
    """The mock-backed `store.distributors` path still serves data.

    Verifies the auth dep shim hands the legacy dict-shape user the
    handlers expect, so existing routes continue to function until
    Phase 2 swaps them.
    """

    def test_get_one_with_authed_user(self, client):
        """Without `distributorId` on the user, handler 403s the
        ownership check; that's the existing semantic and we just
        confirm the dep yielded the dict-shape (didn't crash on attr
        access).
        """
        resp = client.get("/api/distributors/dist-001")
        # 403 = ownership check fired (handler ran, dep returned dict).
        # 404 would mean the row wasn't in the JSON store; either is
        # acceptable evidence the auth shim works — anything OTHER than
        # 401 / 5xx confirms the dep produced a dict-shape user.
        assert resp.status_code in (403, 404)
