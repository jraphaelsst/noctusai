"""Execution tests for the `status_paginas` standard router.

`test_build_standard_routers.py` covers registry/surface (path present); this
file exercises the handlers end-to-end through a FastAPI TestClient with a
`ProductDependencies`-shaped fake whose `get_current_user` is a real coroutine
and whose admin client is a tiny fake supporting the PostgREST query chain
(`.table().select().order()/.eq().execute()` + `.table().update().eq().execute()`).

Asserts: role gate (403 non-admin), 401 on missing token, GET returns ALL rows
(incl. desenvolvimento / desativado), PATCH updates the status, PATCH 400 on an
invalid status value, PATCH 422 on an unknown body key (StrictHttpModel), PATCH
404 on an unknown id, and the `updated_at` defensive-optional bump (present when
the column exists, absent when it doesn't).
"""
from __future__ import annotations

from typing import Optional

import pytest
from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_seed.status_pagina_router import _create_status_pagina_router


# ─── Fakes ────────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Records the chained ops; `.execute()` resolves against the seeded rows.

    Supports the two shapes the router uses:
      select("*").order(col).execute()            → all rows
      select("*").eq("id", v).execute()           → filtered rows
      update(payload).eq("id", v).execute()       → mutate + return updated row
    """

    def __init__(self, store: "_FakeTable"):
        self._store = store
        self._mode = None          # "select" | "update"
        self._eq: dict = {}
        self._payload: dict = {}

    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def order(self, *_a, **_k):
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def _match(self, row) -> bool:
        return all(str(row.get(k)) == str(v) for k, v in self._eq.items())

    def execute(self):
        rows = [r for r in self._store.rows if self._match(r)]
        if self._mode == "select":
            return _FakeResult([dict(r) for r in rows])
        # update: mutate matched rows in place, return the updated copies
        updated = []
        for r in rows:
            r.update(self._payload)
            updated.append(dict(r))
        return _FakeResult(updated)


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows


class _FakeAdmin:
    """Schema-scoped service-role client stand-in. Only `status_pagina` wired."""

    def __init__(self, rows):
        self._table = _FakeTable(rows)

    def table(self, name):
        assert name == "status_pagina", f"unexpected table {name!r}"
        return _FakeQuery(self._table)


class _FakeUser:
    def __init__(self, role="owner"):
        self.user_metadata = {"role": role}


class _FakeDeps:
    """`ProductDependencies`-shaped: async get_current_user, imperative role,
    admin client returning a schema-scoped fake."""

    def __init__(self, rows, role="owner", authed=True):
        self._rows = rows
        self._role = role
        self._authed = authed

    async def get_current_user(self, authorization: Optional[str] = Header(None)):
        if not self._authed or not authorization:
            raise HTTPException(status_code=401, detail="Token ausente")
        return _FakeUser(self._role), "tok"

    def get_user_role(self, user) -> str:
        return self._role

    def get_admin_client(self):
        return _FakeAdmin(self._rows)


def _client(rows, role="owner", authed=True) -> TestClient:
    deps = _FakeDeps(rows, role=role, authed=authed)
    app = FastAPI()
    app.include_router(_create_status_pagina_router(deps, object(), "Test Product"))
    return TestClient(app, raise_server_exceptions=True)


def _erp_rows():
    # erp shape: has tipo_pagina + updated_at
    return [
        {"id": "11111111-1111-1111-1111-111111111111", "nome_pagina": "dashboard",
         "status": "producao", "descricao": None, "tipo_pagina": "geral",
         "updated_at": "2026-01-01T00:00:00+00:00"},
        {"id": "22222222-2222-2222-2222-222222222222", "nome_pagina": "matching",
         "status": "desenvolvimento", "descricao": "beta", "tipo_pagina": "geral",
         "updated_at": "2026-01-01T00:00:00+00:00"},
    ]


def _sw_rows():
    # social-wiring shape: NO tipo_pagina, NO updated_at
    return [
        {"id": "33333333-3333-3333-3333-333333333333", "nome_pagina": "clientes",
         "status": "producao", "descricao": None},
        {"id": "44444444-4444-4444-4444-444444444444", "nome_pagina": "conexoes",
         "status": "desativado", "descricao": None},
    ]


# ─── GET ──────────────────────────────────────────────────────────────────

def test_get_returns_all_rows_incl_non_producao():
    c = _client(_erp_rows(), role="owner")
    r = c.get("/api/status-paginas", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    statuses = {row["status"] for row in data}
    # ALL rows returned — desenvolvimento is NOT filtered out (admin client).
    assert statuses == {"producao", "desenvolvimento"}
    # defensive-optional columns surface when present
    assert data[0]["tipo_pagina"] == "geral"
    assert data[0]["updated_at"] is not None


def test_get_sw_shape_optional_columns_null():
    c = _client(_sw_rows(), role="admin")
    r = c.get("/api/status-paginas", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    # social-wiring has no tipo_pagina / updated_at → serialized as null.
    assert data[0]["tipo_pagina"] is None
    assert data[0]["updated_at"] is None


def test_get_role_gate_403_for_non_admin():
    c = _client(_erp_rows(), role="member")
    r = c.get("/api/status-paginas", headers={"Authorization": "Bearer x"})
    assert r.status_code == 403


def test_get_401_on_missing_token():
    c = _client(_erp_rows(), role="owner")
    r = c.get("/api/status-paginas")
    # Strict: deps rejects the missing token with exactly 401 (auth-boundary).
    assert r.status_code == 401


@pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "dev"])
def test_get_allowed_roles(role):
    c = _client(_erp_rows(), role=role)
    r = c.get("/api/status-paginas", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200


# ─── PATCH ────────────────────────────────────────────────────────────────

def test_patch_updates_status_and_bumps_updated_at_when_column_exists():
    rows = _erp_rows()
    c = _client(rows, role="owner")
    r = c.patch(
        "/api/status-paginas/11111111-1111-1111-1111-111111111111",
        json={"status": "desativado"},
        headers={"Authorization": "Bearer x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "desativado"
    # updated_at column exists on erp → bumped (no longer the seeded value).
    assert body["updated_at"] != "2026-01-01T00:00:00+00:00"


def test_patch_sw_shape_no_updated_at_column():
    rows = _sw_rows()
    c = _client(rows, role="dev")
    r = c.patch(
        "/api/status-paginas/33333333-3333-3333-3333-333333333333",
        json={"status": "desenvolvimento"},
        headers={"Authorization": "Bearer x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "desenvolvimento"
    assert body["updated_at"] is None
    # Column absent → the update payload never carried updated_at (no PGRST204).
    assert "updated_at" not in rows[0]


def test_patch_invalid_status_400():
    c = _client(_erp_rows(), role="owner")
    r = c.patch(
        "/api/status-paginas/11111111-1111-1111-1111-111111111111",
        json={"status": "bogus"},
        headers={"Authorization": "Bearer x"},
    )
    assert r.status_code == 400


def test_patch_unknown_key_422_strict_body():
    c = _client(_erp_rows(), role="owner")
    r = c.patch(
        "/api/status-paginas/11111111-1111-1111-1111-111111111111",
        json={"status": "producao", "nome_pagina": "hijack"},
        headers={"Authorization": "Bearer x"},
    )
    # StrictHttpModel extra="forbid" → 422 on the unknown key.
    assert r.status_code == 422


def test_patch_unknown_id_404():
    c = _client(_erp_rows(), role="owner")
    r = c.patch(
        "/api/status-paginas/99999999-9999-9999-9999-999999999999",
        json={"status": "producao"},
        headers={"Authorization": "Bearer x"},
    )
    assert r.status_code == 404


def test_patch_role_gate_403_for_non_admin():
    c = _client(_erp_rows(), role="viewer")
    r = c.patch(
        "/api/status-paginas/11111111-1111-1111-1111-111111111111",
        json={"status": "producao"},
        headers={"Authorization": "Bearer x"},
    )
    assert r.status_code == 403
