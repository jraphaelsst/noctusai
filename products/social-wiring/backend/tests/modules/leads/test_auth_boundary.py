"""Auth boundary — every /api/leads/* route asserts strict ``== 401``
(never ``in (401, 404)``/``in (401, 422)``) when the Authorization header
is absent. Bodies are well-formed where a body is required so the ONLY
missing thing is auth — isolates the signal (mirrors
``tests/routers/test_clients_router.py::TestAuth``).
Per ``KB § PATTERNS/compliance/auth-boundary-false-green.md``.
"""
from __future__ import annotations

from uuid import uuid4

import pytest


_LEAD_ID = str(uuid4())
_SOURCE_ID = str(uuid4())
_CORRETOR_ID = str(uuid4())
_ALIAS_ID = str(uuid4())

_LEAD_CREATE_BODY = {"data_entrada": "2026-07-01"}
_LEAD_UPDATE_BODY = {"cliente_nome": "X"}
_SOURCE_CREATE_BODY = {"slug": "x", "label": "X"}
_SOURCE_UPDATE_BODY = {"label": "Y"}
_SOURCE_ALIAS_BODY = {"alias": "X", "source_id": _SOURCE_ID}
_CORRETOR_CREATE_BODY = {"nome": "X"}
_CORRETOR_UPDATE_BODY = {"nome": "Y"}
_CORRETOR_ALIAS_BODY = {"alias": "X", "corretor_id": _CORRETOR_ID}

_ROUTES = [
    ("get", "/api/leads", {}),
    ("post", "/api/leads", {"json": _LEAD_CREATE_BODY}),
    ("get", f"/api/leads/{_LEAD_ID}", {}),
    ("patch", f"/api/leads/{_LEAD_ID}", {"json": _LEAD_UPDATE_BODY}),
    ("delete", f"/api/leads/{_LEAD_ID}", {}),
    ("get", "/api/leads/facets", {}),
    ("get", "/api/leads/analytics/summary", {}),
    ("get", "/api/leads/analytics/timeseries", {}),
    ("get", "/api/leads/analytics/by-dimension", {"params": {"dim": "origem"}}),
    ("get", "/api/leads/analytics/heatmap", {}),
    ("get", "/api/leads/sources", {}),
    ("post", "/api/leads/sources", {"json": _SOURCE_CREATE_BODY}),
    ("patch", f"/api/leads/sources/{_SOURCE_ID}", {"json": _SOURCE_UPDATE_BODY}),
    ("delete", f"/api/leads/sources/{_SOURCE_ID}", {}),
    ("get", "/api/leads/sources/aliases", {}),
    ("post", "/api/leads/sources/aliases", {"json": _SOURCE_ALIAS_BODY}),
    ("delete", f"/api/leads/sources/aliases/{_ALIAS_ID}", {}),
    ("get", "/api/leads/corretores", {}),
    ("post", "/api/leads/corretores", {"json": _CORRETOR_CREATE_BODY}),
    ("patch", f"/api/leads/corretores/{_CORRETOR_ID}", {"json": _CORRETOR_UPDATE_BODY}),
    ("delete", f"/api/leads/corretores/{_CORRETOR_ID}", {}),
    ("get", "/api/leads/corretores/aliases", {}),
    ("post", "/api/leads/corretores/aliases", {"json": _CORRETOR_ALIAS_BODY}),
    ("delete", f"/api/leads/corretores/aliases/{_ALIAS_ID}", {}),
    ("get", "/api/leads/import/batches", {}),
    ("post", "/api/leads/import/preview", {"files": {"file": ("x.xlsx", b"stub", "application/octet-stream")}}),
    ("post", "/api/leads/import/commit", {"files": {"file": ("x.xlsx", b"stub", "application/octet-stream")}}),
    # Meta-ingest backfill: a bulk WRITE over every meta_ads_leads row for the
    # caller's org. It resolves its org from the token, so an unauthenticated
    # call has no org to scope to and must be refused at the boundary — not
    # inside the service, where a missing org could be misread as "all orgs".
    ("post", "/api/leads/meta-ingest/backfill", {}),
]


@pytest.mark.parametrize("method, path, kwargs", _ROUTES, ids=[f"{m}:{p}" for m, p, _ in _ROUTES])
def test_requires_auth_strict_401(http_client, method, path, kwargs):
    resp = getattr(http_client, method)(path, **kwargs)
    assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}: {resp.text}"
