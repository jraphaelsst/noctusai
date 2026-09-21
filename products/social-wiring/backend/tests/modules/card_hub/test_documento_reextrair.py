"""`POST /api/clientes/{cliente_id}/documentos/{documento_id}/extrair` —
re-queue extraction for a document that was never read, or whose reading
ended in `erro` (the recovery path that used to be "delete + re-upload,
which destroys the LGPD access history").

Storage is ALWAYS the `fake_storage` fixture and the extractor is ALWAYS
`fake_identity_extractor` — never a real vision provider. Per
`KB § PATTERNS/backend/di-test-seam.md` Class-B.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.card_hub.deps import BUCKET
from tests.modules.card_hub.conftest import ORG_ID, cliente_row, documento_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _url(cid: str, did: str) -> str:
    return f"/api/clientes/{cid}/documentos/{did}/extrair"


def _stored(scoped, did: str) -> dict:
    return scoped.table("cliente_documentos").select("*").eq("id", did).execute().data[0]


class TestRefusals:
    def test_404_unknown_documento(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.post(_url(cid, str(uuid4())), headers=_auth())
        assert resp.status_code == 404, resp.text

    def test_400_when_tipo_documento_is_not_extractable(self, client, scoped):
        """A document filed as `outro` (Gap 1's exact prod symptom) cannot
        be re-queued through this endpoint — re-typing an already-uploaded
        document is a separate, prerequisite fix."""
        cid = str(uuid4())
        did = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_documentos",
            [documento_row(did, cid, tipo_documento="outro", categoria_lgpd="nao_classificado")],
        )
        resp = client.post(_url(cid, did), headers=_auth())
        assert resp.status_code == 400, resp.text
        assert "não é extraível" in resp.json()["error"]["message"]

    @pytest.mark.parametrize("status_em_andamento", ["pendente", "processando"])
    def test_400_when_extraction_already_in_flight(self, client, scoped, status_em_andamento):
        cid = str(uuid4())
        did = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    did, cid, tipo_documento="rg", categoria_lgpd="identidade",
                    extracao_status=status_em_andamento,
                )
            ],
        )
        resp = client.post(_url(cid, did), headers=_auth())
        assert resp.status_code == 400, resp.text
        assert status_em_andamento in resp.json()["error"]["message"]

    def test_404_for_a_soft_deleted_documento(self, client, scoped):
        cid = str(uuid4())
        did = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_documentos",
            [documento_row(did, cid, tipo_documento="rg", deleted_at="2026-01-01T00:00:00+00:00")],
        )
        resp = client.post(_url(cid, did), headers=_auth())
        assert resp.status_code == 404, resp.text


class TestReQueuesAndRuns:
    @pytest.mark.asyncio
    async def test_resets_erro_and_re_runs_immediately(
        self, client, scoped, fake_storage, fake_identity_extractor
    ):
        """The exact prod shape: a document stuck in `erro` (an OpenAI 429)
        must become re-runnable once credentials/quota are fixed — without
        deleting and re-uploading, which would destroy the access log."""
        cid = str(uuid4())
        did = str(uuid4())
        path = f"{ORG_ID}/clientes/{cid}/{did}"
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    did, cid,
                    tipo_documento="rg", categoria_lgpd="identidade",
                    storage_path=path,
                    extracao_status="erro",
                    extracao_erro="openai: 429 credit_balance_exhausted",
                    extracao_tentativas=2,
                )
            ],
        )
        await fake_storage.put(
            bucket=BUCKET, key=path, data=b"%PDF-1.4 fake", content_type="application/pdf"
        )

        resp = client.post(_url(cid, did), headers=_auth())
        assert resp.status_code == 200, resp.text
        # The RESPONSE is the snapshot taken the moment the reset committed —
        # BEFORE the background task (scheduled below, in the same request)
        # ran. `TestClient` executes background tasks synchronously as part
        # of the ASGI response lifecycle, so by the time we re-read the row
        # from the mock further down it has already moved past `pendente`.
        body = resp.json()
        assert body["extracao_status"] == "pendente"
        assert body["extracao_erro"] is None

        # And the background task (this exact request's own) already ran the
        # fake extractor end to end and landed on a terminal state.
        final = _stored(scoped, did)
        assert final["extracao_status"] == "ok"
        assert final["extracao_erro"] is None
        # 🔴 Preserved, not reset — tentativas 2 -> 3 is `extrair_identidade`'s
        # OWN unconditional increment (see that function), not a fresh start.
        assert final["extracao_tentativas"] == 3
        assert fake_identity_extractor.calls, "the fake extractor was never called"

    @pytest.mark.asyncio
    async def test_never_queued_document_becomes_queueable(
        self, client, scoped, fake_storage, fake_identity_extractor
    ):
        """`extracao_status IS NULL` — a document whose type was not yet
        `deve_extrair`-eligible at upload time (or, before this endpoint
        existed, simply never queued for any reason) is exactly as
        re-runnable as one that already failed once."""
        cid = str(uuid4())
        did = str(uuid4())
        path = f"{ORG_ID}/clientes/{cid}/{did}"
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    did, cid,
                    tipo_documento="certidao_casamento", categoria_lgpd="identidade",
                    storage_path=path,
                )
            ],
        )
        await fake_storage.put(
            bucket=BUCKET, key=path, data=b"%PDF-1.4 fake", content_type="application/pdf"
        )

        resp = client.post(_url(cid, did), headers=_auth())
        assert resp.status_code == 200, resp.text
        final = _stored(scoped, did)
        assert final["extracao_status"] == "ok"
        assert final["extracao_tentativas"] == 1
