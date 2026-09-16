"""Full engine run, upload → zip, Urgente, on fakes only.

InMemory repo · FakeJobRepository driven by the REAL seed ``Worker`` ·
seed Fake imaging / image_edit / fx · scripted structured LLM. No live
OpenAI call is made or claimed anywhere in this suite.
"""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal

from noctusai_lib.domain.jobs import JobStatus, Worker
from noctusai_lib.domain.photo_editing import (
    BatchStatus,
    Decision,
    EditType,
    JobType,
    OrgSettings,
    PhotoStatus,
    Speed,
    add_photo_bytes,
    build_batch_zip,
    build_handlers,
    record_decision,
    submit_batch,
)
from noctusai_lib.domain.photo_editing.types import PROCESSING_DONE_STATES

from .conftest import EDIT_MODEL, ORG, PTAX, USER, activate_guide, run

PIPELINE = (
    JobType.INGEST,
    JobType.SUBMIT_LOTE,
    JobType.EDIT,
    JobType.AVALIAR,
    JobType.LOTE_PRONTO,
)


def pipeline_worker(ports) -> Worker:
    handlers = {k: v for k, v in build_handlers(ports).items() if k in PIPELINE}
    return Worker(
        ports.jobs,
        worker_id="test-worker",
        handlers=handlers,
        retry_policy=ports.config.retry_policy(),
    )


async def drain(worker: Worker, limit: int = 500) -> int:
    n = 0
    while await worker.run_once():
        n += 1
        assert n < limit, "worker did not converge"
    return n


async def _scenario(ports, *, n_photos: int, tipos=(EditType.COR_LUZ, EditType.CEU)):
    ports.repo.seed_org_settings(
        OrgSettings(org_id=ORG, tipos_edicao_ativos=tuple(tipos), modelo_editor_id=EDIT_MODEL)
    )
    await activate_guide(ports)
    batch = await ports.repo.create_batch(
        org_id=ORG, nome="Casa 42", criado_por=USER, origem="upload", velocidade=Speed.URGENTE
    )
    for i in range(n_photos):
        await add_photo_bytes(
            ports, lote_id=batch.id, data=f"raw-photo-{i}".encode(), extension="heic"
        )
    worker = pipeline_worker(ports)
    await drain(worker)  # ingest only: the batch is still a draft
    photos = await ports.repo.list_photos(batch.id)
    assert {p.status for p in photos} == {PhotoStatus.PRONTA}
    assert ports.image_edit.requests == []  # nothing edited before submit

    await submit_batch(ports, batch.id, submitted_by=USER)
    await drain(worker)
    return batch, worker


def test_upload_to_zip_urgente(ports) -> None:
    async def scenario() -> None:
        batch, worker = await _scenario(ports, n_photos=3)
        repo = ports.repo

        batch = await repo.get_batch(batch.id)
        assert batch.status is BatchStatus.PRONTO
        assert batch.guia_efetivo_sha256 and batch.modelo_editor_id == EDIT_MODEL
        photos = await repo.list_photos(batch.id)
        assert [p.status for p in photos] == [PhotoStatus.AGUARDANDO_DECISAO] * 3

        # GPS strip: raw uploads are gone, only normalized originals + edits remain.
        stored = set(ports.storage.objects)
        assert not any("/u-" in path for path in stored)
        for p in photos:
            assert p.storage_path_original == f"{ORG}/{batch.id}/{p.id}/original.jpg"
            assert p.storage_path_editada == f"{ORG}/{batch.id}/{p.id}/editada.jpg"
            assert p.storage_path_editada in stored

        # One combined edit call per photo, with the org's model; the
        # imaging organ resized to the edit size and back to input size.
        assert ports.image_edit.requests == [(ORG, EDIT_MODEL)] * 3
        edit_calls = ports.image_edit.adapter.calls
        assert len(edit_calls) == 3
        assert all("Corrigir cor e luz" in c["prompt"] for c in edit_calls)
        assert all("Substituir o céu" in c["prompt"] for c in edit_calls)
        assert not any(c["op"] == "apply_watermark" for c in ports.imaging.calls)

        # Evaluator saw [original, edited]; verdict stored in its own record.
        evals = [c for c in ports.llm.calls if c["schema_name"] == "avaliacao_foto"]
        assert len(evals) == 3 and all(len(c["images"]) == 2 for c in evals)
        assert len(repo.evaluations) == 3
        # Events never leak the verdict (corretor can read fotos_eventos).
        for e in repo.events:
            assert "score" not in e.detalhe and "recomendacao" not in e.detalhe

        # Costs: 3 edits + 3 evaluations → llm_usage + converted ledger rows.
        assert len(repo.llm_usage) == 6
        costs = list(repo.costs.values())
        assert len(costs) == 6
        assert all(c.currency == "USD" and not c.fx_pending for c in costs)
        assert all(c.fx_rate == PTAX for c in costs)
        assert {c.category for c in costs} == {"openai_edit", "openai_vision"}

        # One notification for the round.
        assert len(ports.notifier.notices) == 1
        notice = ports.notifier.notices[0]
        assert (notice.total_fotos, notice.aguardando_decisao, notice.falhou) == (3, 3, 0)

        # Review: approve 1 and 3, reject 2 (comment required).
        await record_decision(ports, foto_id=photos[0].id, decisao=Decision.APROVAR,
                              comentario=None, decidido_por=USER)
        await record_decision(ports, foto_id=photos[1].id, decisao=Decision.REJEITAR,
                              comentario="Céu artificial demais", decidido_por=USER)
        await record_decision(ports, foto_id=photos[2].id, decisao=Decision.APROVAR,
                              comentario=None, decidido_por=USER)
        assert len(repo.dataset) == 3
        assert all(r.guia_efetivo_sha256 == batch.guia_efetivo_sha256 for r in repo.dataset)
        assert repo.dataset[1].avaliacao_score == Decimal("8.50")

        data = await build_batch_zip(ports, batch.id)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert zf.namelist() == ["01.jpg", "03.jpg"]
            assert zf.read("01.jpg") == ports.storage.objects[photos[0].storage_path_editada][0]

        # Decisions stay changeable after download; the zip follows.
        await record_decision(ports, foto_id=photos[1].id, decisao=Decision.APROVAR,
                              comentario=None, decidido_por=USER)
        with zipfile.ZipFile(io.BytesIO(await build_batch_zip(ports, batch.id))) as zf:
            assert zf.namelist() == ["01.jpg", "02.jpg", "03.jpg"]

        # Every job the pipeline created ended COMPLETED.
        statuses = {j.status for j in ports.jobs._jobs.values() if j.type in PIPELINE}
        assert statuses == {JobStatus.COMPLETED}

    run(scenario())


def test_staging_gets_watermark_and_suffix(ports) -> None:
    async def scenario() -> None:
        batch, _ = await _scenario(ports, n_photos=1, tipos=(EditType.STAGING_VIRTUAL,))
        photo = (await ports.repo.list_photos(batch.id))[0]
        watermarks = [c for c in ports.imaging.calls if c["op"] == "apply_watermark"]
        assert [c["text"] for c in watermarks] == ["Imagem gerada com IA"]
        await record_decision(ports, foto_id=photo.id, decisao=Decision.APROVAR,
                              comentario=None, decidido_por=USER)
        with zipfile.ZipFile(io.BytesIO(await build_batch_zip(ports, batch.id))) as zf:
            assert zf.namelist() == ["01_imagem-gerada-com-ia.jpg"]

    run(scenario())


def test_transient_failure_retries_once_then_succeeds(ports) -> None:
    from noctusai_lib.integrations.image_edit import ImageEditRateLimited

    class FlakyOnce:
        backend = "flaky"

        def __init__(self, inner) -> None:
            self.inner = inner
            self.failures = 1

        async def edit(self, request, *, org_id=None):
            if self.failures:
                self.failures -= 1
                raise ImageEditRateLimited("429")
            return await self.inner.edit(request, org_id=org_id)

        def capabilities(self, model):
            return self.inner.capabilities(model)

    ports.image_edit.adapter = FlakyOnce(ports.image_edit.adapter)

    async def scenario() -> None:
        batch, _ = await _scenario(ports, n_photos=1)
        photo = (await ports.repo.list_photos(batch.id))[0]
        assert photo.status is PhotoStatus.AGUARDANDO_DECISAO
        kinds = [e.tipo for e in ports.repo.events if e.foto_id == photo.id]
        assert kinds.count("falha_transitoria") == 1
        # The retried run reused the same edit attempt row.
        assert len([e for e in ports.repo.edits.values() if e.foto_id == photo.id]) == 1
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

    run(scenario())


def test_persistent_failure_marks_falhou_and_does_not_block_batch(ports) -> None:
    from noctusai_lib.integrations.image_edit import ImageEditServerError

    class Selective:
        """Fails edit calls #2 and #3 — photo 2's first run and its single
        automatic retry (the fake job queue re-claims a due retry first)."""

        backend = "selective"

        def __init__(self, inner) -> None:
            self.inner = inner
            self.calls = 0

        async def edit(self, request, *, org_id=None):
            self.calls += 1
            if self.calls in (2, 3):  # photo #2's first run and its one retry
                raise ImageEditServerError("503")
            return await self.inner.edit(request, org_id=org_id)

        def capabilities(self, model):
            return self.inner.capabilities(model)

    ports.image_edit.adapter = Selective(ports.image_edit.adapter)

    async def scenario() -> None:
        batch, _ = await _scenario(ports, n_photos=3)
        photos = await ports.repo.list_photos(batch.id)
        statuses = sorted(p.status.value for p in photos)
        assert statuses == ["aguardando_decisao", "aguardando_decisao", "falhou"]
        failed = next(p for p in photos if p.status is PhotoStatus.FALHOU)
        assert failed.falha_motivo.startswith("ImageEditServerError")
        dead = await ports.jobs.list_dead_letters()
        assert len(dead) == 1 and dead[0].type == JobType.EDIT
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO
        assert ports.notifier.notices[-1].falhou == 1

        ok = [p for p in photos if p.status is not PhotoStatus.FALHOU]
        for p in ok:
            await record_decision(ports, foto_id=p.id, decisao=Decision.APROVAR,
                                  comentario=None, decidido_por=USER)
        with zipfile.ZipFile(io.BytesIO(await build_batch_zip(ports, batch.id))) as zf:
            assert len(zf.namelist()) == 2  # falhou excluded, never blocks

    run(scenario())


def test_manual_retry_runs_a_new_attempt(ports) -> None:
    from noctusai_lib.domain.photo_editing import retry_photo
    from noctusai_lib.integrations.image_edit import ImageEditContentPolicyViolation

    class FatalOnce:
        backend = "fatal-once"

        def __init__(self, inner) -> None:
            self.inner = inner
            self.fired = False

        async def edit(self, request, *, org_id=None):
            if not self.fired:
                self.fired = True
                raise ImageEditContentPolicyViolation("policy")
            return await self.inner.edit(request, org_id=org_id)

        def capabilities(self, model):
            return self.inner.capabilities(model)

    ports.image_edit.adapter = FatalOnce(ports.image_edit.adapter)

    async def scenario() -> None:
        batch, worker = await _scenario(ports, n_photos=1)
        photo = (await ports.repo.list_photos(batch.id))[0]
        assert photo.status is PhotoStatus.FALHOU  # fatal: no auto-retry
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

        await retry_photo(ports, photo.id, requested_by=USER)
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PROCESSANDO
        await drain(worker)
        photo = await ports.repo.get_photo(photo.id)
        assert photo.status is PhotoStatus.AGUARDANDO_DECISAO
        assert photo.tentativas == 1
        attempts = sorted(e.tentativa for e in ports.repo.edits.values())
        assert attempts == [1, 2]
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO
        assert len(ports.notifier.notices) == 2  # one per round

    run(scenario())


def test_done_states_cover_every_terminal_photo_state() -> None:
    assert PROCESSING_DONE_STATES == {
        PhotoStatus.AGUARDANDO_DECISAO,
        PhotoStatus.APROVADA,
        PhotoStatus.REJEITADA,
        PhotoStatus.FALHOU,
    }
