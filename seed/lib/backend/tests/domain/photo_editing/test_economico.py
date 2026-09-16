"""Econômico (OpenAI Batch API) engine runs, on fakes only.

InMemory repo · FakeJobRepository driven by the REAL seed ``Worker`` ·
``FakeImageEditAdapter`` in batch mode · scripted structured LLM. The
batch-capable model is declared EXPLICITLY on both gates a test owns —
``PhotoEditingPorts.capabilities`` and the Fake's ``batch_models`` — because
the static catalog has no batch-capable image model today (PROJECT.md C8).
No live OpenAI call is made or claimed anywhere in this suite.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from decimal import Decimal

import pytest

from noctusai_lib.domain.jobs import JobStatus, Worker
from noctusai_lib.domain.photo_editing import (
    BatchStatus,
    EditType,
    JobType,
    OrgSettings,
    PhotoStatus,
    Speed,
    SubmissionError,
    add_photo_bytes,
    build_handlers,
    compute_capabilities,
    retry_photo,
    submit_batch,
)
from noctusai_lib.domain.photo_editing.costs import (
    BATCH_API_DISCOUNT,
    catalog_entry,
    price_usage_usd,
)
from noctusai_lib.domain.photo_editing.learning import Actor
from noctusai_lib.domain.photo_editing.ports import TokenUsage
from noctusai_lib.domain.photo_editing.types import OpenAIBatchStatus
from noctusai_lib.domain.permissions import FakePermissionGrantRepository
from noctusai_lib.integrations.image_edit import (
    BatchState,
    FakeImageEditAdapter,
    ImageEditCapabilities,
    ImageEditContentPolicyViolation,
    ImageEditRateLimited,
    ImageEditServerError,
)

from .conftest import EDIT_MODEL, ORG, T0, USER, EditFactory, activate_guide, run


def batch_capable(model: str) -> ImageEditCapabilities:
    """The test's catalog seam: EDIT_MODEL is batch-capable."""
    return ImageEditCapabilities(model=model, supports_batch=model == EDIT_MODEL, known=True)


@pytest.fixture
def eco(ports):
    adapter = FakeImageEditAdapter(
        model=EDIT_MODEL, batch_models={EDIT_MODEL}, batch_pending_polls=1
    )
    return dataclasses.replace(ports, image_edit=EditFactory(adapter), capabilities=batch_capable)


def worker_for(ports) -> Worker:
    return Worker(
        ports.jobs,
        worker_id="eco-worker",
        handlers=build_handlers(ports),
        retry_policy=ports.config.retry_policy(),
    )


async def drain(worker: Worker, limit: int = 500) -> int:
    n = 0
    while await worker.run_once():
        n += 1
        assert n < limit, "worker did not converge"
    return n


def jobs_of(ports, job_type: str) -> list:
    return [j for j in ports.jobs._jobs.values() if j.type == job_type]


async def new_eco_batch(ports, n_photos: int, *, ingest_first: bool = True):
    ports.repo.seed_org_settings(
        OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.COR_LUZ,), modelo_editor_id=EDIT_MODEL)
    )
    await activate_guide(ports)
    batch = await ports.repo.create_batch(
        org_id=ORG, nome="Casa eco", criado_por=USER, origem="upload", velocidade=Speed.ECONOMICO
    )
    for i in range(n_photos):
        await add_photo_bytes(ports, lote_id=batch.id, data=f"raw-{i}".encode(), extension="jpg")
    worker = worker_for(ports)
    if ingest_first:
        await drain(worker)
    return batch, worker


def test_full_economico_run_submit_poll_pending_poll_done_evaluate_ready(eco) -> None:
    ports = eco
    adapter = ports.image_edit.adapter

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 2)
        await submit_batch(ports, batch.id, submitted_by=USER)

        # Run until the provider batch is submitted: ONE batch, both photos.
        while not jobs_of(ports, JobType.POLL_OPENAI_BATCH):
            assert await worker.run_once()
        assert [c["op"] for c in adapter.batch_calls] == ["submit"]
        assert len(adapter.batch_calls[0]["custom_ids"]) == 2
        assert adapter.calls == []  # never the synchronous edit
        photos = await ports.repo.list_photos(batch.id)
        assert {p.status for p in photos} == {PhotoStatus.EM_LOTE_OPENAI}
        assert {p.openai_batch_id for p in photos} == {"fake-batch-1"}
        (record,) = ports.repo.openai_batches.values()
        assert record.status is OpenAIBatchStatus.ENVIADO
        assert record.openai_batch_id == "fake-batch-1"
        assert [i["foto_id"] for i in record.itens] == [p.id for p in photos]
        assert all(e.velocidade is Speed.ECONOMICO for e in ports.repo.edits.values())
        (poll0,) = jobs_of(ports, JobType.POLL_OPENAI_BATCH)
        assert poll0.scheduled_for == T0 + timedelta(minutes=5)

        # Poll #0 → still in progress → poll #1 scheduled 15 min out.
        while poll0.status is not JobStatus.COMPLETED:
            assert await worker.run_once()
            poll0 = ports.jobs._jobs[poll0.id]
        record = await ports.repo.get_openai_batch(record.id)
        assert (record.openai_status, record.consultas) == ("in_progress", 1)
        assert {p.status for p in await ports.repo.list_photos(batch.id)} == {
            PhotoStatus.EM_LOTE_OPENAI
        }
        polls = jobs_of(ports, JobType.POLL_OPENAI_BATCH)
        assert [j.payload["consulta"] for j in polls] == [0, 1]
        assert polls[1].scheduled_for == T0 + timedelta(minutes=15)
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PROCESSANDO

        # Poll #1 → completed → results applied → evaluated → batch ready.
        await drain(worker)
        assert [c["op"] for c in adapter.batch_calls] == ["submit", "poll", "poll", "fetch"]
        record = await ports.repo.get_openai_batch(record.id)
        assert record.status is OpenAIBatchStatus.CONCLUIDO
        assert (record.openai_status, record.consultas) == ("completed", 2)
        photos = await ports.repo.list_photos(batch.id)
        assert [p.status for p in photos] == [PhotoStatus.AGUARDANDO_DECISAO] * 2
        assert all(p.storage_path_editada in ports.storage.objects for p in photos)
        assert all(e.status == "concluida" for e in ports.repo.edits.values())
        assert len(ports.repo.evaluations) == 2
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO
        assert len(ports.notifier.notices) == 1

        # Cost: the edit legs are recorded as batch calls at 50% of the
        # catalog price; the evaluator (synchronous vision) is not.
        edit_usage = [u for u in ports.repo.llm_usage.values() if u.operation == "image_edit"]
        assert len(edit_usage) == 2 and all(u.batch for u in edit_usage)
        entry = catalog_entry("openai", EDIT_MODEL, "image_edit")
        u = edit_usage[0]
        tokens = TokenUsage(
            prompt_tokens=u.prompt_tokens,
            image_input_tokens=u.image_input_tokens,
            image_output_tokens=u.image_output_tokens,
        )
        full = price_usage_usd(entry, tokens)
        assert u.cost_estimate_usd == (full * BATCH_API_DISCOUNT).quantize(Decimal("0.000001"))
        assert u.cost_estimate_usd < full
        vision = [x for x in ports.repo.llm_usage.values() if x.operation == "vision"]
        assert len(vision) == 2 and not any(x.batch for x in vision)
        edit_costs = [c for c in ports.repo.costs.values() if c.category == "openai_edit"]
        assert len(edit_costs) == 2 and all(not c.fx_pending for c in edit_costs)

        # Events never carry costs or verdicts.
        for e in ports.repo.events:
            assert not {"score", "recomendacao", "custo", "cost"} & set(e.detalhe)
        assert all(j.status is JobStatus.COMPLETED for j in ports.jobs._jobs.values())

    run(scenario())


def test_submission_waits_for_every_ingest_then_sends_one_batch(eco) -> None:
    ports = eco

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 3, ingest_first=False)
        await submit_batch(ports, batch.id, submitted_by=USER)  # photos still `recebida`
        await drain(worker)
        submits = [c for c in ports.image_edit.adapter.batch_calls if c["op"] == "submit"]
        assert len(submits) == 1 and len(submits[0]["custom_ids"]) == 3
        assert len(ports.repo.openai_batches) == 1
        photos = await ports.repo.list_photos(batch.id)
        assert [p.status for p in photos] == [PhotoStatus.AGUARDANDO_DECISAO] * 3

    run(scenario())


def test_poll_schedule_is_5_15_30_then_30(eco) -> None:
    cfg = eco.config
    assert [cfg.poll_delay_seconds(n) for n in range(5)] == [300, 900, 1800, 1800, 1800]


def test_economico_refused_when_the_model_has_no_batch(ports) -> None:
    async def scenario() -> None:
        # Default ports: the real catalog, where EDIT_MODEL is not batch-capable.
        ports.repo.seed_org_settings(
            OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,), modelo_editor_id=EDIT_MODEL)
        )
        await activate_guide(ports)
        batch = await ports.repo.create_batch(
            org_id=ORG, nome="n", criado_por=USER, origem="upload", velocidade=Speed.ECONOMICO
        )
        await add_photo_bytes(ports, lote_id=batch.id, data=b"x", extension="jpg")
        with pytest.raises(SubmissionError) as exc:
            await submit_batch(ports, batch.id, submitted_by=USER)
        assert exc.value.code == "economico_indisponivel"

    run(scenario())


def test_capabilities_follow_the_injected_gate(eco) -> None:
    settings = OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,), modelo_editor_id=EDIT_MODEL)
    actor = Actor(user_id="a", org_id=ORG, org_role="admin")
    caps = run(
        compute_capabilities(
            actor=actor,
            settings=settings,
            grants=FakePermissionGrantRepository(),
            capabilities=eco.capabilities,
        )
    )
    assert (caps["economico_disponivel"], caps["economico_bloqueado_motivo"]) == (True, None)


class FirstBatchFails:
    """Wraps the Fake: every item of the FIRST provider batch comes back as
    ``error``; later batches pass through."""

    backend = "first-batch-fails"

    def __init__(self, inner: FakeImageEditAdapter, error: Exception, times: int = 1) -> None:
        self.inner = inner
        self.error = error
        self.failing: set[str] = set()
        self.times = times

    async def edit(self, request, *, org_id=None):
        return await self.inner.edit(request, org_id=org_id)

    def capabilities(self, model):
        return self.inner.capabilities(model)

    async def submit_batch(self, items, *, org_id=None, metadata=None):
        sub = await self.inner.submit_batch(items, org_id=org_id, metadata=metadata)
        if self.times > 0:
            self.times -= 1
            self.inner.batch_item_errors.update({i.custom_id: self.error for i in items})
        return sub

    async def poll_batch(self, batch_id, *, org_id=None):
        return await self.inner.poll_batch(batch_id, org_id=org_id)

    async def fetch_batch_results(self, batch_id, *, org_id=None):
        return await self.inner.fetch_batch_results(batch_id, org_id=org_id)


def test_transient_item_failure_is_retried_once_in_a_new_batch(eco) -> None:
    inner = FakeImageEditAdapter(model=EDIT_MODEL, batch_models={EDIT_MODEL})
    ports = dataclasses.replace(
        eco, image_edit=EditFactory(FirstBatchFails(inner, ImageEditRateLimited("429")))
    )

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 2)
        await submit_batch(ports, batch.id, submitted_by=USER)
        await drain(worker)
        submits = [c for c in inner.batch_calls if c["op"] == "submit"]
        assert len(submits) == 2 and all(len(c["custom_ids"]) == 2 for c in submits)
        records = await ports.repo.list_openai_batches(batch.id)
        assert [r.status for r in records] == [OpenAIBatchStatus.CONCLUIDO] * 2
        photos = await ports.repo.list_photos(batch.id)
        assert [p.status for p in photos] == [PhotoStatus.AGUARDANDO_DECISAO] * 2
        for p in photos:
            kinds = [e.tipo for e in ports.repo.events if e.foto_id == p.id]
            assert kinds.count("falha_transitoria") == 1
            edits = [e for e in ports.repo.edits.values() if e.foto_id == p.id]  # creation order
            assert [e.status for e in edits] == ["falhou", "concluida"]
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

    run(scenario())


def test_second_transient_failure_marks_falhou(eco) -> None:
    inner = FakeImageEditAdapter(model=EDIT_MODEL, batch_models={EDIT_MODEL})
    ports = dataclasses.replace(
        eco,
        image_edit=EditFactory(FirstBatchFails(inner, ImageEditServerError("503"), times=2)),
    )

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 1)
        await submit_batch(ports, batch.id, submitted_by=USER)
        await drain(worker)
        assert len(await ports.repo.list_openai_batches(batch.id)) == 2
        (photo,) = await ports.repo.list_photos(batch.id)
        assert photo.status is PhotoStatus.FALHOU
        assert photo.falha_motivo.startswith("ImageEditServerError")
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO
        assert ports.notifier.notices[-1].falhou == 1

    run(scenario())


def test_fatal_item_failure_fails_only_that_photo(eco) -> None:
    ports = eco
    adapter = ports.image_edit.adapter

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 2)
        photos = await ports.repo.list_photos(batch.id)
        await submit_batch(ports, batch.id, submitted_by=USER)
        while not jobs_of(ports, JobType.POLL_OPENAI_BATCH):
            assert await worker.run_once()
        (record,) = ports.repo.openai_batches.values()
        bad = next(i["custom_id"] for i in record.itens if i["foto_id"] == photos[0].id)
        adapter.batch_item_errors[bad] = ImageEditContentPolicyViolation("safety system")
        await drain(worker)
        photos = await ports.repo.list_photos(batch.id)
        assert [p.status for p in photos] == [PhotoStatus.FALHOU, PhotoStatus.AGUARDANDO_DECISAO]
        assert photos[0].falha_motivo.startswith("ImageEditContentPolicyViolation")
        assert len(ports.repo.openai_batches) == 1  # fatal ⇒ no automatic retry
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

        # Manual retry: the photo joins a NEW provider batch.
        await retry_photo(ports, photos[0].id, requested_by=USER)
        adapter.batch_item_errors.clear()
        await drain(worker)
        assert len(ports.repo.openai_batches) == 2
        retried = await ports.repo.get_photo(photos[0].id)
        assert retried.status is PhotoStatus.AGUARDANDO_DECISAO and retried.tentativas == 1
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

    run(scenario())


def test_expired_batch_retries_then_fails(eco) -> None:
    ports = eco
    adapter = ports.image_edit.adapter
    adapter.batch_pending_polls = 0

    class ExpireEvery:
        """Expires every provider batch right after it is submitted."""

        backend = "expire"

        def __init__(self, inner):
            self.inner = inner

        def capabilities(self, model):
            return self.inner.capabilities(model)

        async def submit_batch(self, items, *, org_id=None, metadata=None):
            sub = await self.inner.submit_batch(items, org_id=org_id, metadata=metadata)
            self.inner.set_batch_state(sub.batch_id, BatchState.EXPIRED)
            return sub

        async def poll_batch(self, batch_id, *, org_id=None):
            return await self.inner.poll_batch(batch_id, org_id=org_id)

        async def fetch_batch_results(self, batch_id, *, org_id=None):
            return await self.inner.fetch_batch_results(batch_id, org_id=org_id)

    ports = dataclasses.replace(ports, image_edit=EditFactory(ExpireEvery(adapter)))

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 1)
        await submit_batch(ports, batch.id, submitted_by=USER)
        await drain(worker)
        records = await ports.repo.list_openai_batches(batch.id)
        assert len(records) == 2
        assert all(r.openai_status == "expired" for r in records)
        (photo,) = await ports.repo.list_photos(batch.id)
        assert photo.status is PhotoStatus.FALHOU
        assert "batch_expired" in photo.falha_motivo
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

    run(scenario())


def test_transient_poll_error_reschedules_instead_of_failing(eco) -> None:
    inner = eco.image_edit.adapter

    class FlakyPoll:
        backend = "flaky-poll"

        def __init__(self):
            self.failures = 2

        def capabilities(self, model):
            return inner.capabilities(model)

        async def submit_batch(self, items, *, org_id=None, metadata=None):
            return await inner.submit_batch(items, org_id=org_id, metadata=metadata)

        async def poll_batch(self, batch_id, *, org_id=None):
            if self.failures:
                self.failures -= 1
                raise ImageEditServerError("502")
            return await inner.poll_batch(batch_id, org_id=org_id)

        async def fetch_batch_results(self, batch_id, *, org_id=None):
            return await inner.fetch_batch_results(batch_id, org_id=org_id)

    ports = dataclasses.replace(eco, image_edit=EditFactory(FlakyPoll()))

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 1)
        await submit_batch(ports, batch.id, submitted_by=USER)
        await drain(worker)
        polls = jobs_of(ports, JobType.POLL_OPENAI_BATCH)
        # 2 failed polls + 1 pending (batch_pending_polls=1) + 1 completed.
        assert [j.payload["consulta"] for j in polls] == [0, 1, 2, 3]
        assert all(j.status is JobStatus.COMPLETED for j in polls)
        (photo,) = await ports.repo.list_photos(batch.id)
        assert photo.status is PhotoStatus.AGUARDANDO_DECISAO
        assert await ports.jobs.list_dead_letters() == []

    run(scenario())


def test_overdue_batch_fails_its_photos(eco) -> None:
    ports = eco.with_config(openai_batch_max_wait_seconds=60)
    ports.image_edit.adapter.batch_pending_polls = 10
    clock = ports.clock

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 1)
        await submit_batch(ports, batch.id, submitted_by=USER)
        while not jobs_of(ports, JobType.POLL_OPENAI_BATCH):
            assert await worker.run_once()
        clock.advance(minutes=5)
        await drain(worker)
        (photo,) = await ports.repo.list_photos(batch.id)
        assert photo.status is PhotoStatus.FALHOU
        assert photo.falha_motivo.startswith("lote_openai_prazo_excedido")
        (record,) = ports.repo.openai_batches.values()
        assert record.status is OpenAIBatchStatus.FALHOU
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

    run(scenario())


def test_submit_resumes_a_preparando_record_after_a_transient_submit_error(eco) -> None:
    inner = eco.image_edit.adapter

    class SubmitFailsOnce:
        backend = "submit-fails-once"

        def __init__(self):
            self.failures = 1

        def capabilities(self, model):
            return inner.capabilities(model)

        async def submit_batch(self, items, *, org_id=None, metadata=None):
            if self.failures:
                self.failures -= 1
                raise ImageEditRateLimited("429")
            return await inner.submit_batch(items, org_id=org_id, metadata=metadata)

        async def poll_batch(self, batch_id, *, org_id=None):
            return await inner.poll_batch(batch_id, org_id=org_id)

        async def fetch_batch_results(self, batch_id, *, org_id=None):
            return await inner.fetch_batch_results(batch_id, org_id=org_id)

    ports = dataclasses.replace(eco, image_edit=EditFactory(SubmitFailsOnce()))

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 2)
        await submit_batch(ports, batch.id, submitted_by=USER)
        await drain(worker)
        # The retried job resumed the SAME record; no duplicate edits/records.
        assert len(ports.repo.openai_batches) == 1
        assert len(ports.repo.edits) == 2
        assert [c["op"] for c in inner.batch_calls].count("submit") == 1
        photos = await ports.repo.list_photos(batch.id)
        assert [p.status for p in photos] == [PhotoStatus.AGUARDANDO_DECISAO] * 2
        kinds = [e.tipo for e in ports.repo.events if e.foto_id is None]
        assert "falha_transitoria" in kinds

    run(scenario())


def test_final_submit_failure_fails_every_photo(eco) -> None:
    inner = eco.image_edit.adapter

    class NeverSubmits:
        backend = "never"

        def capabilities(self, model):
            return inner.capabilities(model)

        async def submit_batch(self, items, *, org_id=None, metadata=None):
            raise ImageEditServerError("500")

    ports = dataclasses.replace(eco, image_edit=EditFactory(NeverSubmits()))

    async def scenario() -> None:
        batch, worker = await new_eco_batch(ports, 2)
        await submit_batch(ports, batch.id, submitted_by=USER)
        await drain(worker)
        photos = await ports.repo.list_photos(batch.id)
        assert [p.status for p in photos] == [PhotoStatus.FALHOU] * 2
        (record,) = ports.repo.openai_batches.values()
        assert record.status is OpenAIBatchStatus.FALHOU and record.erro
        dead = await ports.jobs.list_dead_letters()
        assert [j.type for j in dead] == [JobType.SUBMIT_OPENAI_BATCH]
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO

    run(scenario())


def test_gate_closing_after_submit_fails_photos_loudly(eco) -> None:
    """The catalog can lose the batch flag between submit and the job."""
    closed = dataclasses.replace(eco, capabilities=lambda m: ImageEditCapabilities(m, False, True))

    async def scenario() -> None:
        batch, worker = await new_eco_batch(eco, 1)
        await submit_batch(eco, batch.id, submitted_by=USER)
        assert await worker.run_once()  # fotos.submit_lote, gate still open
        assert jobs_of(eco, JobType.SUBMIT_OPENAI_BATCH)
        await drain(worker_for(closed))
        (photo,) = await closed.repo.list_photos(batch.id)
        assert photo.status is PhotoStatus.FALHOU
        assert photo.falha_motivo.startswith("economico_indisponivel")

    run(scenario())
