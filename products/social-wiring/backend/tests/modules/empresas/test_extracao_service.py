"""`empresas.extracao_service.extrair_cartao` — lesson G6 (2026-09-28,
verified by an audit against origin/dev): this used to stamp
`extracao_status='ok'` BEFORE calling `dados_service.aplicar_cartao`, with
NO `try` around the apply at all. A transient DB error there left the
document `ok` with the group never actually applied and nothing to retry
(the sweep never revisits an `ok` row).

Now built on the shared `app.services.extracao_job` runner. These tests
force a REAL apply failure — the empresa row goes missing between upload
and this job running (`dados_service.aplicar_cartao`'s own `ensure_empresa`
raises `NotFoundError`, the FIRST thing it does) — a genuine race, not a
monkeypatch of this product's own code, standing in for any apply-time
failure the lesson protects against.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.empresas import extracao_service
from noctusai_lib.integrations.documents.cartao_cnpj import (
    CartaoCnpjFields,
    FakeCartaoCnpjExtractor,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.empresas.conftest import ORG_ID, documento_row, empresa_row

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)
CNPJ_VALIDO = "11222333000181"


def _leitura(**over) -> CartaoCnpjFields:
    base = dict(
        cnpj=CNPJ_VALIDO, cnpj_valido=True, razao_social="EMPRESA LIDA LTDA",
        situacao_cadastral="ativa",
        confiancas={"razao_social": ExtractionConfidence.ALTA},
        source=TextSource.TEXT_LAYER,
    )
    base.update(over)
    return CartaoCnpjFields(**base)


async def _setup(scoped) -> tuple[str, str, FakeStorageBackend]:
    empresa_id, doc_id = str(uuid4()), str(uuid4())
    scoped.set_table_data(
        "empresas",
        [empresa_row(empresa_id, cnpj=CNPJ_VALIDO, razao_social=None, situacao_cadastral=None)],
    )
    path = f"{ORG_ID}/empresas/{empresa_id}/{doc_id}"
    scoped.set_table_data(
        "empresa_documentos",
        [documento_row(doc_id, empresa_id, storage_path=path, extracao_status="pendente")],
    )
    scoped.set_table_data("empresa_documento_acessos", [])
    scoped.set_table_data("empresa_campo_conflitos", [])
    storage = FakeStorageBackend()
    await storage.put(bucket=BUCKET, key=path, data=b"%PDF-1.4 fake", content_type="application/pdf")
    return empresa_id, doc_id, storage


def _documento(scoped, doc_id) -> dict:
    return [
        r for r in scoped.table("empresa_documentos").select("*").execute().data
        if r["id"] == doc_id
    ][0]


def _empresa(scoped, empresa_id) -> dict:
    return [
        r for r in scoped.table("empresas").select("*").execute().data
        if r["id"] == empresa_id
    ][0]


class TestG6NeverAFalseOkOnApplyFailure:
    @pytest.mark.asyncio
    async def test_apply_failure_ends_in_erro_with_the_reading_already_persisted(
        self, client, scoped,
    ):
        empresa_id, doc_id, storage = await _setup(scoped)
        # The empresa vanished between upload and this job running (a race
        # `ensure_empresa` refuses outright) — a REAL exception out of
        # `dados_service.aplicar_cartao`'s apply step, standing in for the
        # transient DB error lesson G6 protects against.
        scoped.set_table_data("empresas", [])

        out = await extracao_service.extrair_cartao(
            scoped, storage, ORG_UUID, UUID(empresa_id), UUID(doc_id),
            extractor=FakeCartaoCnpjExtractor(result=_leitura()),
        )
        assert out["status"] == "erro"
        assert out["erro"] == "aplicar_leitura"

        doc = _documento(scoped, doc_id)
        assert doc["extracao_status"] == "erro"
        assert "aplicar_leitura" in doc["extracao_erro"]
        # The reading is NOT lost — persisted BEFORE the failing apply, so
        # the failure is diagnosable without re-reading the document. This
        # is the exact bug lesson G6 names: the OLD code stamped `ok` here
        # and only THEN called the apply step with no `try` at all.
        assert doc["extracao_dados"] is not None
        assert doc["extracao_dados"]["razao_social"] == "EMPRESA LIDA LTDA"

    @pytest.mark.asyncio
    async def test_a_successful_apply_writes_ok_only_after_the_apply_runs(
        self, client, scoped,
    ):
        empresa_id, doc_id, storage = await _setup(scoped)
        out = await extracao_service.extrair_cartao(
            scoped, storage, ORG_UUID, UUID(empresa_id), UUID(doc_id),
            extractor=FakeCartaoCnpjExtractor(result=_leitura()),
        )
        assert out["status"] == "ok"
        assert _documento(scoped, doc_id)["extracao_status"] == "ok"
        empresa = _empresa(scoped, empresa_id)
        assert empresa["razao_social"] == "EMPRESA LIDA LTDA"
        assert empresa["situacao_cadastral"] == "ativa"
