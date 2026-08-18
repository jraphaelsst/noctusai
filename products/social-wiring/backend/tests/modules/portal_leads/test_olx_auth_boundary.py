"""Auth boundary for `/api/portals/olx/*`.

Two jobs, and the second is the one that catches real mistakes:

1. every authenticated route rejects an anonymous call with a strict
   ``== 401`` — never ``in (401, 404)``, which passes just as happily
   when the route does not exist or when validation runs before auth;
2. the public route is public **by enumeration**. `POST /leads` has to be
   unauthenticated (OLX has no JWT to send), so it is listed explicitly
   here. A future public route is then a deliberate edit to this list,
   not something that slips in unnoticed.
"""
from __future__ import annotations

import pytest

from tests.modules.portal_leads.conftest import ORG_A  # noqa: F401 — fixture chain

#: Routes that MUST be unauthenticated, and why.
PUBLIC_ROUTES = {
    ("POST", "/api/portals/olx/leads"):
        "Grupo OLX posts here with HTTP Basic and no JWT; the secret IS the auth.",
    ("POST", "/api/portals/olx/leads/{receiver_token}"):
        "Same delivery, multi-tenant form. The path token names the "
        "advertiser; it is NOT the authentication — the same Basic secret "
        "gates it, and an unresolvable token still gets a 200 with the "
        "event parked as unresolved. Public for the same reason as its "
        "tokenless sibling: the vendor has no JWT to send.",
}

#: Routes that MUST require a session.
AUTHENTICATED_ROUTES = [
    ("GET", "/api/portals/olx/events"),
    ("POST", "/api/portals/olx/backfill"),
]


@pytest.mark.parametrize("method,path", AUTHENTICATED_ROUTES)
def test_authenticated_routes_reject_anonymous_calls(http_client, method, path):
    resp = http_client.request(method, path)

    assert resp.status_code == 401, (
        f"{method} {path} answered {resp.status_code}, not 401. A non-401 here "
        "is a false green: it means the route is absent, or validation ran "
        "before the auth check."
    )


# Deliberately NOT tested here: "a garbage bearer token is rejected."
# The fixture stubs `mock_db.auth.get_user` to return a valid user for any
# token, so such a test would assert the fixture, not the route — it
# passed 200 when first written, for exactly that reason. Token VALIDATION
# belongs to the seed's auth dependency and is tested there; what this
# file owns is that these routes sit behind that dependency at all, which
# the header-absent case above proves. (Same convention as
# `tests/modules/leads/test_auth_boundary.py`.)


def test_the_public_route_is_public_by_enumeration():
    """Asserts the intent, so that adding a second public route requires
    editing this list on purpose."""
    from app.main import app

    declared = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/portals/olx"):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method in ("HEAD", "OPTIONS"):
                continue
            declared.add((method, path))

    expected = set(PUBLIC_ROUTES) | set(AUTHENTICATED_ROUTES)
    assert declared == expected, (
        "the OLX route surface changed — classify every new route as public "
        "(with a reason) or authenticated before this test is updated"
    )


def test_the_public_route_still_refuses_an_unsigned_call(http_client):
    """Public ≠ open. Without the Basic secret it is a strict 401."""
    resp = http_client.post("/api/portals/olx/leads", json={"originLeadId": "x"})

    assert resp.status_code == 401
