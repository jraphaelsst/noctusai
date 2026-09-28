"""`app.services.extracao_job` — the shared read→persist→apply→terminal-
status skeleton (lesson G6, 2026-09-28: three sibling extraction services
each stamped a terminal `ok` BEFORE their own apply step, with no/only-
logging exception handling around it — a transient DB error there left an
`ok` document with nothing actually applied and no retry, since the sweep
never revisits an `ok` row).

Unit-level coverage of the runner ITSELF, table-agnostic (a synthetic
table, no product migration needed) — each of the three real adopters
(`card_hub.identidade_extracao_service`, `empresas.extracao_service`,
`imovel_hub.matricula_extracao_service`) pins the SAME contract end to end,
against their OWN real apply steps, in their own test suites.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services import extracao_job
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_ID = str(uuid4())
BUCKET = "test-bucket"
TABLE = "docs_teste"


class _Leitura:
    """A minimal stand-in `leitura` — just the shape `ExtractionJobConfig`
    needs (`.error`, `.error_message`, `.source`), plus a `.valor` payload
    a test's `processar` can persist and assert on."""

    def __init__(self, *, error=None, error_message=None, source="text_layer", valor="ok"):
        self.error = error
        self.error_message = error_message
        self.source = source
        self.valor = valor


def _config(*, processar, leitura=None, suporta_aviso=False, erro_aplicar_codigo="aplicar_leitura"):
    leitura = leitura or _Leitura()

    async def _ler(blob_bytes: bytes, doc: dict):
        return leitura

    return extracao_job.ExtractionJobConfig(
        table=TABLE,
        bucket=BUCKET,
        deve_extrair=lambda tipo: True,
        ler=_ler,
        leitura_erro=lambda l: l.error,
        leitura_erro_mensagem=lambda l: l.error_message,
        leitura_fonte=lambda l: l.source,
        processar=processar,
        erro_aplicar_codigo=erro_aplicar_codigo,
        suporta_aviso=suporta_aviso,
    )


async def _seed(client, storage: FakeStorageBackend, *, tipo: str = "alfa") -> tuple[UUID, UUID]:
    org_id = UUID(ORG_ID)
    doc_id = uuid4()
    path = f"{ORG_ID}/{doc_id}"
    client.table(TABLE).insert(
        {
            "id": str(doc_id), "org_id": ORG_ID, "tipo_documento": tipo,
            "deleted_at": None, "storage_path": path,
            "extracao_status": "pendente", "extracao_tentativas": 0,
            "extracao_em": None, "extracao_erro": None, "extracao_fonte": None,
            "extracao_dados": None,
        }
    ).execute()
    await storage.put(bucket=BUCKET, key=path, data=b"fake bytes", content_type="application/pdf")
    return org_id, doc_id


def _doc(client, doc_id: UUID) -> dict:
    return [
        r for r in client.table(TABLE).select("*").execute().data if r["id"] == str(doc_id)
    ][0]


@pytest.fixture
def client():
    # A synthetic table with no backing migration — schema validation off,
    # same posture `tests/services/test_campo_conflitos.py` takes for its
    # own service-level unit coverage.
    return MockSupabaseClient(validate_schema=False)


@pytest.fixture
def storage():
    return FakeStorageBackend()


class TestApplyFailureNeverStampsOk:
    """The lesson, verbatim: an exception ANYWHERE inside `processar`
    (persisting the reading, applying a field, notifying) ends the job in
    `erro` — never a false terminal `ok`."""

    @pytest.mark.asyncio
    async def test_an_exception_in_processar_ends_in_erro_with_the_reading_persisted(
        self, client, storage,
    ):
        async def _boom_processar(leitura, doc: dict) -> dict:
            # Mirrors every real adopter: persist the reading FIRST, then
            # apply — the apply is what blows up here.
            extracao_job.marcar(
                client, TABLE, UUID(doc["id"]), extracao_dados={"valor": leitura.valor},
            )
            raise RuntimeError("apply exploded")

        org_id, doc_id = await _seed(client, storage)
        out = await extracao_job.executar(client, storage, org_id, doc_id, _config(processar=_boom_processar))

        assert out["status"] == "erro"
        assert out["erro"] == "aplicar_leitura"

        doc = _doc(client, doc_id)
        assert doc["extracao_status"] == "erro"
        assert "aplicar_leitura" in doc["extracao_erro"]
        # The reading is NOT lost — persisted before the failing apply, so
        # the failure is diagnosable without re-reading the document.
        assert doc["extracao_dados"] == {"valor": "ok"}

    @pytest.mark.asyncio
    async def test_a_site_can_name_its_own_apply_erro_code(self, client, storage):
        async def _boom(leitura, doc: dict) -> dict:
            raise RuntimeError("boom")

        org_id, doc_id = await _seed(client, storage)
        config = _config(processar=_boom, erro_aplicar_codigo="aplicar_campos")
        out = await extracao_job.executar(client, storage, org_id, doc_id, config)
        assert out["erro"] == "aplicar_campos"
        assert "aplicar_campos" in _doc(client, doc_id)["extracao_erro"]

    @pytest.mark.asyncio
    async def test_a_failed_reading_is_never_persisted(self, client, storage):
        """The DPS-tripwire shape every sibling follows: a reading that
        errors is not even handed to `processar`."""
        called = False

        async def _processar(leitura, doc: dict) -> dict:
            nonlocal called
            called = True
            return {"status": extracao_job.OK}

        org_id, doc_id = await _seed(client, storage)
        leitura = _Leitura(error="resolver_failed", error_message="vision down")
        config = _config(processar=_processar, leitura=leitura)
        out = await extracao_job.executar(client, storage, org_id, doc_id, config)

        assert out["status"] == "erro"
        assert out["erro"] == "resolver_failed"
        assert called is False
        doc = _doc(client, doc_id)
        assert doc["extracao_status"] == "erro"
        assert "vision down" in doc["extracao_erro"]
        assert doc["extracao_dados"] is None


class TestTerminalStatusLandsOnlyAfterApplySucceeds:
    @pytest.mark.asyncio
    async def test_the_document_is_still_non_terminal_while_processar_runs(
        self, client, storage,
    ):
        async def _processar(leitura, doc: dict) -> dict:
            # The terminal status must NOT exist yet while this runs — it
            # lands only AFTER `processar` returns.
            assert _doc(client, UUID(doc["id"]))["extracao_status"] == "processando"
            return {"status": extracao_job.OK}

        org_id, doc_id = await _seed(client, storage)
        out = await extracao_job.executar(client, storage, org_id, doc_id, _config(processar=_processar))
        assert out["status"] == "ok"
        assert _doc(client, doc_id)["extracao_status"] == "ok"

    @pytest.mark.asyncio
    async def test_aviso_is_only_written_when_the_table_supports_it(self, client, storage):
        async def _processar(leitura, doc: dict) -> dict:
            return {"status": extracao_job.OK, "aviso": "algo_a_dizer"}

        org_id, doc_id = await _seed(client, storage)
        config = _config(processar=_processar, suporta_aviso=False)
        await extracao_job.executar(client, storage, org_id, doc_id, config)
        # `suporta_aviso=False` (the default — most of this family's tables
        # have no `extracao_aviso` column, migration 171 is the exception)
        # must never write it, or a real update would 400 on an unknown
        # column.
        assert "extracao_aviso" not in _doc(client, doc_id)

    @pytest.mark.asyncio
    async def test_aviso_is_written_when_the_table_opts_in(self, client, storage):
        async def _processar(leitura, doc: dict) -> dict:
            return {"status": extracao_job.SEM_DADOS, "aviso": "algo_a_dizer"}

        org_id, doc_id = await _seed(client, storage)
        config = _config(processar=_processar, suporta_aviso=True)
        await extracao_job.executar(client, storage, org_id, doc_id, config)
        doc = _doc(client, doc_id)
        assert doc["extracao_status"] == "sem_dados"
        assert doc["extracao_aviso"] == "algo_a_dizer"


class TestPreambleFailuresAreRecordedNotRaised:
    @pytest.mark.asyncio
    async def test_a_document_not_found_is_an_erro_result_not_an_exception(
        self, client, storage,
    ):
        out = await extracao_job.executar(
            client, storage, UUID(ORG_ID), uuid4(),
            _config(processar=lambda *a, **kw: {"status": extracao_job.OK}),
        )
        assert out == {"status": "erro", "erro": "documento_nao_encontrado"}

    @pytest.mark.asyncio
    async def test_a_deleted_document_is_never_read(self, client, storage):
        org_id, doc_id = await _seed(client, storage)
        client.table(TABLE).update({"deleted_at": "2026-09-28T00:00:00+00:00"}).eq(
            "id", str(doc_id)
        ).execute()
        called = False

        async def _processar(leitura, doc):
            nonlocal called
            called = True
            return {"status": extracao_job.OK}

        out = await extracao_job.executar(client, storage, org_id, doc_id, _config(processar=_processar))
        assert out == {"status": "erro", "erro": "documento_removido"}
        assert called is False

    @pytest.mark.asyncio
    async def test_a_missing_storage_object_is_recorded(self, client, storage):
        org_id, doc_id = await _seed(client, storage)
        empty_storage = FakeStorageBackend()  # never `.put()` — object absent
        out = await extracao_job.executar(
            client, empty_storage, org_id, doc_id,
            _config(processar=lambda *a, **kw: {"status": extracao_job.OK}),
        )
        assert out == {"status": "erro", "erro": "objeto_ausente"}
        assert _doc(client, doc_id)["extracao_status"] == "erro"
