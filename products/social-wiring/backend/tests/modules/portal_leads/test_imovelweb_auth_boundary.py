"""Auth boundary for `/api/portals/imovelweb/*`.

Two jobs, and the second catches the real mistakes:

1. every authenticated route rejects an anonymous call with a strict
   ``== 401`` — never ``in (401, 404)``, which passes just as happily when
   the route does not exist or when validation runs before auth;
2. the public route is public **by enumeration**. `POST /leads` has to be
   unauthenticated (the vendor has no JWT to send), so it is listed
   explicitly. A future public route is then a deliberate edit to this list
   rather than something that slips in unnoticed.

This surface is larger than the OLX one, and the extra routes are exactly
the dangerous kind: `POST /callback/register` rewrites an INTEGRATOR-WIDE
configuration that redirects every agency's leads at once.
"""
from __future__ import annotations

import pytest

from tests.modules.portal_leads.conftest import ORG_A  # noqa: F401 — fixture chain

#: Routes that MUST be unauthenticated, and why.
PUBLIC_ROUTES = {
    ("POST", "/api/portals/imovelweb/leads"):
        "ImovelWeb posts here with the Basic header we registered and no JWT; "
        "that header IS the auth, and there is no signature scheme behind it.",
}

#: Routes that MUST require a session.
AUTHENTICATED_ROUTES = [
    ("GET", "/api/portals/imovelweb/events"),
    ("POST", "/api/portals/imovelweb/backfill"),
    ("GET", "/api/portals/imovelweb/callback"),
    ("POST", "/api/portals/imovelweb/callback/register"),
    ("POST", "/api/portals/imovelweb/reconcile"),
]


@pytest.mark.parametrize("method,path", AUTHENTICATED_ROUTES)
def test_authenticated_routes_reject_anonymous_calls(http_client, method, path):
    resp = http_client.request(method, path)

    assert resp.status_code == 401, (
        f"{method} {path} answered {resp.status_code}, not 401. A non-401 here "
        "is a false green: it means the route is absent, or validation ran "
        "before the auth check."
    )


# Deliberately NOT tested here: "a garbage bearer token is rejected." The
# fixture stubs `mock_db.auth.get_user` to return a valid user for any
# token, so such a test would assert the fixture rather than the route.
# Token VALIDATION belongs to the seed's auth dependency and is tested
# there; what this file owns is that these routes sit behind that
# dependency at all, which the header-absent case above proves.


def test_the_public_route_is_public_by_enumeration():
    """Asserts the intent, so adding a second public route means editing
    this list on purpose."""
    from app.main import app

    declared = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/portals/imovelweb"):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method in ("HEAD", "OPTIONS"):
                continue
            declared.add((method, path))

    expected = set(PUBLIC_ROUTES) | set(AUTHENTICATED_ROUTES)
    assert declared == expected, (
        "the ImovelWeb route surface changed — classify every new route as "
        "public (with a reason) or authenticated before updating this test"
    )


def test_the_public_route_still_refuses_an_unsigned_call(http_client):
    """Public ≠ open. Without the Basic credential it is a strict 401."""
    resp = http_client.post(
        "/api/portals/imovelweb/leads", json={"eventId": "x"}
    )

    assert resp.status_code == 401


def test_the_registration_route_is_confirm_gated(http_client):
    """Authenticated is not enough for the integrator-wide write.

    Anonymous is 401 (above). Authenticated-but-unconfirmed must be 412 —
    and the gate has to be evaluated BEFORE the vendor client is built, so
    that "no confirm" means nothing happened rather than something failed
    afterwards.
    """
    from app.main import app
    from app.modules.portal_leads.routers import imovelweb_webhook

    class _ExplodingAdapter:
        def __getattr__(self, name):
            def _boom(*a, **k):
                raise AssertionError(f"confirm gate did not stop the write; {name}")

            return _boom

    app.dependency_overrides[imovelweb_webhook.get_imovelweb_adapter] = (
        lambda: _ExplodingAdapter()
    )
    try:
        resp = http_client.post(
            "/api/portals/imovelweb/callback/register",
            json={},
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        app.dependency_overrides.pop(imovelweb_webhook.get_imovelweb_adapter, None)

    assert resp.status_code == 412
    assert "NO side-effect" in resp.json()["error"]
