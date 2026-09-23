"""NOC-REMEDIATE[matricula-pipeline-consolidation] (partial, 2026-09-23):
the imóvel-page matrícula upload now reaches the SAME transcription
pipeline `POST /api/matriculas/extrair` (with a `codigo`) and
`POST /api/matriculas/extracoes/de-documento` reach — cartório, inscrição,
situação de ônus, atos and título suggestions — not just the
número-de-matrícula read `test_imovel_documentos.py` already pins.

Live-verified gap this closes: an imóvel-page upload of a matrícula PDF used
to leave `imovel_dados` with only `numero_matricula` filled; uploading the
SAME PDF through `/api/matriculas` with the imóvel's código filled all four
(cartório, inscrição, situação de ônus, and the acts/título suggestions).
"""
from __future__ import annotations

import pytest

from tests.modules.imovel_hub.conftest import CODIGO, ORG_ID, auth, registry_row, seed
from tests.modules.matriculas.conftest import ESPERADOS, TEXTO, transcricao
from tests.modules.matriculas.conftest import background_db  # noqa: F401 - fixture chain
from tests.modules.matriculas.conftest import com_credencial  # noqa: F401 - fixture chain
from tests.modules.matriculas.conftest import stub_transcriber  # noqa: F401 - fixture chain

_PDF_BYTES = b"%PDF-1.4 matricula sintetica do imovel"
_PDF = ("matricula.pdf", _PDF_BYTES, "application/pdf")


def _upload(client, *, tipo="matricula", arquivo=_PDF):
    return client.post(
        f"/api/imoveis/{CODIGO}/documentos",
        files={"file": arquivo},
        data={"tipo_documento": tipo},
        headers=auth(),
    )


@pytest.mark.usefixtures("com_credencial")
class TestImovelPageUploadQueuesTheFullTranscription:
    def test_the_upload_creates_a_pendente_matricula_extracao_linked_to_the_document(
        self,
        client,
        scoped,
        fake_storage,
        fake_extractor,
        stub_transcriber,
        background_db,
    ):
        seed(scoped, registry=[registry_row()])
        scoped.set_table_data("matricula_extracoes", [])

        r = _upload(client)
        assert r.status_code == 200, r.text
        documento = r.json()

        payload = scoped.table("matricula_extracoes").inserted_payloads[-1]
        assert payload["codigo"] == CODIGO
        assert payload["imovel_documento_id"] == documento["id"]
        assert payload["status"] == "pendente"
        # `criar_extracao_de_documento` (the SAME call `/extracoes/de-
        # documento` makes) stamps `org_id` explicitly from Python — unlike
        # `/extrair`'s standalone INSERT, which relies on the DB default.
        assert payload["org_id"] == ORG_ID

    def test_the_transcription_runs_and_persists_text_and_acts(
        self,
        client,
        scoped,
        fake_storage,
        fake_extractor,
        stub_transcriber,
        background_db,
    ):
        seed(scoped, registry=[registry_row()])
        scoped.set_table_data("matricula_extracoes", [])

        _upload(client)

        texto = transcricao(TEXTO).text
        assert [u["status"] for u in background_db.updates] == [
            "processando",
            "concluida",
        ]
        assert background_db.updates[-1]["texto_extraido"] == texto
        atos = background_db.inserts["matricula_atos"]
        assert [(a["kind"], a["numero"]) for a in atos] == ESPERADOS

    def test_the_numero_de_matricula_job_still_runs_alongside_it(
        self,
        client,
        scoped,
        fake_storage,
        fake_extractor,
        stub_transcriber,
        background_db,
    ):
        """The pre-existing job (`test_imovel_documentos.py`'s own coverage)
        must not regress — the imóvel page now schedules THREE jobs off one
        upload, not a replacement of the other two."""
        seed(scoped, registry=[registry_row()])
        scoped.set_table_data("matricula_extracoes", [])

        r = _upload(client)
        documento = r.json()
        assert documento["extracao_status"] == "pendente"

    def test_a_non_pdf_matricula_upload_still_succeeds_but_queues_no_transcription(
        self,
        client,
        scoped,
        fake_storage,
        fake_extractor,
        stub_transcriber,
        background_db,
    ):
        """`criar_extracao_de_documento` only accepts
        `mime_type == 'application/pdf'` — a scanned JPEG (this route's
        other allowed mime type) must not fail the upload; it must just skip
        the full transcription."""
        seed(scoped, registry=[registry_row()])
        scoped.set_table_data("matricula_extracoes", [])

        r = _upload(client, arquivo=("matricula.jpg", b"\xff\xd8\xff fake jpeg", "image/jpeg"))
        assert r.status_code == 200, r.text

        assert scoped.table("matricula_extracoes").inserted_payloads == []

    def test_a_guia_iptu_upload_is_never_queued_for_the_matricula_transcription(
        self,
        client,
        scoped,
        fake_storage,
        fake_extractor,
        stub_transcriber,
        background_db,
    ):
        seed(scoped, registry=[registry_row()])
        scoped.set_table_data("matricula_extracoes", [])

        r = _upload(client, tipo="guia_iptu", arquivo=("guia.pdf", _PDF_BYTES, "application/pdf"))
        assert r.status_code == 200, r.text

        assert scoped.table("matricula_extracoes").inserted_payloads == []
