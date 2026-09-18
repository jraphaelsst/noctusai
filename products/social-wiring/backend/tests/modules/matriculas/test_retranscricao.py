"""Migration 135 — source retention + re-transcribe-by-supersede.

Three things under test:

1. The standalone (no `codigo`) upload path now RETAINS the PDF instead of
   discarding it (`POST /extrair`, `arquivos_svc`).
2. `POST /extracoes/{id}/retranscrever` (`estrutura_svc.criar_retranscricao`)
   SUPERSEDES — a new row is inserted, the old one is marked
   `substituida_por` and NEVER has `texto_extraido` rewritten (the write-once
   trigger's guarantee is never fought, only respected).
3. `GET /extracoes/{id}/arquivo-original` returns a signed URL for whichever
   source the extraction actually kept, 409 when it kept none.
"""
from __future__ import annotations

import asyncio

import pytest

from app.modules.imovel_hub.deps import BUCKET
from app.modules.matriculas import arquivos_service as arquivos_svc
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    TEXTO,
    arquivo_row,
    documento_row,
    extracao_row,
    registry_row,
    seed,
)

_PDF_BYTES = b"%PDF-1.4 matricula sintetica"
_PDF = {"file": ("matricula.pdf", _PDF_BYTES, "application/pdf")}


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _guardar(fake_storage, bucket: str, storage_path: str) -> None:
    asyncio.run(
        fake_storage.put(
            bucket=bucket, key=storage_path, data=_PDF_BYTES, content_type="application/pdf"
        )
    )


# ─── POST /api/matriculas/extrair without codigo — the source is retained ──


@pytest.mark.usefixtures("com_credencial")
class TestStandaloneUploadRetainsTheSource:
    def test_the_pdf_is_kept_and_the_extraction_points_at_it(
        self, client, scoped, fake_storage, fake_extractor, stub_transcriber, background_db
    ):
        seed(scoped, registry=[registry_row()])
        client.mock_supabase.set_table_data("matricula_extracoes", [])

        _data(client.post("/api/matriculas/extrair", files=_PDF))

        arquivos = scoped.table("matricula_extracao_arquivos").inserted_payloads
        assert len(arquivos) == 1
        arquivo = arquivos[0]
        assert arquivo["tipo_documento"] == "matricula"
        assert arquivo["org_id"] == ORG_ID

        blob = asyncio.run(fake_storage.get(bucket=BUCKET, key=arquivo["storage_path"]))
        assert blob is not None and blob.data == _PDF_BYTES

        payload = client.mock_supabase.table("matricula_extracoes").inserted_payloads[-1]
        assert payload["arquivo_origem_id"] == arquivo["id"]
        assert "codigo" not in payload
        assert "imovel_documento_id" not in payload

    def test_a_linked_upload_does_not_also_write_the_standalone_table(
        self, client, scoped, fake_storage, fake_extractor, stub_transcriber, background_db
    ):
        seed(scoped, registry=[registry_row()])
        client.mock_supabase.set_table_data("matricula_extracoes", [])

        client.post("/api/matriculas/extrair", files=_PDF, data={"codigo": CODIGO})

        assert scoped.table("matricula_extracao_arquivos").inserted_payloads == []
        payload = client.mock_supabase.table("matricula_extracoes").inserted_payloads[-1]
        assert "arquivo_origem_id" not in payload


# ─── POST /api/matriculas/extracoes/{id}/retranscrever ─────────────────────


@pytest.mark.usefixtures("com_credencial")
class TestRetranscreverLinked:
    def test_supersedes_never_rewrites(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        doc = documento_row()
        anterior = extracao_row(imovel_documento_id=doc["id"], codigo=CODIGO)
        seed(scoped, registry=[registry_row()], documentos=[doc], extracoes=[anterior])
        _guardar(fake_storage, BUCKET, doc["storage_path"])

        nova = _data(client.post(f"/api/matriculas/extracoes/{anterior['id']}/retranscrever"))

        assert nova["id"] != anterior["id"]
        assert nova["status"] == "pendente"
        assert nova["codigo"] == CODIGO
        assert nova["imovel_documento_id"] == doc["id"]

        # The OLD row's only update is the supersede pointer — never a
        # second write to texto_extraido (the write-once trigger's job,
        # never fought here).
        atualizacoes_antiga = [
            u for u in scoped.table("matricula_extracoes").updated_payloads
            if set(u.keys()) - {"substituida_por"} == set()
        ]
        assert {"substituida_por": nova["id"]} in atualizacoes_antiga
        for u in scoped.table("matricula_extracoes").updated_payloads:
            assert "texto_extraido" not in u

        # The background pipeline ran off the RETAINED source, landing on
        # the NEW row's id.
        assert stub_transcriber.calls == 1
        assert background_db.updates[-1]["status"] == "concluida"
        assert background_db.update_predicates[-1] == [
            ("id", nova["id"]), ("org_id", ORG_ID)
        ]


@pytest.mark.usefixtures("com_credencial")
class TestRetranscreverStandalone:
    def test_reads_from_the_retained_standalone_file(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        arquivo = arquivo_row()
        anterior = extracao_row(codigo=None, arquivo_origem_id=arquivo["id"])
        seed(scoped, extracoes=[anterior], arquivos=[arquivo])
        _guardar(fake_storage, BUCKET, arquivo["storage_path"])

        nova = _data(client.post(f"/api/matriculas/extracoes/{anterior['id']}/retranscrever"))

        assert nova["codigo"] is None
        assert nova["arquivo_origem_id"] == arquivo["id"]
        assert stub_transcriber.calls == 1
        assert background_db.updates[-1]["status"] == "concluida"


@pytest.mark.usefixtures("com_credencial")
class TestRetranscreverRefusals:
    def test_a_non_concluded_extraction_is_a_409(self, client, scoped):
        anterior = extracao_row(status="processando", codigo=None)
        seed(scoped, extracoes=[anterior])

        resp = client.post(f"/api/matriculas/extracoes/{anterior['id']}/retranscrever")
        assert resp.status_code == 409

    def test_an_already_superseded_extraction_is_a_409(self, client, scoped):
        anterior = extracao_row(codigo=None, substituida_por="already-new-one")
        seed(scoped, extracoes=[anterior])

        resp = client.post(f"/api/matriculas/extracoes/{anterior['id']}/retranscrever")
        assert resp.status_code == 409

    def test_a_pre_135_row_with_no_retained_source_is_a_409_naming_the_reason(
        self, client, scoped
    ):
        anterior = extracao_row(codigo=None)  # no imovel_documento_id, no arquivo_origem_id
        seed(scoped, extracoes=[anterior])

        resp = client.post(f"/api/matriculas/extracoes/{anterior['id']}/retranscrever")
        assert resp.status_code == 409
        assert "PDF de origem" in resp.json()["error"]["message"]


# ─── GET /api/matriculas/extracoes/{id}/arquivo-original ───────────────────


class TestArquivoOriginalRoute:
    def test_linked_extraction_returns_a_signed_url_for_the_imovel_document(
        self, client, scoped, fake_storage
    ):
        doc = documento_row()
        extracao = extracao_row(imovel_documento_id=doc["id"], codigo=CODIGO)
        seed(scoped, registry=[registry_row()], documentos=[doc], extracoes=[extracao])
        _guardar(fake_storage, BUCKET, doc["storage_path"])

        data = _data(client.get(f"/api/matriculas/extracoes/{extracao['id']}/arquivo-original"))
        assert "url" in data and "expires_at" in data

    def test_standalone_extraction_returns_a_signed_url_and_logs_the_access(
        self, client, scoped, fake_storage
    ):
        arquivo = arquivo_row()
        extracao = extracao_row(codigo=None, arquivo_origem_id=arquivo["id"])
        seed(scoped, extracoes=[extracao], arquivos=[arquivo])
        _guardar(fake_storage, BUCKET, arquivo["storage_path"])

        data = _data(client.get(f"/api/matriculas/extracoes/{extracao['id']}/arquivo-original"))
        assert "url" in data

        acessos = scoped.table("imovel_documento_acessos").inserted_payloads
        assert any(
            a.get("extracao_id") == extracao["id"] and a.get("acao") == "view"
            for a in acessos
        )

    def test_no_retained_source_is_a_409(self, client, scoped):
        extracao = extracao_row(codigo=None)
        seed(scoped, extracoes=[extracao])

        resp = client.get(f"/api/matriculas/extracoes/{extracao['id']}/arquivo-original")
        assert resp.status_code == 409


# ─── arquivos_service — the DocumentoStore configuration itself ────────────


class TestArquivosService:
    def test_guardar_stamps_the_matricula_retention_policy(self, scoped, fake_storage):
        row = asyncio.run(
            arquivos_svc.guardar(
                scoped, fake_storage, __import__("uuid").UUID(ORG_ID),
                filename="m.pdf", content_type="application/pdf",
                data=_PDF_BYTES, enviado_por=None,
            )
        )
        assert row["tipo_documento"] == "matricula"
        assert row["org_id"] == ORG_ID
