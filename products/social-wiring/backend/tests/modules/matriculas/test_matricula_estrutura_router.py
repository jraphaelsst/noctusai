"""The structured-matrícula routes (migration 109), through HTTP.

The upload and de-documento routes exist for their SIDE EFFECTS (a kept PDF,
a linked row, a transcription, persisted acts, the imóvel's número read), so
each is asserted on what it wrote — a 200 alone proves nothing.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.modules.imovel_hub.deps import BUCKET
from tests.modules.matriculas.conftest import (
    CODIGO,
    ESPERADOS,
    ORG_ID,
    TEXTO,
    contrato_row,
    documento_row,
    extracao_row,
    registry_row,
    seed,
    transcricao,
)

_PDF_BYTES = b"%PDF-1.4 matricula sintetica"
_PDF = {"file": ("matricula.pdf", _PDF_BYTES, "application/pdf")}


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _guardar(fake_storage, doc: dict) -> None:
    asyncio.run(
        fake_storage.put(
            bucket=BUCKET,
            key=doc["storage_path"],
            data=_PDF_BYTES,
            content_type="application/pdf",
        )
    )


# ─── POST /api/matriculas/extrair with codigo ─────────────────────────────


@pytest.mark.usefixtures("com_credencial")
class TestUploadLinkedToAnImovel:
    def test_the_pdf_is_kept_as_the_imovels_document_and_linked(
        self, client, scoped, fake_storage, fake_extractor, stub_transcriber, background_db
    ):
        seed(scoped, registry=[registry_row()])
        client.mock_supabase.set_table_data("matricula_extracoes", [])

        _data(client.post("/api/matriculas/extrair", files=_PDF, data={"codigo": "ap1234"}))

        docs = scoped.table("imovel_documentos").inserted_payloads
        assert len(docs) == 1 and docs[0]["tipo_documento"] == "matricula"
        blob = asyncio.run(fake_storage.get(bucket=BUCKET, key=docs[0]["storage_path"]))
        assert blob is not None and blob.data == _PDF_BYTES

        payload = client.mock_supabase.table("matricula_extracoes").inserted_payloads[-1]
        assert payload["codigo"] == CODIGO
        assert payload["imovel_documento_id"] == docs[0]["id"]
        assert "org_id" not in payload, "org must come from the DB default"

    def test_the_transcription_persists_text_and_acts(
        self, client, scoped, fake_storage, fake_extractor, stub_transcriber, background_db
    ):
        seed(scoped, registry=[registry_row()])
        client.mock_supabase.set_table_data("matricula_extracoes", [])

        client.post("/api/matriculas/extrair", files=_PDF, data={"codigo": CODIGO})

        texto = transcricao(TEXTO).text
        assert [u["status"] for u in background_db.updates] == ["processando", "concluida"]
        assert background_db.updates[-1]["texto_extraido"] == texto
        atos = background_db.inserts["matricula_atos"]
        assert [(a["kind"], a["numero"]) for a in atos] == ESPERADOS
        assert "".join(texto[a["char_inicio"] : a["char_fim"]] for a in atos) == texto

    def test_the_imovels_numero_read_is_queued_too(
        self, client, scoped, fake_storage, fake_extractor, stub_transcriber, background_db
    ):
        seed(scoped, registry=[registry_row()])
        client.mock_supabase.set_table_data("matricula_extracoes", [])

        client.post("/api/matriculas/extrair", files=_PDF, data={"codigo": CODIGO})

        itens = client.get(f"/api/imoveis/{CODIGO}/documentos").json()["items"]
        assert itens[0]["extracao_status"] == "ok"
        assert itens[0]["extracao_matricula"] == fake_extractor.NUMERO

    def test_an_unknown_imovel_is_a_404_and_writes_nothing(
        self, client, scoped, fake_storage, fake_extractor, stub_transcriber, background_db
    ):
        seed(scoped, registry=[])
        client.mock_supabase.set_table_data("matricula_extracoes", [])

        resp = client.post("/api/matriculas/extrair", files=_PDF, data={"codigo": "NOPE9"})

        assert resp.status_code == 404
        assert client.mock_supabase.table("matricula_extracoes").inserted_payloads == []
        assert background_db.updates == []

    def test_without_codigo_no_imovel_link_is_written(
        self, client, scoped, fake_storage, fake_extractor, stub_transcriber, background_db
    ):
        """The unlinked shape stays unlinked — no `codigo` / imóvel document.
        It no longer discards the bytes though (migration 135); that's
        covered in `test_retranscricao.py::TestStandaloneUploadRetainsTheSource`.
        """
        seed(scoped, registry=[registry_row()])
        client.mock_supabase.set_table_data("matricula_extracoes", [])

        _data(client.post("/api/matriculas/extrair", files=_PDF))

        payload = client.mock_supabase.table("matricula_extracoes").inserted_payloads[-1]
        assert "codigo" not in payload and "imovel_documento_id" not in payload
        assert scoped.table("imovel_documentos").inserted_payloads == []


# ─── POST /api/matriculas/extracoes/de-documento ──────────────────────────


@pytest.mark.usefixtures("com_credencial")
class TestTranscribeAnImovelsStoredMatricula:
    def _post(self, client, doc):
        return client.post(
            "/api/matriculas/extracoes/de-documento",
            json={"codigo": CODIGO.lower(), "imovel_documento_id": doc["id"]},
        )

    def test_reads_the_stored_pdf_and_persists_text_and_acts(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        doc = documento_row()
        seed(scoped, registry=[registry_row()], documentos=[doc])
        _guardar(fake_storage, doc)

        data = _data(self._post(client, doc))

        assert data["codigo"] == CODIGO
        assert data["imovel_documento_id"] == doc["id"]
        assert data["status"] == "pendente"
        assert "storage_path" not in data
        inserida = scoped.table("matricula_extracoes").inserted_payloads[-1]
        assert inserida["org_id"] == ORG_ID

        assert stub_transcriber.calls == 1
        assert background_db.updates[-1]["status"] == "concluida"
        assert len(background_db.inserts["matricula_atos"]) == len(ESPERADOS)
        for preds in background_db.update_predicates:
            assert ("org_id", ORG_ID) in preds, "a service-role write must be org-scoped"

    def test_a_missing_stored_object_is_recorded_as_erro(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        doc = documento_row()
        seed(scoped, registry=[registry_row()], documentos=[doc])

        _data(self._post(client, doc))

        assert stub_transcriber.calls == 0
        assert background_db.updates[-1]["status"] == "erro"
        assert "não foi encontrado" in background_db.updates[-1]["erro_mensagem"]

    def test_a_second_transcription_of_the_same_document_is_a_409(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        doc = documento_row()
        seed(
            scoped,
            registry=[registry_row()],
            documentos=[doc],
            extracoes=[extracao_row(imovel_documento_id=doc["id"])],
        )

        assert self._post(client, doc).status_code == 409
        assert stub_transcriber.calls == 0

    def test_a_failed_transcription_does_not_block_a_retry(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        doc = documento_row()
        seed(
            scoped,
            registry=[registry_row()],
            documentos=[doc],
            extracoes=[extracao_row(imovel_documento_id=doc["id"], status="erro")],
        )
        _guardar(fake_storage, doc)

        _data(self._post(client, doc))

    # House convention: a domain refusal (`ValidationError_`) is a 400; 422 is
    # reserved for a request body that fails its schema.
    def test_a_non_matricula_document_is_a_400(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        doc = documento_row(tipo_documento="guia_iptu")
        seed(scoped, registry=[registry_row()], documentos=[doc])

        assert self._post(client, doc).status_code == 400
        assert stub_transcriber.calls == 0

    def test_a_photographed_matricula_is_a_400(
        self, client, scoped, fake_storage, stub_transcriber, background_db
    ):
        doc = documento_row(mime_type="image/jpeg")
        seed(scoped, registry=[registry_row()], documentos=[doc])

        assert self._post(client, doc).status_code == 400
        assert stub_transcriber.calls == 0


# ─── GET atos / GET+PUT fontes ────────────────────────────────────────────


class TestActsAndSources:
    def test_the_acts_are_literal_slices(self, client, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])

        data = _data(client.get(f"/api/matriculas/extracoes/{ext['id']}/atos"))

        assert data["total"] == len(ESPERADOS)
        assert "".join(a["texto"] for a in data["atos"]) == TEXTO

    def test_an_unknown_extraction_is_a_404(self, client, scoped):
        seed(scoped)
        resp = client.get(f"/api/matriculas/extracoes/{uuid4()}/atos")
        assert resp.status_code == 404

    def test_confirming_a_source_lands_on_the_imovel(self, client, scoped):
        ext = extracao_row()
        seed(scoped, registry=[registry_row()], extracoes=[ext])
        base = f"/api/matriculas/extracoes/{ext['id']}/fontes"

        sugerido = _data(client.get(base))["sugestoes"]["titulo_aquisitivo"]
        assert sugerido["numero"] == 4

        titulo = _data(
            client.put(base, json={"titulo_aquisitivo_ato_id": sugerido["ato_id"]})
        )["titulo_aquisitivo"]
        assert titulo["origem"] == "sugerido"
        assert titulo["texto"] == TEXTO[titulo["char_inicio"] : titulo["char_fim"]]

        dados = client.get(f"/api/imoveis/{CODIGO}/dados").json()
        assert dados["titulo_aquisitivo_fonte"]["ato_id"] == sugerido["ato_id"]
        assert dados["onus_fonte"] is None

    def test_an_authored_field_is_not_accepted_on_the_fontes_route(self, client, scoped):
        ext = extracao_row()
        seed(scoped, registry=[registry_row()], extracoes=[ext])

        resp = client.put(
            f"/api/matriculas/extracoes/{ext['id']}/fontes",
            json={"situacao_onus": "livre"},
        )
        assert resp.status_code == 422


# ─── GET+PUT contratos/{id}/atos ──────────────────────────────────────────


class TestContractQuote:
    def _seed(self, client, scoped):
        ext = extracao_row()
        contrato = contrato_row()
        seed(scoped, extracoes=[ext], contratos=[contrato])
        atos = _data(client.get(f"/api/matriculas/extracoes/{ext['id']}/atos"))["atos"]
        return ext, contrato, atos

    def test_put_then_get_is_byte_identical(self, client, scoped):
        ext, contrato, atos = self._seed(client, scoped)
        url = f"/api/matriculas/contratos/{contrato['id']}/atos"

        _data(client.put(url, json={"extracao_id": ext["id"], "ato_ids": [a["id"] for a in atos]}))
        data = _data(client.get(url))

        assert data["texto"].encode("utf-8") == TEXTO.encode("utf-8")
        assert data["extracao_id"] == ext["id"]
        assert data["codigo"] == CODIGO

    def test_a_subset_in_operator_order(self, client, scoped):
        ext, contrato, atos = self._seed(client, scoped)
        escolha = [atos[4], atos[0]]

        data = _data(
            client.put(
                f"/api/matriculas/contratos/{contrato['id']}/atos",
                json={"extracao_id": ext["id"], "ato_ids": [a["id"] for a in escolha]},
            )
        )

        assert data["texto"] == escolha[0]["texto"] + escolha[1]["texto"]

    def test_an_act_of_another_matricula_is_a_400(self, client, scoped):
        ext, contrato, _atos = self._seed(client, scoped)
        resp = client.put(
            f"/api/matriculas/contratos/{contrato['id']}/atos",
            json={"extracao_id": ext["id"], "ato_ids": [str(uuid4())]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["message"].startswith("Atos não pertencem")

    def test_an_unknown_contract_is_a_404(self, client, scoped):
        seed(scoped)
        resp = client.get(f"/api/matriculas/contratos/{uuid4()}/atos")
        assert resp.status_code == 404


# ─── delete guard + list filter + LGPD log ────────────────────────────────


class TestDeleteListAndAccessLog:
    def test_a_quoted_extraction_cannot_be_deleted(self, client, scoped):
        seed(
            scoped,
            selecao=[
                {
                    "id": str(uuid4()),
                    "org_id": ORG_ID,
                    "contrato_id": str(uuid4()),
                    "extracao_id": "ext-001",
                    "ato_id": str(uuid4()),
                    "ordem": 1,
                }
            ],
        )
        client.mock_supabase.set_table_data(
            "matricula_extracoes", [extracao_row("ext-001")]
        )

        resp = client.delete("/api/matriculas/extracoes/ext-001")

        assert resp.status_code == 409

    def test_the_history_narrows_to_one_imovel(self, client, scoped):
        client.mock_supabase.set_table_data(
            "matricula_extracoes",
            [
                extracao_row(codigo=CODIGO),
                extracao_row(codigo="OUTRO1"),
                extracao_row(codigo=None),
            ],
        )

        resp = client.get("/api/matriculas/extracoes?codigo=ap1234")

        assert resp.status_code == 200
        assert [r["codigo"] for r in resp.json()["data"]] == [CODIGO]

    def test_opening_an_imovels_pdf_is_logged_with_who_opened_it(
        self, client, scoped, fake_storage
    ):
        doc = documento_row()
        seed(scoped, registry=[registry_row()], documentos=[doc])
        _guardar(fake_storage, doc)

        resp = client.get(f"/api/imoveis/{CODIGO}/documentos/{doc['id']}/url")

        assert resp.status_code == 200, resp.text
        log = scoped.table("imovel_documento_acessos").inserted_payloads
        assert len(log) == 1
        assert log[0]["acao"] == "view"
        assert log[0]["documento_id"] == doc["id"]
        assert log[0]["usuario_id"], "a content read must name who opened it"


class TestTextReadsAreLogged:
    """Migration 111: three routes hand back CPF-bearing text with no PDF
    read behind them — each must append a `text_view` row, keyed to the
    extraction (not a document, which may not exist for an unlinked upload)."""

    def _seed(self, scoped, *, codigo=CODIGO):
        ext = extracao_row(codigo=codigo)
        contrato = contrato_row()
        seed(scoped, extracoes=[ext], contratos=[contrato])
        return ext, contrato

    def test_getting_one_extracao_logs_a_text_view(self, client, scoped):
        # `GET /extracoes/{id}` is a LEGACY route — it reads through the
        # caller's own token (`get_user_client`), not the service-role
        # `scoped` client the structured (109) routes use. Seeded on
        # `client.mock_supabase`, same as `test_the_history_narrows_to_one_
        # imovel` below. The LOG write still lands on `scoped` — the route
        # logs through `get_matriculas_client` regardless of which client it
        # read the row with.
        ext, _contrato = self._seed(scoped)
        client.mock_supabase.set_table_data("matricula_extracoes", [ext])

        resp = client.get(f"/api/matriculas/extracoes/{ext['id']}")

        assert resp.status_code == 200, resp.text
        log = scoped.table("imovel_documento_acessos").inserted_payloads
        assert len(log) == 1
        assert log[0]["acao"] == "text_view"
        assert log[0]["extracao_id"] == ext["id"]
        assert log[0]["documento_id"] is None
        assert log[0]["usuario_id"], "a content read must name who opened it"

    def test_listing_atos_logs_a_text_view(self, client, scoped):
        ext, _contrato = self._seed(scoped)

        resp = client.get(f"/api/matriculas/extracoes/{ext['id']}/atos")

        assert resp.status_code == 200, resp.text
        log = scoped.table("imovel_documento_acessos").inserted_payloads
        assert len(log) == 1
        assert log[0]["acao"] == "text_view"
        assert log[0]["extracao_id"] == ext["id"]

    def test_getting_the_contract_selection_logs_a_text_view(self, client, scoped):
        ext, contrato = self._seed(scoped)
        atos = _data(client.get(f"/api/matriculas/extracoes/{ext['id']}/atos"))["atos"]
        client.put(
            f"/api/matriculas/contratos/{contrato['id']}/atos",
            json={"extracao_id": ext["id"], "ato_ids": [a["id"] for a in atos]},
        )
        # The PUT above already logged (it returns the same quoted text) —
        # only the GET's own row is under test here.
        scoped.set_table_data("imovel_documento_acessos", [])

        resp = client.get(f"/api/matriculas/contratos/{contrato['id']}/atos")

        assert resp.status_code == 200, resp.text
        log = scoped.table("imovel_documento_acessos").inserted_payloads
        assert len(log) == 1
        assert log[0]["acao"] == "text_view"
        assert log[0]["extracao_id"] == ext["id"]

    def test_an_empty_contract_selection_logs_nothing(self, client, scoped):
        """No acts selected -> no text is returned -> nothing to log."""
        _ext, contrato = self._seed(scoped)

        resp = client.get(f"/api/matriculas/contratos/{contrato['id']}/atos")

        assert resp.status_code == 200, resp.text
        assert scoped.table("imovel_documento_acessos").inserted_payloads == []
