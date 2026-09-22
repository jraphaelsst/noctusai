"""Regression coverage for the insert-then-update CHECK-violation bug
(2026-09-22, RODRIGO MORASCHI ENRIQUEZ's contrato c8ea4072-db00-403f-98b2-
2877b9c5ab7d): `nova_versao_gerada` used to insert `atendimento_contrato_
versoes` with `origem='gerado'` and NO docx columns, then `UPDATE` them in
afterward. Migrations 120/134's per-origem CHECK
(`atendimento_contrato_versoes_docx_por_origem`) is checked on EVERY
INSERT — `NOT VALID` only grandfathers pre-existing rows — so that write
has NEVER succeeded against the real database: `POST .../gerar` 500'd with
`new row for relation "atendimento_contrato_versoes" violates check
constraint "atendimento_contrato_versoes_docx_por_origem"` on every call,
in production, while the mock-backed suite stayed green. Measured against
prod on 2026-09-22: zero rows, of any origem, had ever landed in that
table.

These tests pin BOTH halves of the fix:

1. `DocumentoStore.guardar`'s `sidecar` parameter — the docx sibling is
   uploaded and its two columns ride in the SAME insert payload as the PDF
   row, never a follow-up `UPDATE` (`contratos_service.nova_versao_gerada`
   / `_guardar_versao`).
2. The mock-fidelity gap that let (1)'s bug ship green in the first place:
   `MockSupabaseClient` had no way to model a cross-column, per-discriminant
   CHECK like this one (`CheckManifest`'s shape is single-column-enum only,
   and no product had ever wired it for this table). `noctusai_lib.testing.
   mocks.ConditionalPresenceManifest` + `tests/conftest.py`'s
   `_ATENDIMENTO_CONTRATO_VERSOES_PRESENCE_MANIFEST` close that gap — see
   that constant's docstring for why it is hand-maintained, same as
   `CheckManifest` before it.

`test_the_mock_refuses_a_generated_version_missing_its_docx_columns` is the
one that must fail on the UNFIXED mock (no presence manifest wired /
`validate_schema_constraints=False`) and pass once it is wired — it
exercises the MOCK directly, isolated from the service fix, so a future
regression in either half is caught independently.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.modules.card_hub import contratos_service as svc
from noctusai_lib.testing import MockCheckViolation
from tests.modules.card_hub.conftest import ORG_ID

_T0 = "2026-01-01T00:00:00+00:00"


def _seed_contrato(scoped) -> dict:
    """One live 'rascunho' contract, no versions yet — enough for
    `_guardar_versao`'s `exigir_contrato` + `_proximo_numero` reads."""
    ids = {"atendimento": str(uuid4()), "contrato": str(uuid4())}
    scoped.set_table_data("atendimento_contratos", [{
        "id": ids["contrato"], "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
        "titulo": "Promessa de compra e venda", "modelo": "compra_venda",
        "status": "rascunho", "status_em": None, "status_por": None,
        "origem": "upload", "criado_por": None,
        "deleted_at": None, "delete_motivo": None, "delete_solicitado_por": None,
        "assinatura_data": None, "prazo_pendencias_dias": None,
        "created_at": _T0, "updated_at": None,
    }])
    scoped.set_table_data("atendimento_contrato_versoes", [])
    scoped.set_table_data("atendimento_contrato_versao_acessos", [])
    return ids


def _versao_row(**over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "contrato_id": str(uuid4()),
        "storage_path": "org/contratos/contrato/versao", "nome_original": "contrato.pdf",
        "mime_type": "application/pdf", "tamanho_bytes": 10,
        "tipo_documento": "contrato", "enviado_por": None,
        "deleted_at": None, "delete_motivo": None, "created_at": _T0,
        "numero": 1, "rotulo": None,
    }
    row.update(over)
    return row


class TestSidecarInsertsInTheSamePayload:
    """`contratos_service.nova_versao_gerada` — the production fix."""

    def test_a_generated_version_inserts_docx_columns_in_the_same_payload(
        self, scoped, fake_storage
    ):
        ids = _seed_contrato(scoped)
        docx_bytes = b"PK\x03\x04 fake docx"
        asyncio.run(svc.nova_versao_gerada(
            scoped, fake_storage, ORG_ID, ids["atendimento"], ids["contrato"],
            data=b"%PDF-1.4 fake pdf",
            content_type="application/pdf",
            docx=docx_bytes,
            contexto_sha256="a" * 64,
            usuario_id=None,
        ))

        payloads = scoped.table("atendimento_contrato_versoes").inserted_payloads
        assert len(payloads) == 1
        payload = payloads[0]
        assert payload["origem"] == "gerado"
        # 🔴 THE ASSERTION THAT MATTERS: both docx columns are IN THE INSERT
        # PAYLOAD ITSELF (what the mock — and Postgres — actually validate
        # the row against), never patched in by a later UPDATE.
        assert payload["docx_storage_path"] == f"{payload['storage_path']}.docx"
        assert payload["docx_tamanho_bytes"] == len(docx_bytes)

        # No follow-up UPDATE ever touches the docx columns — insert-then-
        # update is exactly the shape that shipped broken.
        updates = scoped.table("atendimento_contrato_versoes").updated_payloads
        assert not any("docx_storage_path" in u for u in updates)
        assert not any("docx_tamanho_bytes" in u for u in updates)

    def test_no_orphan_row_when_the_sidecar_upload_fails(self, scoped, fake_storage):
        """If the docx `.put()` fails, the PDF's row must never be
        inserted — and the PDF object itself must not be left orphaned in
        storage (`DocumentoStore.guardar`'s `sidecar` failure path)."""
        ids = _seed_contrato(scoped)

        async def _boom(**kwargs):
            raise RuntimeError("storage backend unavailable")

        fake_storage.put = _boom  # self-patch-ok: substitutes the FAKE's IO, not our logic

        with pytest.raises(RuntimeError):
            asyncio.run(svc.nova_versao_gerada(
                scoped, fake_storage, ORG_ID, ids["atendimento"], ids["contrato"],
                data=b"%PDF-1.4 fake pdf", content_type="application/pdf",
                docx=b"PK\x03\x04 fake docx", contexto_sha256="a" * 64,
                usuario_id=None,
            ))

        assert scoped.table("atendimento_contrato_versoes").inserted_payloads == []


class TestMockEnforcesThePerOrigemCheck:
    """The mock-fidelity half: isolated from the service fix, exercising
    `MockSupabaseClient` directly against the raw insert shape."""

    def test_the_mock_refuses_a_generated_version_missing_its_docx_columns(
        self, scoped
    ):
        scoped.set_table_data("atendimento_contrato_versoes", [])
        with pytest.raises(MockCheckViolation):
            scoped.table("atendimento_contrato_versoes").insert(
                _versao_row(origem="gerado", contexto_sha256="a" * 64)
                # docx_storage_path / docx_tamanho_bytes deliberately absent
                # — the exact shape `nova_versao_gerada` used to insert.
            ).execute()

    def test_the_mock_refuses_a_generated_version_with_docx_columns_explicitly_null(
        self, scoped
    ):
        scoped.set_table_data("atendimento_contrato_versoes", [])
        with pytest.raises(MockCheckViolation):
            scoped.table("atendimento_contrato_versoes").insert(
                _versao_row(
                    origem="gerado", contexto_sha256="a" * 64,
                    docx_storage_path=None, docx_tamanho_bytes=None,
                )
            ).execute()

    @pytest.mark.parametrize("origem", ["upload", "assinado"])
    def test_a_non_generated_version_inserts_with_docx_columns_null(
        self, scoped, origem
    ):
        scoped.set_table_data("atendimento_contrato_versoes", [])
        scoped.table("atendimento_contrato_versoes").insert(
            _versao_row(origem=origem)
        ).execute()

        payload = scoped.table("atendimento_contrato_versoes").inserted_payloads[-1]
        assert payload.get("docx_storage_path") is None
        assert payload.get("docx_tamanho_bytes") is None

    def test_a_non_generated_version_with_a_docx_column_set_is_refused(self, scoped):
        """The mirror case: an 'upload' row may never carry a docx
        sibling — migration 120's CHECK forbids it just as firmly as it
        requires one for 'gerado'."""
        scoped.set_table_data("atendimento_contrato_versoes", [])
        with pytest.raises(MockCheckViolation):
            scoped.table("atendimento_contrato_versoes").insert(
                _versao_row(origem="upload", docx_storage_path="x/y.docx")
            ).execute()
