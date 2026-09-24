"""`empresas.sweep_service.varrer_extracoes_pendentes` — D3, mirroring
`identidade_extracao_service`'s own stalled-extraction recovery sweep
verbatim (P0c contract §C6, item 5 of the P0c integration dispatch).

WHAT THESE PIN
--------------
1. A document stuck `processando`/never-started past `STALE_APOS` is
   recovered — the silent error this sweep exists for: the process died
   between stamping `processando` and writing a terminal status, and
   nothing would ever move it again.
2. A RECENT document is left alone — it may simply still be working;
   racing it would double the bill and could interleave two writers.
3. **Retries are bounded (D3): at most `MAX_TENTATIVAS` STARTS, then a
   terminal, explained `erro`** — a deterministically-broken document must
   stop costing money.
4. A terminal document (`ok`/`sem_dados`/an already-exhausted `erro`) is
   never swept.
5. The attempt counter advances on each read.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.empresas import extracao_service, sweep_service
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


def _old(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _leitura(**over) -> CartaoCnpjFields:
    base = dict(
        cnpj=CNPJ_VALIDO, cnpj_valido=True, razao_social="EMPRESA LIDA LTDA",
        situacao_cadastral="ativa",
        confiancas={"razao_social": ExtractionConfidence.ALTA},
        source=TextSource.TEXT_LAYER,
    )
    base.update(over)
    return CartaoCnpjFields(**base)


async def _setup(scoped, *, doc_extra=None, empresa_extra=None):
    empresa_id, doc_id = str(uuid4()), str(uuid4())
    over = {"razao_social": None, **(empresa_extra or {})}
    scoped.set_table_data("empresas", [
        empresa_row(empresa_id, cnpj=CNPJ_VALIDO, **over)
    ])
    path = f"{ORG_ID}/empresas/{empresa_id}/{doc_id}"
    row = documento_row(
        doc_id, empresa_id, storage_path=path,
        extracao_status="pendente", extracao_tentativas=0, created_at=_old(30),
    )
    row.update(doc_extra or {})
    scoped.set_table_data("empresa_documentos", [row])
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


class TestStalledExtractionSweep:
    @pytest.mark.asyncio
    async def test_a_document_stuck_in_processando_is_retried(self, client, scoped):
        empresa_id, doc_id, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "processando", "extracao_em": _old(60),
                       "extracao_tentativas": 1},
        )
        result = await sweep_service.varrer_extracoes_pendentes(
            scoped, storage,
            extractor_factory=lambda _org, _tipo=None: FakeCartaoCnpjExtractor(result=_leitura()),
        )
        assert result["encontrados"] == 1
        assert result["retomados"] == 1
        assert _documento(scoped, doc_id)["extracao_status"] == "ok"
        assert _empresa(scoped, empresa_id)["razao_social"] == "EMPRESA LIDA LTDA"

    @pytest.mark.asyncio
    async def test_a_never_started_document_is_recovered(self, client, scoped):
        """The OTHER stranded shape D3 names: `pendente` with no
        `extracao_em` at all — the upload route scheduled the background
        task and the process died before it ever ran."""
        _empresa_id, doc_id, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "pendente", "extracao_em": None,
                       "created_at": _old(30)},
        )
        result = await sweep_service.varrer_extracoes_pendentes(
            scoped, storage,
            extractor_factory=lambda _org, _tipo=None: FakeCartaoCnpjExtractor(result=_leitura()),
        )
        assert result["encontrados"] == 1
        assert result["retomados"] == 1
        assert _documento(scoped, doc_id)["extracao_status"] == "ok"

    @pytest.mark.asyncio
    async def test_a_recent_document_is_left_alone(self, client, scoped):
        """It may simply still be working. Racing it would double the bill
        and could interleave two writers on one row."""
        _empresa_id, _doc_id, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "processando", "extracao_em": _old(1)},
        )
        result = await sweep_service.varrer_extracoes_pendentes(scoped, storage)
        assert result["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_retries_are_bounded(self, client, scoped):
        """A deterministically-broken document must stop costing money."""
        _empresa_id, doc_id, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "processando", "extracao_em": _old(60),
                       "extracao_tentativas": extracao_service.MAX_TENTATIVAS},
        )
        result = await sweep_service.varrer_extracoes_pendentes(
            scoped, storage,
            extractor_factory=lambda _org, _tipo=None: FakeCartaoCnpjExtractor(result=_leitura()),
        )
        doc = _documento(scoped, doc_id)

        assert result["esgotados"] == 1
        assert result["retomados"] == 0
        # Terminal, visible, and explains itself — not a silent `processando`.
        assert doc["extracao_status"] == "erro"
        assert "tentativas" in doc["extracao_erro"]

    @pytest.mark.asyncio
    async def test_a_terminal_document_is_never_swept(self, client, scoped):
        _empresa_id, _doc_id, storage = await _setup(
            scoped,
            doc_extra={"extracao_status": "ok", "extracao_em": _old(600)},
        )
        assert (await sweep_service.varrer_extracoes_pendentes(scoped, storage))["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_an_exhausted_erro_document_is_never_swept(self, client, scoped):
        """`_candidatos`' `com_erro` branch filters `extracao_tentativas <
        MAX_TENTATIVAS` — an already-esgotado row must not re-enter the
        candidate pool and loop."""
        _empresa_id, _doc_id, storage = await _setup(
            scoped,
            doc_extra={
                "extracao_status": "erro", "extracao_em": _old(600),
                "extracao_tentativas": extracao_service.MAX_TENTATIVAS,
            },
        )
        assert (await sweep_service.varrer_extracoes_pendentes(scoped, storage))["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_the_attempt_counter_advances_on_each_read(self, client, scoped):
        empresa_id, doc_id, storage = await _setup(scoped)
        await extracao_service.extrair_cartao(
            scoped, storage, ORG_UUID, UUID(empresa_id), UUID(doc_id),
            extractor=FakeCartaoCnpjExtractor(result=_leitura()),
        )
        assert _documento(scoped, doc_id)["extracao_tentativas"] == 1

