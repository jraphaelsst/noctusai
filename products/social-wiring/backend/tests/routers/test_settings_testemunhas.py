"""`/api/settings/imobiliaria/testemunhas` — the org's standing signature
witnesses, max 2 (migration 108).

🔴 A LOCAL FIXTURE, NOT THE SHARED `scoped` ONE
---------------------------------------------------
`settings_router.py`'s imobiliaria/testemunhas routes resolve
`get_user_client(token)` fresh, INLINE, on every call, then chain
`.schema("social_wiring")` — and `MockSupabaseClient.schema()` returns a
BRAND NEW wrapper (empty table registry) every time it is invoked, same data-
loss shape `card_hub/deps.py`'s own docstring documents for the identical
Supabase-mock behaviour. A round trip (POST then GET) needs ONE stable
scoped instance across a test's several HTTP calls, so `testemunhas_scoped`
below patches `get_user_client` — this router's own DI seam, not a guard —
to always hand back the same cached scoped client, mirroring how the shared
`client` fixture itself patches `DatabaseModule.get_client`/`get_admin_client`
(`unittest.mock.patch`, per `KB § PATTERNS/backend/di-test-seam.md`).

This is a PRE-EXISTING gap, not one introduced here: zero tests exist today
for `dados_imobiliaria`/`agentes_financeiros`, the two other
`get_user_client(token).schema(...)`-inline endpoints in this router — see
this migration's delivery note (`drift-found:`).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.dependencies import coerce_org_uuid

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))


class _StableSchemaClient:
    """`.schema(name)` always returns the SAME cached instance, regardless of
    `name` — the route calls `get_user_client(token).schema("social_wiring")`
    fresh on every request; without this, each call would re-invoke the real
    `MockSupabaseClient.schema()` and get a brand new, empty table registry."""

    def __init__(self, scoped: Any):
        self._scoped = scoped

    def schema(self, _name: str) -> Any:
        return self._scoped


@pytest.fixture
def testemunhas_scoped(client):
    scoped = client.mock_supabase.schema("social_wiring")
    with patch(
        "app.routers.settings_router.get_user_client",
        return_value=_StableSchemaClient(scoped),
    ):
        yield scoped


class TestListAndCreate:
    def test_a_fresh_org_has_no_testemunhas(self, client, testemunhas_scoped):
        r = client.get("/api/settings/imobiliaria/testemunhas")
        assert r.status_code == 200, r.text
        assert r.json() == {"items": [], "total": 0}

    def test_creating_a_testemunha_round_trips(self, client, testemunhas_scoped):
        r = client.post(
            "/api/settings/imobiliaria/testemunhas",
            json={"nome": "João Silva", "cpf": "123.456.789-00", "rg": "MG-1234567"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["nome"] == "João Silva"
        assert body["cpf"] == "123.456.789-00"

        listado = client.get("/api/settings/imobiliaria/testemunhas").json()
        assert listado["total"] == 1
        assert listado["items"][0]["nome"] == "João Silva"

    def test_a_second_testemunha_is_accepted(self, client, testemunhas_scoped):
        client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Primeira"}
        )
        r = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Segunda"}
        )
        assert r.status_code == 201, r.text
        assert client.get(
            "/api/settings/imobiliaria/testemunhas"
        ).json()["total"] == 2

    def test_a_third_testemunha_is_refused_with_409(self, client, testemunhas_scoped):
        client.post("/api/settings/imobiliaria/testemunhas", json={"nome": "Um"})
        client.post("/api/settings/imobiliaria/testemunhas", json={"nome": "Dois"})
        r = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Três"}
        )
        assert r.status_code == 409, r.text
        assert "2" in r.text


class TestUpdateAndDelete:
    def test_updating_a_testemunha(self, client, testemunhas_scoped):
        created = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "João"}
        ).json()
        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{created['id']}",
            json={"rg": "MG-9999999"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["rg"] == "MG-9999999"
        assert r.json()["nome"] == "João"

    def test_an_unknown_testemunha_patch_is_404(self, client, testemunhas_scoped):
        import uuid
        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{uuid.uuid4()}",
            json={"nome": "X"},
        )
        assert r.status_code == 404

    def test_deleting_a_testemunha_frees_a_slot(self, client, testemunhas_scoped):
        um = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Um"}
        ).json()
        client.post("/api/settings/imobiliaria/testemunhas", json={"nome": "Dois"})

        removed = client.delete(
            f"/api/settings/imobiliaria/testemunhas/{um['id']}"
        )
        assert removed.status_code == 204

        # The slot freed by the delete accepts a third testemunha now.
        r = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Três"}
        )
        assert r.status_code == 201, r.text
