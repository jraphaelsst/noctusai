"""`POST /api/imoveis/{codigo}/documentos/{documento_id}/extrair` — re-run a
finished (or failed) read IN PLACE, never delete + re-upload.

A matrícula-number parser fix (2026-09-28, CNM check-digit handling) left
prod documents holding stale reads under the OLD parser, and delete +
re-upload would destroy the document's `imovel_documento_acessos` LGPD
access history (migration 109/111) — this is the recovery path, mirroring
`card_hub.documentos_service.reextrair_documento`'s contract.

Auth is not re-tested here — `test_imovel_auth_boundary.py` enumerates every
mounted route.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.imovel_hub import documentos_service
from tests.modules.imovel_hub.conftest import CODIGO, ORG_ID, auth, documento_row, seed

ORG = UUID(ORG_ID)


def _reextrair(client, did, codigo=CODIGO):
    return client.post(
        f"/api/imoveis/{codigo}/documentos/{did}/extrair", headers=auth()
    )


def _row(scoped, did):
    return [
        r
        for r in scoped.table("imovel_documentos").select("*").execute().data
        if r["id"] == did
    ][0]


class TestReextrairViaRoute:
    def test_a_finished_matricula_read_is_requeued(
        self, client, scoped, fake_storage, fake_extractor
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, extracao_status="ok", extracao_matricula="12345",
            extracao_tentativas=1,
        )])
        r = _reextrair(client, did)
        assert r.status_code == 200, r.text
        body = r.json()
        # Set synchronously, before whatever the background job does.
        assert body["extracao_status"] == "pendente"
        assert body["extracao_erro"] is None

    def test_a_sem_dados_read_is_requeued(
        self, client, scoped, fake_storage, fake_extractor
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, extracao_status="sem_dados", extracao_tentativas=1,
        )])
        r = _reextrair(client, did)
        assert r.status_code == 200, r.text
        assert r.json()["extracao_status"] == "pendente"

    def test_an_erro_read_is_requeued_without_resetting_tentativas(
        self, client, scoped, fake_storage, fake_extractor
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, extracao_status="erro",
            extracao_erro="insufficient_quota: sem creditos",
            extracao_tentativas=2,
        )])
        r = _reextrair(client, did)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["extracao_status"] == "pendente"
        assert body["extracao_erro"] is None
        # 🔴 A deliberate human retry is not the unattended sweep's budget
        # to hide — never reset, only ever bumped by an actual attempt.
        row = _row(scoped, did)
        assert row["extracao_tentativas"] >= 2

    def test_refuses_while_the_number_read_is_already_in_flight(
        self, client, scoped, fake_storage, fake_extractor
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, extracao_status="processando")])
        r = _reextrair(client, did)
        assert r.status_code == 400, r.text
        assert "extracao_status" in r.text

    def test_refuses_while_the_structured_read_is_already_in_flight(
        self, client, scoped, fake_storage, fake_extractor
    ):
        # `cnd_iptu` carries ONLY the structured pipeline (not a
        # número-de-matrícula candidate) — isolates the estrutura guard.
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, tipo_documento="cnd_iptu", estrutura_status="pendente",
        )])
        r = _reextrair(client, did)
        assert r.status_code == 400, r.text
        assert "estrutura_status" in r.text

    def test_a_structured_only_tipo_is_requeued_without_touching_numero(
        self, client, scoped, fake_storage, fake_extractor
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, tipo_documento="guia_iptu", estrutura_status="ok",
            extracao_status=None,
        )])
        r = _reextrair(client, did)
        assert r.status_code == 200, r.text
        body = r.json()
        # `guia_iptu` is never a número-de-matrícula candidate — untouched.
        assert body["extracao_status"] is None

    def test_a_manually_confirmed_structured_read_is_never_overwritten(
        self, client, scoped, fake_storage, fake_extractor
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, tipo_documento="cnd_iptu", estrutura_status="ok",
            numero="CND-1", origem="manual", confirmado_por="user-1",
        )])
        r = _reextrair(client, did)
        assert r.status_code == 200, r.text
        body = r.json()
        # The confirmed field is never touched by the re-run — same value
        # the row had before, regardless of whatever the background job
        # (which self-guards on `origem`/`confirmado_por`) does with
        # `estrutura_status` under the hood.
        assert body["numero"] == "CND-1"
        assert body["origem"] == "manual"

    def test_an_unknown_document_is_a_404(self, client, scoped):
        seed(scoped)
        r = _reextrair(client, str(uuid4()))
        assert r.status_code == 404


class TestReextrairServiceDirectly:
    """Branches unreachable through the fixed `TIPOS_DOCUMENTO` vocabulary
    today (every registered imóvel tipo carries at least one pipeline) —
    exercised directly against the service, same posture
    `test_a_guia_iptu_is_refused_even_if_the_job_is_called_directly` uses
    one file over."""

    def test_a_tipo_with_neither_pipeline_is_refused_by_name(self, scoped):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, tipo_documento="matricula")])
        # Simulate a tipo this module's vocabulary has since retired —
        # `deve_extrair`/`deve_extrair_estrutura` both read off
        # `tipo_documento`, so an unrecognised value refuses cleanly rather
        # than silently reading nothing.
        row = _row(scoped, did)
        row["tipo_documento"] = "outro"
        scoped.set_table_data("imovel_documentos", [row])
        with pytest.raises(ValidationError_) as exc:
            documentos_service.reextrair_documento(scoped, ORG, CODIGO, did)
        assert exc.value.details["field"] == "tipo_documento"
