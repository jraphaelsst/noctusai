"""Imóvel documents + the matrícula read that feeds `numero_matricula`.

THE FEATURE IN ONE SENTENCE
--------------------------
Upload a matrícula, and the número de matrícula fills itself in.

WHAT THESE PIN BEYOND THE HAPPY PATH
------------------------------------
- a guia de IPTU is NOT read for a matrícula number (it carries an inscrição
  imobiliária — a different number that would be wrong in this column);
- a low-confidence read is RECORDED but NOT written to the record;
- a number a human already typed is never overwritten by a read;
- every failure ends in a recorded `extracao_status`, because this job runs
  detached and an exception would surface nowhere;
- deleting the document does NOT erase the number it produced.

Auth is not re-tested here — `test_auth_boundary.py` covers every route.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    MatriculaFields,
    TextSource,
)
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.imovel_hub import documentos_service
from app.modules.imovel_hub import matricula_extracao_service as extracao
from tests.modules.imovel_hub.conftest import (
    CODIGO,
    ORG_ID,
    auth,
    dados_row,
    documento_row,
    seed,
)

PDF = ("matricula.pdf", b"%PDF-1.7 fake", "application/pdf")


def _upload(client, *, tipo="matricula", arquivo=PDF):
    return client.post(
        f"/api/imoveis/{CODIGO}/documentos",
        files={"file": arquivo},
        data={"tipo_documento": tipo},
        headers=auth(),
    )


class TestUpload:
    def test_a_matricula_uploads_and_is_queued_for_reading(
        self, client, scoped, fake_storage, fake_extractor
    ):
        seed(scoped)
        r = _upload(client)
        assert r.status_code == 200
        body = r.json()
        assert body["tipo_documento"] == "matricula"
        # 🔴 Stamped at UPLOAD time, not by the job. A job that never starts
        # is then visibly waiting instead of invisibly lost.
        assert body["extracao_status"] == "pendente"

    def test_a_guia_iptu_uploads_but_is_never_queued(
        self, client, scoped, fake_storage, fake_extractor
    ):
        """🔴 It carries an inscrição imobiliária, not a matrícula number.

        Reading one into `numero_matricula` would be confidently wrong.
        """
        seed(scoped)
        body = _upload(client, tipo="guia_iptu").json()
        assert body["tipo_documento"] == "guia_iptu"
        assert body["extracao_status"] is None

    def test_an_unknown_type_is_refused_by_name(
        self, client, scoped, fake_storage, fake_extractor
    ):
        seed(scoped)
        r = _upload(client, tipo="escritura")
        # 400, not 422: this is a service-level `ValidationError_` (the type
        # is well-formed input that names a type we do not accept), not a
        # schema rejection. Pydantic's 422 is reserved for a malformed body.
        assert r.status_code == 400
        assert "escritura" in r.text

    def test_an_unknown_imovel_is_a_404(
        self, client, scoped, fake_storage, fake_extractor
    ):
        seed(scoped)
        r = client.post(
            "/api/imoveis/NOPE9999/documentos",
            files={"file": PDF},
            data={"tipo_documento": "matricula"},
            headers=auth(),
        )
        assert r.status_code == 404

    def test_a_disallowed_mime_type_names_the_limit(
        self, client, scoped, fake_storage, fake_extractor
    ):
        seed(scoped)
        r = _upload(client, arquivo=("m.exe", b"MZ", "application/x-msdownload"))
        assert r.status_code == 400
        assert "application/x-msdownload" in r.text

    def test_an_oversized_file_names_the_limit_in_megabytes(self):
        """The message must carry a real number — see `_format_bytes_human`
        for the incident where it integer-divided to a misleading "0MB".

        🔴 Driven through `validar_upload`'s `max_bytes` seam, NOT by
        monkeypatching `MAX_UPLOAD_BYTES`. Patching the constant would mean
        this test exercises a guard it invented rather than the one the
        product runs — and a compliance keeper flags exactly that.
        """
        with pytest.raises(ValidationError_) as exc:
            documentos_service.validar_upload(
                tipo_documento="matricula",
                content_type="application/pdf",
                tamanho_bytes=50,
                max_bytes=10,
            )
        msg = str(exc.value)
        assert "0MB" not in msg
        assert "KB" in msg or "MB" in msg

    def test_the_real_ceiling_is_reported_in_whole_megabytes(self):
        """At the production limit the message reads in MB, not a raw count."""
        with pytest.raises(ValidationError_) as exc:
            documentos_service.validar_upload(
                tipo_documento="matricula",
                content_type="application/pdf",
                tamanho_bytes=documentos_service.MAX_UPLOAD_BYTES + 1,
            )
        assert "40.0MB" in str(exc.value)


class TestListingAndRemoval:
    def test_listing_returns_the_house_envelope(self, client, scoped):
        seed(scoped, documentos=[documento_row(str(uuid4()))])
        body = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

    def test_a_soft_deleted_document_is_not_listed(self, client, scoped):
        seed(
            scoped,
            documentos=[
                documento_row(str(uuid4()), deleted_at="2026-02-01T00:00:00+00:00")
            ],
        )
        body = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert body["total"] == 0

    def test_delete_requires_a_motivo(self, client, scoped):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did)])
        r = client.delete(
            f"/api/imoveis/{CODIGO}/documentos/{did}", headers=auth()
        )
        assert r.status_code == 422

    def test_delete_soft_deletes(self, client, scoped):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did)])
        r = client.delete(
            f"/api/imoveis/{CODIGO}/documentos/{did}?motivo=arquivo+errado",
            headers=auth(),
        )
        assert r.status_code == 204
        body = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert body["total"] == 0

    def test_deleting_the_document_does_not_erase_the_number_it_produced(
        self, client, scoped
    ):
        """🔴 The number is a FACT about the property; the document is
        evidence. Removing the evidence does not un-know the fact, and
        blanking a field nobody asked to blank loses data silently.
        """
        did = str(uuid4())
        seed(
            scoped,
            documentos=[documento_row(did)],
            dados=[
                dados_row(
                    numero_matricula="12345",
                    numero_matricula_origem="matricula",
                    numero_matricula_documento_id=did,
                )
            ],
        )
        client.delete(
            f"/api/imoveis/{CODIGO}/documentos/{did}?motivo=substituida",
            headers=auth(),
        )
        body = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert body["numero_matricula"] == "12345"
        # Provenance still points at the (soft-deleted) row, so it stays
        # readable rather than becoming an anonymous value.
        assert body["numero_matricula_documento_id"] == did


class _Extractor:
    """Returns a scripted `MatriculaFields`, or raises if asked to."""

    def __init__(self, fields=None, boom=False):
        self._fields = fields
        self._boom = boom
        self.calls = 0

    async def extract(self, content, *, mimetype=None, filename=None):
        self.calls += 1
        if self._boom:
            raise RuntimeError("extractor exploded")
        return self._fields


def _alta(numero="12345"):
    return MatriculaFields(
        numero_matricula=numero,
        numero_matricula_confianca=ExtractionConfidence.ALTA,
        numero_matricula_rotulo="MATRICULA N",
        source=TextSource.TEXT_LAYER,
    )


def _baixa(numero="12345"):
    return MatriculaFields(
        numero_matricula=numero,
        numero_matricula_confianca=ExtractionConfidence.BAIXA,
        numero_matricula_rotulo="MATRICULA N",
        source=TextSource.OCR,
    )


class TestTheExtraction:
    """The user's ask: upload the matrícula, the number fills itself in."""

    @pytest.mark.asyncio
    async def test_a_high_confidence_read_lands_on_the_imovel(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, extracao_status="pendente")])
        await fake_storage.put(
            bucket="social-wiring-documentos",
            key=f"{ORG_ID}/imoveis/{CODIGO}/x",
            data=b"%PDF",
            content_type="application/pdf",
        )
        scoped.set_table_data(
            "imovel_documentos",
            [
                documento_row(
                    did,
                    extracao_status="pendente",
                    storage_path=f"{ORG_ID}/imoveis/{CODIGO}/x",
                )
            ],
        )

        out = await extracao.extrair(
            scoped,
            fake_storage,
            UUID(ORG_ID),
            CODIGO,
            UUID(did),
            extractor=_Extractor(_alta()),
        )
        assert out["status"] == "ok"
        assert out["aplicado_ao_imovel"] is True

        body = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert body["numero_matricula"] == "12345"
        assert body["numero_matricula_origem"] == "matricula"
        # 🔴 A machine read is attributable to a DOCUMENT, never to a person.
        assert body["numero_matricula_confirmado_por"] is None

    @pytest.mark.asyncio
    async def test_a_low_confidence_read_is_recorded_but_not_written(
        self, client, scoped, fake_storage
    ):
        """🔴 The rule that keeps a misread digit out of the registry.

        The read is kept on the DOCUMENT so the UI can offer it, and kept off
        the record so nobody mistakes it for a checked fact.
        """
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(
            scoped,
            documentos=[documento_row(did, extracao_status="pendente", storage_path=path)],
        )
        await fake_storage.put(
            bucket="social-wiring-documentos",
            key=path,
            data=b"%PDF",
            content_type="application/pdf",
        )

        out = await extracao.extrair(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extractor=_Extractor(_baixa()),
        )
        assert out["status"] == "ok"
        assert out["aplicado_ao_imovel"] is False

        dados = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert dados["numero_matricula"] is None

        docs = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert docs["items"][0]["extracao_matricula"] == "12345"
        assert docs["items"][0]["extracao_confianca"] == "baixa"

    @pytest.mark.asyncio
    async def test_a_number_a_human_typed_is_never_overwritten(
        self, client, scoped, fake_storage
    ):
        """🔴 FIRST WRITER WINS, and the check is a re-read, not a flag.

        Minutes can separate the upload from this call, and a human may well
        have typed the number in between. Declining is the correct outcome.
        """
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(
            scoped,
            documentos=[documento_row(did, extracao_status="pendente", storage_path=path)],
            dados=[dados_row(numero_matricula="99887", numero_matricula_origem="manual")],
        )
        await fake_storage.put(
            bucket="social-wiring-documentos", key=path, data=b"%PDF",
            content_type="application/pdf",
        )

        out = await extracao.extrair(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extractor=_Extractor(_alta("12345")),
        )
        assert out["aplicado_ao_imovel"] is False
        dados = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert dados["numero_matricula"] == "99887"
        assert dados["numero_matricula_origem"] == "manual"


class TestEveryFailureIsRecorded:
    """🔴 This job runs detached. An exception here surfaces NOWHERE, and the
    document would sit in `processando` forever with a field that never
    fills. So every path ends in a written status."""

    @pytest.mark.asyncio
    async def test_a_missing_storage_object_is_recorded_not_raised(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        seed(
            scoped,
            documentos=[
                documento_row(did, extracao_status="pendente", storage_path="nope")
            ],
        )
        out = await extracao.extrair(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extractor=_Extractor(_alta()),
        )
        assert out["status"] == "erro"
        docs = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert docs["items"][0]["extracao_status"] == "erro"
        assert docs["items"][0]["extracao_erro"]

    @pytest.mark.asyncio
    async def test_an_extractor_error_field_is_recorded(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(
            scoped,
            documentos=[documento_row(did, extracao_status="pendente", storage_path=path)],
        )
        await fake_storage.put(
            bucket="social-wiring-documentos", key=path, data=b"%PDF",
            content_type="application/pdf",
        )
        fields = MatriculaFields(error="resolver_failed", error_message="vision down")
        out = await extracao.extrair(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extractor=_Extractor(fields),
        )
        assert out["status"] == "erro"
        docs = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert "vision down" in docs["items"][0]["extracao_erro"]

    @pytest.mark.asyncio
    async def test_a_readable_document_with_no_number_is_sem_dados_not_erro(
        self, client, scoped, fake_storage
    ):
        """The distinction that decides whether retrying is worth anything."""
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(
            scoped,
            documentos=[documento_row(did, extracao_status="pendente", storage_path=path)],
        )
        await fake_storage.put(
            bucket="social-wiring-documentos", key=path, data=b"%PDF",
            content_type="application/pdf",
        )
        out = await extracao.extrair(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extractor=_Extractor(MatriculaFields(source=TextSource.TEXT_LAYER)),
        )
        assert out["status"] == "sem_dados"
        docs = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert docs["items"][0]["extracao_status"] == "sem_dados"
        assert docs["items"][0]["extracao_erro"] is None

    @pytest.mark.asyncio
    async def test_a_document_deleted_before_the_job_ran_is_not_read(
        self, scoped, fake_storage
    ):
        """Reading its bytes now would be work on something already withdrawn."""
        did = str(uuid4())
        seed(
            scoped,
            documentos=[
                documento_row(
                    did,
                    extracao_status="pendente",
                    deleted_at="2026-02-01T00:00:00+00:00",
                )
            ],
        )
        extractor = _Extractor(_alta())
        out = await extracao.extrair(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did), extractor=extractor
        )
        assert out["erro"] == "documento_removido"
        assert extractor.calls == 0

    @pytest.mark.asyncio
    async def test_a_guia_iptu_is_refused_even_if_the_job_is_called_directly(
        self, scoped, fake_storage
    ):
        did = str(uuid4())
        seed(
            scoped,
            documentos=[documento_row(did, tipo_documento="guia_iptu")],
        )
        extractor = _Extractor(_alta())
        out = await extracao.extrair(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did), extractor=extractor
        )
        assert out["erro"] == "tipo_nao_extraivel"
        assert extractor.calls == 0
