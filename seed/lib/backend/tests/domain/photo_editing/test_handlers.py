from __future__ import annotations

import dataclasses
import io
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from PIL import Image

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobStatus, Worker
from noctusai_lib.domain.photo_editing import (
    BatchStatus,
    Decision,
    EditType,
    FakeStructuredLlm,
    InvalidModelOutputError,
    JobType,
    OrgSettings,
    PhotoStatus,
    Speed,
    SubmissionError,
    TokenUsage,
    add_photo_bytes,
    build_handlers,
    build_worker,
    handle_avaliar,
    handle_edit,
    handle_fx_backfill,
    handle_ingest,
    handle_lote_pronto,
    handle_propor_regras,
    handle_regen_guia,
    is_retryable,
    openai_image_edit_factory,
    record_decision,
    submit_batch,
)
from noctusai_lib.domain.photo_editing.handlers import parse_evaluation
from noctusai_lib.domain.photo_editing.types import PlatformSettings, ReferencePair, Room
from noctusai_lib.integrations.fx import FakeFxRateAdapter
from noctusai_lib.integrations.image_edit import (
    EditedImage,
    ImageEditContentPolicyViolation,
    ImageEditNotConfigured,
    ImageEditRateLimited,
    ImageEditResult,
    ImageEditUsage,
    OpenAIImageEditAdapter,
)
from noctusai_lib.integrations.imaging import RealImagingAdapter, UnsupportedImageFormatError
from noctusai_lib.integrations.llm.exceptions import LLMAPIError
from noctusai_lib.integrations.quota import InMemoryQuotaTracker, QuotaConfig

from .conftest import EDIT_MODEL, ORG, USER, EditFactory, activate_guide, run


def job(job_type: str, payload: dict, retry_count: int = 0) -> Job:
    now = datetime.now(timezone.utc)
    return Job(id="j", type=job_type, payload=payload, status=JobStatus.RUNNING,
               retry_count=retry_count, max_retries=1, last_error=None,
               created_at=now, updated_at=now)


async def new_batch(ports, velocidade=Speed.URGENTE):
    return await ports.repo.create_batch(org_id=ORG, nome="L", criado_por=USER,
                                         origem="upload", velocidade=velocidade)


async def drain(ports, types=None) -> None:
    if types is None:
        worker = build_worker(ports, worker_id="w")
    else:
        handlers = {k: v for k, v in build_handlers(ports).items() if k in types}
        worker = Worker(ports.jobs, worker_id="w", handlers=handlers,
                        retry_policy=ports.config.retry_policy())
    for _ in range(500):
        if not await worker.run_once():
            return
    raise AssertionError("did not converge")


# ---------------------------------------------------------------------------
# Real pixels: output keeps the input size; staging is watermarked
# ---------------------------------------------------------------------------


def jpeg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


class PngEditAdapter:
    """Returns a real PNG at the requested edit size (DI double)."""

    backend = "png"

    def __init__(self) -> None:
        self.sizes: list[str] = []

    async def edit(self, request, *, org_id=None):
        self.sizes.append(request.size)
        w, h = (int(x) for x in request.size.split("x"))
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (10, 200, 10)).save(buf, format="PNG")
        return ImageEditResult(
            images=(EditedImage(image_bytes=buf.getvalue(), format="png"),),
            model=EDIT_MODEL,
            usage=ImageEditUsage(prompt_tokens=50, image_input_tokens=1000,
                                 image_output_tokens=4000, total_tokens=5050),
            latency_ms=1,
            raw={},
        )

    def capabilities(self, model):
        raise NotImplementedError


@pytest.mark.parametrize("w,h", [(720, 1080), (1620, 1080)])
def test_output_is_jpeg_at_input_size(ports, w, h) -> None:
    adapter = PngEditAdapter()
    real = dataclasses.replace(ports, imaging=RealImagingAdapter(), image_edit=EditFactory(adapter))
    real.repo.seed_org_settings(OrgSettings(
        org_id=ORG, tipos_edicao_ativos=(EditType.STAGING_VIRTUAL,), modelo_editor_id=EDIT_MODEL))

    async def scenario() -> None:
        await activate_guide(real)
        batch = await new_batch(real)
        photo = await add_photo_bytes(real, lote_id=batch.id, data=jpeg(w, h), extension="jpg")
        await submit_batch(real, batch.id, submitted_by=USER)
        await drain(real)
        photo = await real.repo.get_photo(photo.id)
        assert photo.status is PhotoStatus.AGUARDANDO_DECISAO
        ew, eh = (int(x) for x in adapter.sizes[0].split("x"))
        assert ew % 16 == 0 and eh % 16 == 0 and ew * eh <= 2560 * 1440
        out = Image.open(io.BytesIO(real.storage.objects[photo.storage_path_editada][0]))
        assert (out.format, out.size) == ("JPEG", (w, h))
        # Watermark pixels differ from the flat edit colour in the corner.
        assert out.getpixel((w - 5, h - 5)) != out.getpixel((5, 5))
        edit = await real.repo.latest_edit(photo.id)
        assert edit.modelo_versao == f"{EDIT_MODEL}-2026-09-08"
        assert edit.llm_usage_id in real.repo.llm_usage

    run(scenario())


def test_undecodable_upload_fails_fatally(ports) -> None:
    real = dataclasses.replace(ports, imaging=RealImagingAdapter())

    async def scenario() -> None:
        batch = await new_batch(real)
        photo = await add_photo_bytes(real, lote_id=batch.id, data=b"not an image", extension="jpg")
        with pytest.raises(DeadLetterError):
            await handle_ingest(real, job(JobType.INGEST, {"foto_id": photo.id}))
        photo = await real.repo.get_photo(photo.id)
        assert photo.status is PhotoStatus.FALHOU
        assert photo.falha_motivo.startswith("UnsupportedImageFormatError")

    run(scenario())


# ---------------------------------------------------------------------------
# Uploads + submission guards
# ---------------------------------------------------------------------------


def test_upload_guards(ports) -> None:
    async def scenario() -> None:
        ports.repo.seed_org_settings(OrgSettings(org_id=ORG, limite_fotos_por_lote=1,
                                                 limite_bytes_por_foto=10))
        batch = await new_batch(ports)
        for data, ext, code in [(b"", "jpg", "arquivo_vazio"),
                                (b"x" * 11, "jpg", "arquivo_grande_demais"),
                                (b"x", "gif", "formato_nao_suportado")]:
            with pytest.raises(SubmissionError) as exc:
                await add_photo_bytes(ports, lote_id=batch.id, data=data, extension=ext)
            assert exc.value.code == code
        await add_photo_bytes(ports, lote_id=batch.id, data=b"x", extension="JPG")
        with pytest.raises(SubmissionError) as exc:
            await add_photo_bytes(ports, lote_id=batch.id, data=b"y", extension="jpg")
        assert exc.value.code == "lote_cheio"
        # Ingest dedupe: one job for the photo.
        assert [j.type for j in ports.jobs._jobs.values()] == [JobType.INGEST]

    run(scenario())


@pytest.mark.parametrize(
    "settings,velocidade,code",
    [
        (OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,)), Speed.URGENTE,
         "modelo_nao_configurado"),
        (OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,), modelo_editor_id="gpt-image-2"),
         Speed.URGENTE, "modelo_desconhecido"),
        (OrgSettings(org_id=ORG, modelo_editor_id=EDIT_MODEL), Speed.URGENTE, "sem_tipos_edicao"),
        (OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,), modelo_editor_id=EDIT_MODEL),
         Speed.ECONOMICO, "economico_indisponivel"),
    ],
)
def test_submission_refusals(ports, settings, velocidade, code) -> None:
    async def scenario() -> None:
        await activate_guide(ports)
        ports.repo.seed_org_settings(settings)
        batch = await new_batch(ports, velocidade)
        await add_photo_bytes(ports, lote_id=batch.id, data=b"x", extension="jpg")
        with pytest.raises(SubmissionError) as exc:
            await submit_batch(ports, batch.id, submitted_by=USER)
        assert exc.value.code == code
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.RASCUNHO

    run(scenario())


def test_empty_batch_and_missing_guide(ports) -> None:
    from noctusai_lib.domain.photo_editing import GuideNotActiveError

    async def scenario() -> None:
        batch = await new_batch(ports)
        with pytest.raises(SubmissionError, match="não tem fotos"):
            await submit_batch(ports, batch.id, submitted_by=USER)
        await add_photo_bytes(ports, lote_id=batch.id, data=b"x", extension="jpg")
        with pytest.raises(GuideNotActiveError):
            await submit_batch(ports, batch.id, submitted_by=USER)

    run(scenario())


def test_submit_is_idempotent_and_snapshots_guide(ports) -> None:
    async def scenario() -> None:
        await activate_guide(ports, "v1")
        batch = await new_batch(ports)
        await add_photo_bytes(ports, lote_id=batch.id, data=b"x", extension="jpg")
        first = await submit_batch(ports, batch.id, submitted_by=USER)
        # A new guide activated after submit must NOT change the batch.
        await activate_guide(ports, "v2")
        again = await submit_batch(ports, batch.id, submitted_by=USER)
        assert again.guia_efetivo_sha256 == first.guia_efetivo_sha256
        submits = [j for j in ports.jobs._jobs.values() if j.type == JobType.SUBMIT_LOTE]
        assert len(submits) == 1
        await drain(ports)
        eg = await ports.repo.get_effective_guide(first.guia_efetivo_id)
        assert "v1" in eg.texto
        assert all("v1" in c["prompt"] for c in ports.image_edit.adapter.calls)

    run(scenario())


# ---------------------------------------------------------------------------
# Handler idempotency + failure policy
# ---------------------------------------------------------------------------


async def _edited_photo(ports):
    await activate_guide(ports)
    batch = await new_batch(ports)
    photo = await add_photo_bytes(ports, lote_id=batch.id, data=b"x", extension="jpg")
    await submit_batch(ports, batch.id, submitted_by=USER)
    await drain(ports, types={JobType.INGEST, JobType.SUBMIT_LOTE, JobType.EDIT})
    return batch, await ports.repo.get_photo(photo.id)


def test_handlers_are_idempotent(ports) -> None:
    async def scenario() -> None:
        batch, photo = await _edited_photo(ports)
        assert photo.status is PhotoStatus.EDITADA
        calls = len(ports.image_edit.adapter.calls)
        await handle_edit(ports, job(JobType.EDIT, {"foto_id": photo.id}))
        await handle_ingest(ports, job(JobType.INGEST, {"foto_id": photo.id}))
        assert len(ports.image_edit.adapter.calls) == calls
        edit = await ports.repo.latest_edit(photo.id)
        await handle_avaliar(ports, job(JobType.AVALIAR, {"foto_id": photo.id, "edicao_id": edit.id}))
        n_evals = len(ports.repo.evaluations)
        await handle_avaliar(ports, job(JobType.AVALIAR, {"foto_id": photo.id, "edicao_id": edit.id}))
        assert len(ports.repo.evaluations) == n_evals == 1
        # Batch-ready: first call notifies, second is a no-op.
        await handle_lote_pronto(ports, job(JobType.LOTE_PRONTO, {"lote_id": batch.id}))
        await handle_lote_pronto(ports, job(JobType.LOTE_PRONTO, {"lote_id": batch.id}))
        assert len(ports.notifier.notices) == 1

    run(scenario())


def test_missing_payload_dead_letters(ports) -> None:
    with pytest.raises(DeadLetterError):
        run(handle_edit(ports, job(JobType.EDIT, {})))
    with pytest.raises(DeadLetterError):
        run(handle_edit(ports, job(JobType.EDIT, {"foto_id": "nope"})))


def test_evaluator_retry_then_fail(ports) -> None:
    async def scenario() -> None:
        batch, photo = await _edited_photo(ports)
        edit = await ports.repo.latest_edit(photo.id)
        ports.llm.responses["avaliacao_foto"] = [LLMAPIError("openai", "502"),
                                                 LLMAPIError("openai", "502")]
        payload = {"foto_id": photo.id, "edicao_id": edit.id}
        with pytest.raises(LLMAPIError):  # first run: retryable ⇒ re-raised
            await handle_avaliar(ports, job(JobType.AVALIAR, payload, retry_count=0))
        assert (await ports.repo.get_photo(photo.id)).status is PhotoStatus.AVALIANDO
        with pytest.raises(DeadLetterError):  # last run ⇒ falhou
            await handle_avaliar(ports, job(JobType.AVALIAR, payload, retry_count=1))
        photo = await ports.repo.get_photo(photo.id)
        assert photo.status is PhotoStatus.FALHOU
        tipos = [e.tipo for e in ports.repo.events if e.foto_id == photo.id]
        assert tipos.count("falha_transitoria") == 1 and "falha" in tipos
        ready = [j for j in ports.jobs._jobs.values() if j.type == JobType.LOTE_PRONTO]
        assert ready, "a failed photo must trigger the batch-ready check"

    run(scenario())


def test_structural_infidelity_forces_reject() -> None:
    rec, score, motivo, fiel = parse_evaluation(
        {"recomendacao": "aprovar", "score": 9, "motivo": "linda", "fidelidade_estrutural": False})
    assert (rec, score, fiel) == (Decision.REJEITAR, Decimal("9.00"), False)
    assert motivo.startswith("[estrutura alterada]")


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"recomendacao": "talvez", "score": 5, "motivo": "", "fidelidade_estrutural": True},
        {"recomendacao": "aprovar", "score": 11, "motivo": "", "fidelidade_estrutural": True},
        {"recomendacao": "aprovar", "score": "x", "motivo": "", "fidelidade_estrutural": True},
        {"recomendacao": "aprovar", "score": 5, "motivo": 3, "fidelidade_estrutural": True},
    ],
)
def test_invalid_evaluation_is_retryable(bad) -> None:
    with pytest.raises(InvalidModelOutputError) as exc:
        parse_evaluation(bad)
    assert is_retryable(exc.value)


def test_classifier() -> None:
    assert is_retryable(ImageEditRateLimited("429"))
    assert not is_retryable(ImageEditContentPolicyViolation("no"))
    assert not is_retryable(UnsupportedImageFormatError("x"))
    assert not is_retryable(ValueError("bad size"))
    assert is_retryable(LLMAPIError("openai", "boom"))
    assert is_retryable(RuntimeError("unknown ⇒ retry once"))


def test_missing_vision_usage_is_recorded_as_an_event_not_a_zero(ports) -> None:
    no_usage = dataclasses.replace(
        ports, llm=FakeStructuredLlm({"avaliacao_foto": ports.llm.responses["avaliacao_foto"]},
                                     usage=None))

    async def scenario() -> None:
        _, photo = await _edited_photo(no_usage)
        edit = await no_usage.repo.latest_edit(photo.id)
        before = len(no_usage.repo.costs)
        await handle_avaliar(no_usage, job(JobType.AVALIAR, {"foto_id": photo.id, "edicao_id": edit.id}))
        assert len(no_usage.repo.costs) == before
        notes = [e for e in no_usage.repo.events if e.tipo == "custo_nao_registrado"]
        assert notes and notes[0].detalhe == {"etapa": JobType.AVALIAR, "motivo": "uso_indisponivel"}

    run(scenario())


def test_edit_quota_exhausted_fails_photo(ports) -> None:
    async def scenario() -> None:
        quota = InMemoryQuotaTracker()
        await quota.register_quota(key=f"fotos.edit:{ORG}", config=QuotaConfig(cap=1, window_seconds=3600))
        capped = dataclasses.replace(ports, edit_quota=quota)
        await activate_guide(capped)
        batch = await new_batch(capped)
        for _ in range(2):
            await add_photo_bytes(capped, lote_id=batch.id, data=b"x", extension="jpg")
        await submit_batch(capped, batch.id, submitted_by=USER)
        await drain(capped, types={JobType.INGEST, JobType.SUBMIT_LOTE, JobType.EDIT})
        statuses = sorted(p.status.value for p in await capped.repo.list_photos(batch.id))
        assert statuses == ["editada", "falhou"]
        failed = [p for p in await capped.repo.list_photos(batch.id) if p.status is PhotoStatus.FALHOU]
        assert failed[0].falha_motivo.startswith("limite_de_uso_atingido")
        assert len(capped.image_edit.adapter.calls) == 1  # no spend past the cap

    run(scenario())


def test_notifications_can_be_switched_off(ports) -> None:
    async def scenario() -> None:
        ports.repo.platform_settings = PlatformSettings(notificacoes_globais_ativas=False)
        batch, photo = await _edited_photo(ports)
        await drain(ports)
        assert (await ports.repo.get_batch(batch.id)).status is BatchStatus.PRONTO
        assert ports.notifier.notices == []
        ev = [e for e in ports.repo.events if e.tipo == "lote_pronto"][0]
        assert ev.detalhe["notificado"] is False

    run(scenario())


# ---------------------------------------------------------------------------
# Debounced jobs + fx backfill
# ---------------------------------------------------------------------------


def test_regen_guia_trailing_debounce(ports, clock) -> None:
    async def scenario() -> None:
        ports.repo.seed_reference(ReferencePair(id="r", antes_url="a", depois_url="d",
                                                comodo=Room.SALA, criado_por=USER))
        await handle_regen_guia(ports, job(JobType.REGEN_GUIA, {}))
        assert ports.llm.calls == []  # pool changed just now ⇒ rescheduled
        rescheduled = [j for j in ports.jobs._jobs.values() if j.type == JobType.REGEN_GUIA]
        assert len(rescheduled) == 1 and rescheduled[0].scheduled_for > clock.now
        clock.advance(seconds=ports.config.guide_regen_debounce_seconds + 1)
        await handle_regen_guia(ports, job(JobType.REGEN_GUIA, {}))
        assert (await ports.repo.get_guide(1)).status.value == "rascunho"

    run(scenario())


def test_propor_regras_trailing_debounce(ports, clock) -> None:
    from .test_dataset_and_learning import _review_ready_photo

    async def scenario() -> None:
        await handle_propor_regras(ports, job(JobType.PROPOR_REGRAS, {"org_id": ORG}))
        assert ports.llm.calls == []  # no rejections ⇒ nothing
        _, (p,) = await _review_ready_photo(ports)
        await record_decision(ports, foto_id=p.id, decisao=Decision.REJEITAR,
                              comentario="céu falso", decidido_por=USER)
        await handle_propor_regras(ports, job(JobType.PROPOR_REGRAS, {"org_id": ORG}))
        assert ports.llm.calls == []  # too recent
        clock.advance(seconds=ports.config.rule_proposal_debounce_seconds + 1)
        ports.llm.responses["propor_regras"] = {"regras": [{"texto": "Não usar céu falso",
                                                             "comentarios": [1]}]}
        await handle_propor_regras(ports, job(JobType.PROPOR_REGRAS, {"org_id": ORG}))
        assert [r.texto for r in ports.repo.rules.values()] == ["Não usar céu falso"]

    run(scenario())


def test_fx_backfill_handler(ports) -> None:
    from noctusai_lib.domain.photo_editing import record_ai_cost

    async def scenario() -> None:
        dry = dataclasses.replace(ports, fx=FakeFxRateAdapter({}))
        await record_ai_cost(dry, org_id=ORG, step="s", category="c", operation="image_edit",
                             kind="image_edit", model=EDIT_MODEL,
                             usage=TokenUsage(image_output_tokens=100))
        await handle_fx_backfill(ports, job(JobType.FX_BACKFILL, {"dia": "2026-09-16"}))
        assert not any(c.fx_pending for c in ports.repo.costs.values())

    run(scenario())


# ---------------------------------------------------------------------------
# Wiring helpers
# ---------------------------------------------------------------------------


def test_build_worker_binds_all_handlers_and_one_retry(ports) -> None:
    worker = build_worker(ports, worker_id="w")
    assert set(worker._handlers) == set(JobType.ALL)
    assert worker._retry_policy.max_retries == 1


def test_openai_factory_refuses_without_key() -> None:
    factory = openai_image_edit_factory(lambda org_id=None: None)
    with pytest.raises(ImageEditNotConfigured):
        factory(ORG, EDIT_MODEL)
    adapter = openai_image_edit_factory(lambda org_id=None: "sk-test")(ORG, EDIT_MODEL)
    assert isinstance(adapter, OpenAIImageEditAdapter)
