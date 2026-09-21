"""`/api/settings/imobiliaria/testemunhas` — the org's standing signature
witnesses, max 2 (migration 108).

🔴 A LOCAL FIXTURE, NOT THE SHARED `scoped` ONE — AND A REAL `Depends()` SEAM,
NOT A PATCH OF OUR OWN CODE
--------------------------------------------------------------------------------
`settings_router.py`'s testemunhas (and `dados_imobiliaria`) routes resolve
the caller's own client via `Depends(get_social_wiring_client)`
(`app/dependencies.py`) — a cached, schema-scoped client, fixing the defect
`get_user_client(token).schema(...)`-inline used to have: `MockSupabaseClient.
schema()` returns a BRAND NEW wrapper (empty table registry) every time it is
invoked, so re-deriving it fresh per call silently lost every prior write
within a test — see `get_scoped_user_client`'s docstring.

Because the client now arrives via a real FastAPI dependency, this fixture
uses `app.dependency_overrides` — the sanctioned DI-test-seam
(`KB § PATTERNS/backend/di-test-seam.md` Class-B), not `unittest.mock.patch`
of our own module (CLAUDE.md §1 forbids monkeypatching our own code,
including in tests). `testemunhas_scoped` overrides `get_social_wiring_client`
with a shared-state fake so a test's several HTTP calls (POST then GET, …)
see one consistent view — same shape `card_hub/conftest.py`'s `fake_storage`
fixture uses for `get_storage_backend`.
"""
from __future__ import annotations

import pytest

from app.dependencies import coerce_org_uuid, get_social_wiring_client

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))


@pytest.fixture
def testemunhas_scoped(client):
    from app.main import app

    scoped = client.mock_supabase.schema("social_wiring")
    prev = app.dependency_overrides.get(get_social_wiring_client)
    app.dependency_overrides[get_social_wiring_client] = lambda: scoped
    yield scoped
    if prev is None:
        app.dependency_overrides.pop(get_social_wiring_client, None)
    else:
        app.dependency_overrides[get_social_wiring_client] = prev


class TestListAndCreate:
    def test_a_fresh_org_has_no_testemunhas(self, client, testemunhas_scoped):
        r = client.get("/api/settings/imobiliaria/testemunhas")
        assert r.status_code == 200, r.text
        assert r.json() == {"items": [], "total": 0}

    def test_creating_a_testemunha_round_trips(self, client, testemunhas_scoped):
        r = client.post(
            "/api/settings/imobiliaria/testemunhas",
            json={
                "nome": "João Silva", "cpf": "123.456.789-00", "rg": "MG-1234567",
                "email": "joao.silva@exemplo.test",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["nome"] == "João Silva"
        assert body["cpf"] == "123.456.789-00"
        assert body["email"] == "joao.silva@exemplo.test"

        listado = client.get("/api/settings/imobiliaria/testemunhas").json()
        assert listado["total"] == 1
        assert listado["items"][0]["nome"] == "João Silva"
        assert listado["items"][0]["email"] == "joao.silva@exemplo.test"

    def test_a_testemunha_without_an_email_is_accepted(self, client, testemunhas_scoped):
        """[migration 143] e-mail is optional — Contract 08's real witnesses
        only carry nome/rg; the registry must not force one."""
        r = client.post(
            "/api/settings/imobiliaria/testemunhas",
            json={"nome": "Sem E-mail", "rg": "MG-0000000"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["email"] is None

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

    def test_updating_a_testemunhas_email(self, client, testemunhas_scoped):
        created = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "João"}
        ).json()
        assert created["email"] is None
        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{created['id']}",
            json={"email": "joao@exemplo.test"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "joao@exemplo.test"

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
