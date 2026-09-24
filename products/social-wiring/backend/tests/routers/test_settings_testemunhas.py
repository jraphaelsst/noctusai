"""`/api/settings/imobiliaria/testemunhas` — the org's REGISTRY of signature
witnesses (migration 108, opened up by 168 — no more 2-per-org cap, CPF now
required on create).

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

#: mod-11-valid synthetic CPFs — never a real person's.
CPF_1 = "111.444.777-35"
CPF_2 = "529.982.247-25"
CPF_3 = "935.411.347-80"


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
                "nome": "João Silva", "cpf": CPF_1, "celular": "11988887777",
                "email": "joao.silva@exemplo.test",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["nome"] == "João Silva"
        assert body["cpf"] == CPF_1
        assert body["celular"] == "11988887777"
        assert body["email"] == "joao.silva@exemplo.test"
        assert body["cpf_pendente"] is False

        listado = client.get("/api/settings/imobiliaria/testemunhas").json()
        assert listado["total"] == 1
        assert listado["items"][0]["nome"] == "João Silva"
        assert listado["items"][0]["email"] == "joao.silva@exemplo.test"

    def test_a_testemunha_without_an_email_is_accepted(self, client, testemunhas_scoped):
        """[migration 143] e-mail is optional — the registry must not force
        one."""
        r = client.post(
            "/api/settings/imobiliaria/testemunhas",
            json={"nome": "Sem E-mail", "cpf": CPF_1},
        )
        assert r.status_code == 201, r.text
        assert r.json()["email"] is None

    def test_a_missing_cpf_is_refused_with_422(self, client, testemunhas_scoped):
        """[Migration 168, owner decision] CPF is REQUIRED on create — the
        contract prints it instead of RG."""
        r = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Sem CPF"}
        )
        assert r.status_code == 422, r.text

    def test_an_invalid_cpf_is_refused_with_422(self, client, testemunhas_scoped):
        r = client.post(
            "/api/settings/imobiliaria/testemunhas",
            json={"nome": "CPF Ruim", "cpf": "111.111.111-11"},
        )
        assert r.status_code == 422, r.text

    def test_more_than_two_testemunhas_are_all_accepted(self, client, testemunhas_scoped):
        """[Migration 168] The 2-per-org cap is GONE — this is a registry
        now, not a fixed pair."""
        for nome, cpf in (("Um", CPF_1), ("Dois", CPF_2), ("Três", CPF_3)):
            r = client.post(
                "/api/settings/imobiliaria/testemunhas", json={"nome": nome, "cpf": cpf}
            )
            assert r.status_code == 201, r.text
        assert client.get(
            "/api/settings/imobiliaria/testemunhas"
        ).json()["total"] == 3


class TestUpdateAndDelete:
    def test_updating_a_testemunha(self, client, testemunhas_scoped):
        created = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "João", "cpf": CPF_1}
        ).json()
        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{created['id']}",
            json={"celular": "11999998888"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["celular"] == "11999998888"
        assert r.json()["nome"] == "João"

    def test_updating_a_testemunhas_email(self, client, testemunhas_scoped):
        created = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "João", "cpf": CPF_1}
        ).json()
        assert created["email"] is None
        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{created['id']}",
            json={"email": "joao@exemplo.test"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "joao@exemplo.test"

    def test_an_invalid_cpf_patch_is_refused_with_422(self, client, testemunhas_scoped):
        created = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "João", "cpf": CPF_1}
        ).json()
        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{created['id']}",
            json={"cpf": "111.111.111-11"},
        )
        assert r.status_code == 422, r.text

    def test_an_unknown_testemunha_patch_is_404(self, client, testemunhas_scoped):
        import uuid
        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{uuid.uuid4()}",
            json={"nome": "X"},
        )
        assert r.status_code == 404

    def test_deleting_a_testemunha(self, client, testemunhas_scoped):
        um = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Um", "cpf": CPF_1}
        ).json()

        removed = client.delete(
            f"/api/settings/imobiliaria/testemunhas/{um['id']}"
        )
        assert removed.status_code == 204
        assert client.get(
            "/api/settings/imobiliaria/testemunhas"
        ).json()["total"] == 0


class TestSoftDelete:
    """Owner directive (2026-09-24): deleting a witness must not remove
    anything linked to it. DELETE is a soft delete (`excluida_em`) — the row
    survives, the registry list omits it, and every `contrato_testemunhas`
    selection that points at it is left untouched. `contratos_em_uso` is an
    informative count only; it never blocks the delete."""

    def test_delete_keeps_the_row_and_every_contract_selection(
        self, client, testemunhas_scoped
    ):
        um = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Um", "cpf": CPF_1}
        ).json()
        selecao = {
            "id": "sel-1", "org_id": ORG_ID, "contrato_id": "contrato-1",
            "testemunha_id": um["id"], "ordem": 1,
        }
        testemunhas_scoped.set_table_data("contrato_testemunhas", [selecao])

        assert client.delete(
            f"/api/settings/imobiliaria/testemunhas/{um['id']}"
        ).status_code == 204

        linhas = testemunhas_scoped.table("org_testemunhas").select("*").execute().data
        assert [r["id"] for r in linhas] == [um["id"]]
        assert linhas[0]["excluida_em"]
        selecoes = (
            testemunhas_scoped.table("contrato_testemunhas").select("*").execute().data
        )
        assert [r["id"] for r in selecoes] == ["sel-1"]

    def test_a_deleted_witness_cannot_be_deleted_or_edited_again(
        self, client, testemunhas_scoped
    ):
        um = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Um", "cpf": CPF_1}
        ).json()
        client.delete(f"/api/settings/imobiliaria/testemunhas/{um['id']}")

        assert client.delete(
            f"/api/settings/imobiliaria/testemunhas/{um['id']}"
        ).status_code == 404
        assert client.patch(
            f"/api/settings/imobiliaria/testemunhas/{um['id']}", json={"nome": "X"}
        ).status_code == 404

    def test_list_reports_how_many_contracts_use_each_witness(
        self, client, testemunhas_scoped
    ):
        um = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Um", "cpf": CPF_1}
        ).json()
        dois = client.post(
            "/api/settings/imobiliaria/testemunhas", json={"nome": "Dois", "cpf": CPF_2}
        ).json()
        testemunhas_scoped.set_table_data(
            "contrato_testemunhas",
            [
                {"id": "s1", "org_id": ORG_ID, "contrato_id": "c1", "testemunha_id": um["id"], "ordem": 1},
                {"id": "s2", "org_id": ORG_ID, "contrato_id": "c2", "testemunha_id": um["id"], "ordem": 1},
            ],
        )

        itens = {
            i["nome"]: i["contratos_em_uso"]
            for i in client.get("/api/settings/imobiliaria/testemunhas").json()["items"]
        }
        assert itens == {"Um": 2, "Dois": 0}


class TestCpfPendenteLegacyRows:
    """[Migration 168] The 2 rows migration 108 shipped (RG + e-mail, no
    CPF) are KEPT — this exercises that shape directly, without going
    through create (which now requires a CPF)."""

    def test_a_row_with_no_cpf_is_flagged_pendente(self, client, testemunhas_scoped):
        from datetime import datetime, timezone
        from uuid import uuid4

        testemunhas_scoped.table("org_testemunhas").insert(
            {
                "id": str(uuid4()), "org_id": ORG_ID, "nome": "Legada Sem CPF",
                "rg": "MG-1234567", "cpf": None, "email": "legada@exemplo.test",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        listado = client.get("/api/settings/imobiliaria/testemunhas").json()
        assert listado["total"] == 1
        assert listado["items"][0]["cpf_pendente"] is True
        assert listado["items"][0]["nome"] == "Legada Sem CPF"

    def test_patching_in_a_cpf_clears_the_pending_flag(self, client, testemunhas_scoped):
        from datetime import datetime, timezone
        from uuid import uuid4

        row_id = str(uuid4())
        testemunhas_scoped.table("org_testemunhas").insert(
            {
                "id": row_id, "org_id": ORG_ID, "nome": "Legada Sem CPF",
                "rg": "MG-1234567", "cpf": None, "email": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        r = client.patch(
            f"/api/settings/imobiliaria/testemunhas/{row_id}", json={"cpf": CPF_1}
        )
        assert r.status_code == 200, r.text
        assert r.json()["cpf_pendente"] is False
