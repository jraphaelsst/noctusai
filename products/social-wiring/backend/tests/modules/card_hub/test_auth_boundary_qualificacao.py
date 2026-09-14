"""`GET /api/clientes/{cliente_id}/qualificacao-completude` (migration 110)
— strict `== 401`, never `in (401, 404)`. A permissive tuple is a
false-green: it passes when the route doesn't exist at all, and it passes
when validation runs before auth. Only the exact code proves the guard
fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`

This route is ALSO covered by `test_auth_boundary.py::
test_every_card_hub_route_requires_auth`'s auto-enumeration (it walks every
mounted `card_hub` router's routes, so a brand-new route inherits that
sweep for free — nothing had to be added there for this one to be caught).
This file pins the concrete path explicitly rather than relying only on
enumeration, per this slice's own auth-boundary requirement, and would fail
loudly if a future refactor renamed the path in one place but not the
other.
"""
from __future__ import annotations

from uuid import uuid4

_CLIENTE_ID = str(uuid4())


def test_qualificacao_completude_requires_auth(anon_client):
    resp = anon_client.get(f"/api/clientes/{_CLIENTE_ID}/qualificacao-completude")
    assert resp.status_code == 401, (
        f"GET /api/clientes/{{cliente_id}}/qualificacao-completude -> "
        f"{resp.status_code} (expected a strict 401 — the route must never "
        "be reachable without auth, regardless of whether the cliente_id "
        "exists)"
    )


def test_qualificacao_completude_is_still_401_for_a_nonexistent_cliente(anon_client):
    """The 401 must fire BEFORE `ensure_cliente` gets a chance to 404 —
    otherwise an unauthenticated caller could distinguish a real cliente_id
    from a fake one by the status code alone."""
    resp = anon_client.get(
        f"/api/clientes/{uuid4()}/qualificacao-completude"
    )
    assert resp.status_code == 401
