"""Cartório data on an imóvel (migration 075).

WHAT THESE PIN
--------------
- an imóvel with no row yet reads as every field null, not as a 404 and not
  as `{}` — "nothing recorded" is the normal state of a freshly synced
  property, not an error;
- the authored table never touches the Vista mirror;
- `numero_matricula` stamps its own provenance when a human types it, and
  drops that provenance when they clear it;
- a field the API does not own is REFUSED by name, never silently dropped.

Auth is not re-tested here — `test_auth_boundary.py` enumerates every
mounted route and asserts a strict 401 on each.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.imovel_hub.conftest import (
    CODIGO,
    ORG_ID,
    auth,
    dados_row,
    imovel_row,
    seed,
)


class TestReading:
    def test_an_imovel_with_no_cartorio_row_reads_as_all_null(self, client, scoped):
        """🔴 The distinction a caller must never have to make.

        "No row" and "a row with nothing in it" mean the same thing to a
        user, so they must look the same over the wire — otherwise every
        consumer branches on it, differently.
        """
        seed(scoped)
        r = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth())
        assert r.status_code == 200
        body = r.json()
        assert body["codigo"] == CODIGO
        assert body["numero_matricula"] is None
        assert body["numero_registro_imoveis"] is None
        assert body["prefeitura_cadastro_imobiliario"] is None
        assert body["captador"] is None

    def test_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        r = client.get("/api/imoveis/NOPE9999/dados", headers=auth())
        assert r.status_code == 404

    def test_an_imovel_from_another_org_is_not_visible(self, client, scoped):
        seed(scoped, imoveis=[imovel_row(org_id=str(uuid4()))])
        r = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth())
        assert r.status_code == 404

    def test_stored_values_come_back(self, client, scoped):
        seed(
            scoped,
            dados=[
                dados_row(
                    numero_matricula="12345",
                    numero_registro_imoveis="5º RI",
                    prefeitura_cadastro_imobiliario="Sao Paulo",
                )
            ],
        )
        body = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert body["numero_matricula"] == "12345"
        assert body["numero_registro_imoveis"] == "5º RI"
        assert body["prefeitura_cadastro_imobiliario"] == "Sao Paulo"


class TestWriting:
    def test_the_first_patch_creates_the_row(self, client, scoped):
        seed(scoped)
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"numero_registro_imoveis": "2º RI"},
            headers=auth(),
        )
        assert r.status_code == 200
        assert r.json()["numero_registro_imoveis"] == "2º RI"

    def test_a_second_patch_updates_without_clobbering_the_first(
        self, client, scoped
    ):
        """Absence means "leave alone" — the whole reason the service reads
        `model_fields_set` rather than dropping nulls."""
        seed(scoped)
        client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"numero_registro_imoveis": "2º RI"},
            headers=auth(),
        )
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"prefeitura_cadastro_imobiliario": "Santos"},
            headers=auth(),
        )
        assert r.json()["numero_registro_imoveis"] == "2º RI"
        assert r.json()["prefeitura_cadastro_imobiliario"] == "Santos"

    def test_an_explicit_null_clears_a_field(self, client, scoped):
        """`None` is a real value. A wrongly-typed number has to be erasable."""
        seed(scoped, dados=[dados_row(numero_registro_imoveis="2º RI")])
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"numero_registro_imoveis": None},
            headers=auth(),
        )
        assert r.json()["numero_registro_imoveis"] is None

    def test_typing_a_matricula_stamps_manual_provenance(self, client, scoped):
        """A human IS the provenance, and it is recorded so a later extraction
        can tell the column is already spoken for."""
        seed(scoped)
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"numero_matricula": "12345"},
            headers=auth(),
        )
        body = r.json()
        assert body["numero_matricula"] == "12345"
        assert body["numero_matricula_origem"] == "manual"
        assert body["numero_matricula_em"] is not None

    def test_clearing_a_matricula_clears_its_provenance_too(self, client, scoped):
        """🔴 A stale origin pointing at a number that is no longer there is
        worse than no origin at all."""
        seed(
            scoped,
            dados=[
                dados_row(
                    numero_matricula="12345",
                    numero_matricula_origem="matricula",
                    numero_matricula_em="2026-01-01T00:00:00+00:00",
                )
            ],
        )
        body = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"numero_matricula": None},
            headers=auth(),
        ).json()
        assert body["numero_matricula"] is None
        assert body["numero_matricula_origem"] is None
        assert body["numero_matricula_em"] is None

    def test_a_provenance_column_cannot_be_set_from_the_body(self, client, scoped):
        """Stamped, never accepted. `StrictHttpModel` refuses the unknown key
        by name rather than dropping it — a silently-ignored field is
        indistinguishable from a saved one."""
        seed(scoped)
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"numero_matricula_origem": "manual"},
            headers=auth(),
        )
        assert r.status_code == 422
        assert "numero_matricula_origem" in r.text

    def test_patching_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        r = client.patch(
            "/api/imoveis/NOPE9999/dados",
            json={"numero_registro_imoveis": "2º RI"},
            headers=auth(),
        )
        assert r.status_code == 404


class TestTheVistaMirrorIsNeverTouched:
    def test_writing_cartorio_data_leaves_the_imoveis_row_alone(
        self, client, scoped
    ):
        """🔴 The whole reason migration 075 is a separate table.

        `imoveis` is re-upserted by every Vista sync. If authored data landed
        there, a sync payload that stopped carrying the column would silently
        null a número de matrícula mid-sale.
        """
        seed(scoped)

        def mirror():
            # Read it back the way production would, not through a test-only
            # accessor — the question is what a subsequent request SEES.
            return (
                scoped.table("imoveis")
                .select("*")
                .eq("org_id", ORG_ID)
                .eq("codigo", CODIGO)
                .execute()
            ).data or []

        antes = [dict(row) for row in mirror()]
        assert antes, "fixture did not seed the mirror"

        client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"numero_matricula": "12345", "prefeitura_cadastro_imobiliario": "SP"},
            headers=auth(),
        )

        assert [dict(row) for row in mirror()] == antes
        # And the authored column never appears on the mirror at all.
        assert all("numero_matricula" not in row for row in antes)
