"""Job handlers — one idempotent handler per job type.

Signature: ``async def handle_x(ports: PhotoEditingPorts, job: Job) -> None``.
``build_handlers(ports)`` binds them for ``noctusai_lib.domain.jobs.Worker``;
``build_worker(ports, worker_id=...)`` also binds the engine's retry policy
(auto-retry ONCE, then ``falhou``) — use it, so the handlers' own
"is this the last attempt?" check and the worker's policy agree.

Failure semantics (plan §6):
- retryable (429 / 5xx / timeout / malformed model output / unknown) on
  the first run → a ``falha_transitoria`` event, re-raise → the worker
  requeues the job once;
- retryable on the last run, or fatal (content policy / invalid size /
  unsupported file / missing configuration / quota) at any run → the
  photo goes ``falhou`` with the reason, the batch-ready check is
  enqueued (a failed photo never blocks the batch) and the job is
  dead-lettered.

Idempotency: every handler first reads the photo/batch state and returns
without side effects when the work is already done; every enqueue uses a
dedupe key; every status change is a compare-and-set.

Events never carry the AI verdict or costs: ``fotos_eventos`` is readable
by the corretor, who must never see either.

Econômico (W4): ``fotos.submit_openai_batch`` sends every ``pronta`` photo
of a batch as ONE provider batch (photos → ``em_lote_openai``, one
``fotos_lotes_openai`` row), ``fotos.poll_openai_batch`` polls it on the
5 / 15 / 30 min schedule and, once terminal, applies each item exactly like
a synchronous edit (same output path, cost at the batch discount). A
transient per-item failure sends the photo back to ``pronta`` for the next
provider batch ONCE; a second one (or a fatal one) fails the photo.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobHandler, Worker
from noctusai_lib.domain.photo_editing.costs import (
    CATEGORY_OPENAI_EDIT,
    CATEGORY_OPENAI_VISION,
    UnpricedModelError,
    backfill_fx,
    catalog_entry,
    record_ai_cost,
)
from noctusai_lib.domain.photo_editing.guide import (
    GuideNotActiveError,
    generate_draft_from_pool,
    resolve_effective_guide,
)
from noctusai_lib.domain.photo_editing.learning import InvalidModelOutputError, propose_rules
from noctusai_lib.domain.photo_editing.naming import (
    EDITED_NAME,
    ORIGINAL_NAME,
    STAGING_WATERMARK_TEXT,
    is_staged,
    storage_path,
)
from noctusai_lib.domain.photo_editing.pipeline import (
    SubmissionError,
    enqueue_batch_ready_check,
    enqueue_edit,
    enqueue_evaluation,
    enqueue_openai_batch_poll,
    enqueue_openai_batch_submit,
    enqueue_photo_work,
    schedule_guide_regen,
    schedule_rule_proposal,
    validate_submission,
)
from noctusai_lib.domain.photo_editing.ports import (
    BatchReadyNotice,
    PhotoEditingPorts,
    TokenUsage,
)
from noctusai_lib.domain.photo_editing.prompts import (
    render_edit_prompt,
    render_evaluator_prompt,
)
from noctusai_lib.domain.photo_editing.types import (
    PROCESSING_DONE_STATES,
    Batch,
    BatchStatus,
    Decision,
    EditAttempt,
    EditType,
    EffectiveGuide,
    IllegalTransitionError,
    JobType,
    OpenAIBatchRecord,
    OpenAIBatchStatus,
    OrgSettings,
    Photo,
    PhotoEvent,
    PhotoStatus,
    Speed,
)
from noctusai_lib.integrations.image_edit import (
    BatchEditItem,
    BatchItemResult,
    ImageEditError,
    ImageEditRequest,
    ImageEditResult,
    ImageEditTimeout,
)
from noctusai_lib.integrations.imaging import UnsupportedImageFormatError
from noctusai_lib.integrations.llm.exceptions import LLMAPIError, LLMNotConfigured
from noctusai_lib.primitives.image_sizing import compute_edit_size

logger = logging.getLogger(__name__)

_REASON_MAX = 500


class PhotoEditingConfigError(RuntimeError):
    """The engine is not configured to run this step — fatal."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class EditQuotaExceededError(RuntimeError):
    """The org's edit quota is exhausted — fatal for this attempt; a
    manual retry after the window resets runs it again."""

    code = "limite_de_uso_atingido"


_FATAL_TYPES: tuple[type[BaseException], ...] = (
    UnsupportedImageFormatError,
    UnpricedModelError,
    PhotoEditingConfigError,
    SubmissionError,
    GuideNotActiveError,
    EditQuotaExceededError,
    IllegalTransitionError,
    LLMNotConfigured,
    FileNotFoundError,
)


def is_retryable(exc: BaseException) -> bool:
    """The engine's single retryable-vs-fatal classifier."""
    if isinstance(exc, ImageEditError):
        return exc.retryable
    if isinstance(exc, (InvalidModelOutputError, LLMAPIError)):
        return True
    if isinstance(exc, _FATAL_TYPES):
        return False
    if isinstance(exc, ValueError):
        # compute_edit_size / validate_size refuse an impossible geometry.
        return False
    return True


def failure_reason(exc: BaseException) -> str:
    code = getattr(exc, "code", None) or type(exc).__name__
    return f"{code}: {exc}"[:_REASON_MAX]


def _payload(job: Job, key: str) -> str:
    value = job.payload.get(key)
    if not isinstance(value, str) or not value:
        raise DeadLetterError(f"job {job.id} ({job.type}) payload lacks {key!r}")
    return value


def _is_last_attempt(ports: PhotoEditingPorts, job: Job) -> bool:
    return job.retry_count >= ports.config.max_auto_retries


async def _fail_photo(ports: PhotoEditingPorts, photo_id: str, reason: str) -> None:
    photo = await ports.repo.get_photo(photo_id)
    if photo is None or photo.status in PROCESSING_DONE_STATES:
        return
    await ports.repo.transition_photo(
        photo_id, PhotoStatus.FALHOU, falha_motivo=reason, event_tipo="falha"
    )
    edit = await ports.repo.latest_edit(photo_id)
    if edit is not None and edit.status == "pendente":
        await ports.repo.update_edit(edit.id, status="falhou", erro=reason)
    await enqueue_batch_ready_check(ports, photo.lote_id)


async def _photo_step(
    ports: PhotoEditingPorts,
    job: Job,
    photo_id: str,
    body: Callable[[], Awaitable[None]],
) -> None:
    try:
        await body()
    except DeadLetterError:
        raise
    except Exception as exc:
        reason = failure_reason(exc)
        if is_retryable(exc) and not _is_last_attempt(ports, job):
            photo = await ports.repo.get_photo(photo_id)
            if photo is not None:
                await ports.repo.add_event(
                    PhotoEvent(
                        org_id=photo.org_id,
                        lote_id=photo.lote_id,
                        foto_id=photo_id,
                        tipo="falha_transitoria",
                        detalhe={"etapa": job.type, "erro": reason},
                    )
                )
            raise
        logger.warning(
            "photo_editing.photo_failed foto_id=%s job=%s reason=%s", photo_id, job.type, reason
        )
        await _fail_photo(ports, photo_id, reason)
        raise DeadLetterError(reason) from exc


async def _plain_step(body: Callable[[], Awaitable[None]]) -> None:
    try:
        await body()
    except DeadLetterError:
        raise
    except Exception as exc:
        if is_retryable(exc):
            raise
        raise DeadLetterError(failure_reason(exc)) from exc


async def _cpu(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(fn, *args, **kwargs)


async def _load_photo(ports: PhotoEditingPorts, job: Job) -> Photo:
    photo = await ports.repo.get_photo(_payload(job, "foto_id"))
    if photo is None:
        raise DeadLetterError(f"foto {job.payload.get('foto_id')} não existe")
    return photo


async def _load_batch(ports: PhotoEditingPorts, lote_id: str) -> Batch:
    batch = await ports.repo.get_batch(lote_id)
    if batch is None:
        raise DeadLetterError(f"lote {lote_id} não existe")
    return batch


async def _snapshot_guide(ports: PhotoEditingPorts, batch: Batch) -> EffectiveGuide:
    if not batch.guia_efetivo_id:
        raise PhotoEditingConfigError("guia_nao_congelado", f"lote {batch.id} sem guia efetivo")
    guide = await ports.repo.get_effective_guide(batch.guia_efetivo_id)
    if guide is None:
        raise PhotoEditingConfigError(
            "guia_nao_congelado", f"guia efetivo {batch.guia_efetivo_id} não existe"
        )
    return guide


async def _record_cost_or_note(
    ports: PhotoEditingPorts, photo: Photo, usage: TokenUsage | None, **kwargs: Any
) -> int | None:
    """Record the call's cost; when the provider path gave no usage, say
    so in an event instead of writing a fabricated $0."""
    if usage is None or not any(
        (
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.image_input_tokens,
            usage.image_output_tokens,
        )
    ):
        await ports.repo.add_event(
            PhotoEvent(
                org_id=photo.org_id,
                lote_id=photo.lote_id,
                foto_id=photo.id,
                tipo="custo_nao_registrado",
                detalhe={"etapa": kwargs.get("step"), "motivo": "uso_indisponivel"},
            )
        )
        return None
    recorded = await record_ai_cost(ports, org_id=photo.org_id, usage=usage, **kwargs)
    return recorded.llm_usage_id


# ---------------------------------------------------------------------------
# fotos.ingest
# ---------------------------------------------------------------------------


async def handle_ingest(ports: PhotoEditingPorts, job: Job) -> None:
    """Normalize the upload (HEIC→JPEG, EXIF transpose, sRGB, GPS strip),
    store it as the photo's original, delete the raw upload."""
    photo = await _load_photo(ports, job)

    async def body() -> None:
        current = photo
        if current.status is PhotoStatus.RECEBIDA:
            moved = await ports.repo.transition_photo(current.id, PhotoStatus.NORMALIZANDO)
            if moved is None:
                return
            current = moved
        elif current.status is not PhotoStatus.NORMALIZANDO:
            return  # already ingested
        settings = await ports.repo.get_org_settings(current.org_id) or OrgSettings(
            org_id=current.org_id
        )
        raw_path = current.storage_path_original
        raw = await ports.storage.get(raw_path)
        if len(raw) > settings.limite_bytes_por_foto:
            raise PhotoEditingConfigError("arquivo_grande_demais", f"{len(raw)} bytes")
        normalized = await _cpu(ports.imaging.normalize_for_edit, raw)
        final_path = storage_path(current.org_id, current.lote_id, current.id, ORIGINAL_NAME)
        await ports.storage.put(final_path, normalized.jpeg_bytes, content_type="image/jpeg")
        await ports.repo.update_photo(
            current.id,
            storage_path_original=final_path,
            largura_original=normalized.width,
            altura_original=normalized.height,
        )
        if raw_path != final_path:
            # LGPD: the raw upload may carry GPS EXIF — keep only the stripped copy.
            await ports.storage.delete(raw_path)
        ready = await ports.repo.transition_photo(
            current.id,
            PhotoStatus.PRONTA,
            detalhe={
                "formato_origem": normalized.source_format,
                "convertida": normalized.converted,
                "gps_removido": normalized.gps_stripped,
            },
        )
        if ready is None:
            return
        batch = await _load_batch(ports, ready.lote_id)
        if batch.status in (BatchStatus.SUBMETIDO, BatchStatus.PROCESSANDO):
            await enqueue_photo_work(ports, batch, ready)

    await _photo_step(ports, job, photo.id, body)


# ---------------------------------------------------------------------------
# fotos.submit_lote
# ---------------------------------------------------------------------------


async def handle_submit_lote(ports: PhotoEditingPorts, job: Job) -> None:
    """Move a submitted batch to ``processando`` and enqueue the edits of
    every photo already ingested (the rest are enqueued by their ingest)."""
    lote_id = _payload(job, "lote_id")

    async def body() -> None:
        batch = await _load_batch(ports, lote_id)
        if batch.status in (BatchStatus.RASCUNHO, BatchStatus.PRONTO):
            return  # not submitted via submit_batch / already finished
        plan = await validate_submission(ports, batch)
        if not batch.guia_efetivo_id:
            effective = await resolve_effective_guide(ports, batch.org_id)
            batch = await ports.repo.update_batch(
                lote_id,
                guia_efetivo_id=effective.id,
                guia_efetivo_sha256=effective.sha256,
            )
        if not batch.modelo_editor_id:
            batch = await ports.repo.update_batch(lote_id, modelo_editor_id=plan.model_id)
        if batch.status is BatchStatus.SUBMETIDO:
            batch = await ports.repo.update_batch(lote_id, status=BatchStatus.PROCESSANDO)
        if Speed(batch.velocidade) is Speed.ECONOMICO:
            # One provider batch for everything already ingested; photos still
            # ingesting re-enqueue it when they land (the handler waits).
            await enqueue_openai_batch_submit(ports, lote_id)
        else:
            for photo in plan.photos:
                if photo.status is PhotoStatus.PRONTA:
                    await enqueue_edit(ports, photo)
        await enqueue_batch_ready_check(ports, lote_id)

    await _plain_step(body)


# ---------------------------------------------------------------------------
# fotos.edit (Urgente)
# ---------------------------------------------------------------------------


async def handle_edit(ports: PhotoEditingPorts, job: Job) -> None:
    photo = await _load_photo(ports, job)

    async def body() -> None:
        current = photo
        if current.status is PhotoStatus.PRONTA:
            moved = await ports.repo.transition_photo(current.id, PhotoStatus.EDITANDO)
            if moved is None:
                return
            current = moved
        elif current.status is not PhotoStatus.EDITANDO:
            return  # already edited, failed, or not ingested yet
        batch = await _load_batch(ports, current.lote_id)
        model = batch.modelo_editor_id
        if not model:
            raise PhotoEditingConfigError("modelo_nao_configurado", f"lote {batch.id} sem modelo")
        settings = await ports.repo.get_org_settings(current.org_id)
        tipos = tuple(settings.tipos_edicao_ativos) if settings else ()
        if not tipos:
            raise PhotoEditingConfigError("sem_tipos_edicao", "nenhum tipo de edição ativo")
        guide = await _snapshot_guide(ports, batch)
        if current.largura_original is None or current.altura_original is None:
            raise PhotoEditingConfigError("foto_nao_normalizada", f"foto {current.id}")
        width, height = current.largura_original, current.altura_original
        catalog_entry(ports.config.image_edit_provider, model, "image_edit")  # fail before spend

        if ports.edit_quota is not None:
            check = await ports.edit_quota.consume(
                key=f"{ports.config.edit_quota_key_prefix}:{current.org_id}"
            )
            if not check.allowed:
                raise EditQuotaExceededError(
                    f"limite de edições atingido; libera em {check.reset_at.isoformat()}"
                )

        edit = await _pending_edit(
            ports, current, tipos=tipos, model=model, velocidade=batch.velocidade
        )

        original = await ports.storage.get(current.storage_path_original)
        edit_w, edit_h = compute_edit_size(width, height)
        edit_input = await _cpu(ports.imaging.resize, original, width=edit_w, height=edit_h)
        prompt = render_edit_prompt(
            tipos, guia_texto=guide.texto, guia_sha256=guide.sha256
        )
        adapter = ports.image_edit(current.org_id, model)
        result = await adapter.edit(
            ImageEditRequest(
                images=(edit_input,),
                prompt=prompt.text,
                size=f"{edit_w}x{edit_h}",
                # `extra` is forwarded to the provider VERBATIM — never put
                # engine metadata there (the prompt ref is recorded on the
                # `editada` transition event instead).
                request_id=f"{current.id}:{edit.id}",
            ),
            org_id=current.org_id,
        )
        await _store_edit_output(
            ports,
            current,
            edit,
            result,
            model=model,
            tipos=tipos,
            prompt_ref=prompt.ref,
            step=JobType.EDIT,
            batch=False,
        )

    await _photo_step(ports, job, photo.id, body)


async def _pending_edit(
    ports: PhotoEditingPorts,
    photo: Photo,
    *,
    tipos: tuple[EditType, ...],
    model: str,
    velocidade: Speed,
) -> EditAttempt:
    """The photo's open edit attempt for its current round — reused when a
    retried job re-enters, created otherwise."""
    edit = await ports.repo.latest_edit(photo.id)
    attempt_no = photo.tentativas + 1
    if edit is None or edit.tentativa != attempt_no or edit.status != "pendente":
        edit = await ports.repo.create_edit(
            org_id=photo.org_id,
            lote_id=photo.lote_id,
            foto_id=photo.id,
            tentativa=attempt_no,
            tipos_edicao=tipos,
            modelo_id=model,
            velocidade=velocidade,
        )
    return edit


async def _store_edit_output(
    ports: PhotoEditingPorts,
    photo: Photo,
    edit: EditAttempt,
    result: ImageEditResult,
    *,
    model: str,
    tipos: tuple[EditType, ...],
    prompt_ref: str,
    step: str,
    batch: bool,
) -> None:
    """Shared tail of an edit, synchronous or batch: record the cost, bring
    the output back to the input size, watermark staging, store, move the
    photo to ``editada`` and enqueue its evaluation."""
    if not result.images:
        raise InvalidModelOutputError("o modelo não devolveu imagem")
    if photo.largura_original is None or photo.altura_original is None:
        raise PhotoEditingConfigError("foto_nao_normalizada", f"foto {photo.id}")
    width, height = photo.largura_original, photo.altura_original

    entry = catalog_entry(ports.config.image_edit_provider, model, "image_edit")
    model_version = f"{model}{entry.snapshot}" if entry.snapshot else None
    usage_id = await _record_cost_or_note(
        ports,
        photo,
        TokenUsage(
            prompt_tokens=result.usage.prompt_tokens,
            image_input_tokens=result.usage.image_input_tokens,
            image_output_tokens=result.usage.image_output_tokens,
            total_tokens=result.usage.total_tokens,
        ),
        step=step,
        category=CATEGORY_OPENAI_EDIT,
        operation="image_edit",
        kind="image_edit",
        model=model,
        model_version=model_version,
        batch=batch,
    )

    # Back to the exact input size (Lanczos), JPEG — plus the visible
    # AI watermark when virtual staging was applied.
    output = await _cpu(
        ports.imaging.resize, result.images[0].image_bytes, width=width, height=height
    )
    if is_staged(tipos):
        output = await _cpu(ports.imaging.apply_watermark, output, text=STAGING_WATERMARK_TEXT)
    edited_path = storage_path(photo.org_id, photo.lote_id, photo.id, EDITED_NAME)
    await ports.storage.put(edited_path, output, content_type="image/jpeg")
    await ports.repo.update_edit(
        edit.id,
        status="concluida",
        llm_usage_id=usage_id,
        modelo_versao=model_version,
        concluida_at=ports.clock(),
    )
    await ports.repo.update_photo(photo.id, storage_path_editada=edited_path)
    done = await ports.repo.transition_photo(
        photo.id,
        PhotoStatus.EDITADA,
        detalhe={"edicao_id": edit.id, "prompt": prompt_ref},
    )
    if done is not None:
        await enqueue_evaluation(ports, photo.id, edit.id)


# ---------------------------------------------------------------------------
# fotos.submit_openai_batch / fotos.poll_openai_batch (Econômico)
# ---------------------------------------------------------------------------

_INGESTING = frozenset({PhotoStatus.RECEBIDA, PhotoStatus.NORMALIZANDO})


def _custom_id(foto_id: str, edicao_id: str) -> str:
    return f"{foto_id}:{edicao_id}"


async def _open_openai_batch(
    ports: PhotoEditingPorts, batch: Batch, model: str, ready: list[Photo]
) -> OpenAIBatchRecord | None:
    """Gate + price + guide checks (all before any spend), then one edit
    attempt per photo, the ``preparando`` record, and ``pronta →
    em_lote_openai``. Returns ``None`` when no photo is left to send."""
    settings = await ports.repo.get_org_settings(batch.org_id)
    tipos = tuple(settings.tipos_edicao_ativos) if settings else ()
    if not tipos:
        raise PhotoEditingConfigError("sem_tipos_edicao", "nenhum tipo de edição ativo")
    if not ports.capabilities(model).supports_batch:
        raise PhotoEditingConfigError(
            "economico_indisponivel", f"modelo {model} não suporta a Batch API"
        )
    catalog_entry(ports.config.image_edit_provider, model, "image_edit")  # fail before spend
    guide = await _snapshot_guide(ports, batch)
    prompt_ref = render_edit_prompt(tipos, guia_texto=guide.texto, guia_sha256=guide.sha256).ref

    itens: list[dict[str, Any]] = []
    for photo in ready:
        if ports.edit_quota is not None:
            check = await ports.edit_quota.consume(
                key=f"{ports.config.edit_quota_key_prefix}:{photo.org_id}"
            )
            if not check.allowed:
                await _fail_photo(
                    ports,
                    photo.id,
                    failure_reason(
                        EditQuotaExceededError(
                            f"limite de edições atingido; libera em {check.reset_at.isoformat()}"
                        )
                    ),
                )
                continue
        edit = await _pending_edit(
            ports, photo, tipos=tipos, model=model, velocidade=Speed.ECONOMICO
        )
        itens.append(
            {
                "foto_id": photo.id,
                "edicao_id": edit.id,
                "custom_id": _custom_id(photo.id, edit.id),
                "tentativas": photo.tentativas,
                "prompt": prompt_ref,
            }
        )
    if not itens:
        return None
    record = await ports.repo.create_openai_batch(
        org_id=batch.org_id, lote_id=batch.id, modelo_id=model, itens=tuple(itens)
    )
    for item in itens:
        # A photo a concurrent writer moved first is simply not sent
        # (`_send_openai_batch` skips anything not `em_lote_openai`).
        await ports.repo.transition_photo(
            item["foto_id"],
            PhotoStatus.EM_LOTE_OPENAI,
            detalhe={"lote_openai_id": record.id},
        )
    return record


async def _send_openai_batch(
    ports: PhotoEditingPorts, batch: Batch, record: OpenAIBatchRecord
) -> None:
    """Build the provider requests from the record and submit them. Safe to
    re-run from ``preparando`` (a crash or transient error before the
    provider confirmed): the requests are rebuilt deterministically."""
    guide = await _snapshot_guide(ports, batch)
    items: list[BatchEditItem] = []
    sent: list[str] = []
    for item in record.itens:
        photo = await ports.repo.get_photo(item["foto_id"])
        if photo is None or photo.status is not PhotoStatus.EM_LOTE_OPENAI:
            continue
        edit = await ports.repo.get_edit(item["edicao_id"])
        if edit is None:
            raise PhotoEditingConfigError("edicao_inexistente", item["edicao_id"])
        if photo.largura_original is None or photo.altura_original is None:
            raise PhotoEditingConfigError("foto_nao_normalizada", f"foto {photo.id}")
        original = await ports.storage.get(photo.storage_path_original)
        edit_w, edit_h = compute_edit_size(photo.largura_original, photo.altura_original)
        edit_input = await _cpu(ports.imaging.resize, original, width=edit_w, height=edit_h)
        prompt = render_edit_prompt(
            edit.tipos_edicao, guia_texto=guide.texto, guia_sha256=guide.sha256
        )
        items.append(
            BatchEditItem(
                custom_id=item["custom_id"],
                request=ImageEditRequest(
                    images=(edit_input,),
                    prompt=prompt.text,
                    size=f"{edit_w}x{edit_h}",
                    request_id=item["custom_id"],
                ),
            )
        )
        sent.append(photo.id)
    if not items:
        await ports.repo.update_openai_batch(
            record.id,
            status=OpenAIBatchStatus.FALHOU,
            erro="sem_itens: nenhuma foto do lote OpenAI continua aguardando envio",
            concluido_at=ports.clock(),
        )
        return
    adapter = ports.image_edit(record.org_id, record.modelo_id)
    submission = await adapter.submit_batch(
        items,
        org_id=record.org_id,
        metadata={"lote_id": record.lote_id, "lote_openai_id": record.id},
    )
    await ports.repo.update_openai_batch(
        record.id,
        status=OpenAIBatchStatus.ENVIADO,
        openai_batch_id=submission.batch_id,
        openai_status=submission.state.value,
        input_file_id=submission.input_file_id,
        submetido_at=ports.clock(),
        erro=None,
    )
    for foto_id in sent:
        await ports.repo.update_photo(foto_id, openai_batch_id=submission.batch_id)
    await ports.repo.add_event(
        PhotoEvent(
            org_id=record.org_id,
            lote_id=record.lote_id,
            tipo="lote_openai_enviado",
            detalhe={"lote_openai_id": record.id, "fotos": len(items), "modelo": record.modelo_id},
        )
    )
    await enqueue_openai_batch_poll(ports, record.id, 0)


async def handle_submit_openai_batch(ports: PhotoEditingPorts, job: Job) -> None:
    """Send an Econômico batch's ``pronta`` photos as ONE provider batch.

    Waits (returns) while any photo is still being ingested — the last
    ingest re-enqueues this job. A ``preparando`` record (a previous run
    moved the photos but the provider never confirmed) is resumed first.
    Transient failure → retried once; final failure → every involved photo
    ``falhou`` and the record ``falhou``.
    """
    lote_id = _payload(job, "lote_id")
    involved: list[str] = []
    state: dict[str, Any] = {}

    async def body() -> None:
        batch = await _load_batch(ports, lote_id)
        state["batch"] = batch
        if batch.status not in (BatchStatus.SUBMETIDO, BatchStatus.PROCESSANDO):
            return
        if Speed(batch.velocidade) is not Speed.ECONOMICO:
            return
        photos = await ports.repo.list_photos(lote_id)
        if any(p.status in _INGESTING for p in photos):
            return
        records = await ports.repo.list_openai_batches(lote_id)
        record = next((r for r in records if r.status is OpenAIBatchStatus.PREPARANDO), None)
        if record is None:
            ready = [p for p in photos if p.status is PhotoStatus.PRONTA]
            if not ready:
                return
            involved[:] = [p.id for p in ready]
            model = batch.modelo_editor_id
            if not model:
                raise PhotoEditingConfigError(
                    "modelo_nao_configurado", f"lote {batch.id} sem modelo"
                )
            record = await _open_openai_batch(ports, batch, model, ready)
            if record is None:
                return
        state["record"] = record
        involved[:] = [item["foto_id"] for item in record.itens]
        await _send_openai_batch(ports, batch, record)

    try:
        await body()
    except DeadLetterError:
        raise
    except Exception as exc:
        reason = failure_reason(exc)
        batch = state.get("batch")
        if is_retryable(exc) and not _is_last_attempt(ports, job):
            if batch is not None:
                await ports.repo.add_event(
                    PhotoEvent(
                        org_id=batch.org_id,
                        lote_id=lote_id,
                        tipo="falha_transitoria",
                        detalhe={"etapa": job.type, "erro": reason},
                    )
                )
            raise
        logger.warning(
            "photo_editing.openai_batch_submit_failed lote_id=%s reason=%s", lote_id, reason
        )
        record = state.get("record")
        if record is not None:
            await ports.repo.update_openai_batch(
                record.id,
                status=OpenAIBatchStatus.FALHOU,
                erro=reason,
                concluido_at=ports.clock(),
            )
        for foto_id in involved:
            await _fail_photo(ports, foto_id, reason)
        raise DeadLetterError(reason) from exc


async def _fail_record_photos(
    ports: PhotoEditingPorts, record: OpenAIBatchRecord, reason: str
) -> None:
    for item in record.itens:
        photo = await ports.repo.get_photo(item["foto_id"])
        if photo is not None and photo.status is PhotoStatus.EM_LOTE_OPENAI:
            await _fail_photo(ports, photo.id, reason)
    await ports.repo.update_openai_batch(
        record.id, status=OpenAIBatchStatus.FALHOU, erro=reason, concluido_at=ports.clock()
    )


def _tries_of(records: list[OpenAIBatchRecord], item: dict[str, Any]) -> int:
    """How many provider batches carried this photo in this attempt round."""
    return sum(
        1
        for r in records
        for i in r.itens
        if i.get("foto_id") == item["foto_id"] and i.get("tentativas") == item.get("tentativas")
    )


async def _apply_openai_batch_results(
    ports: PhotoEditingPorts,
    job: Job,
    record: OpenAIBatchRecord,
    results: tuple[BatchItemResult, ...],
) -> None:
    by_id = {r.custom_id: r for r in results}
    records = await ports.repo.list_openai_batches(record.lote_id)
    resubmit = False
    for item in record.itens:
        photo = await ports.repo.get_photo(item["foto_id"])
        if photo is None or photo.status is not PhotoStatus.EM_LOTE_OPENAI:
            continue  # already applied (re-run) or moved by someone else
        outcome = by_id.get(item["custom_id"])
        error: BaseException
        if outcome is None:
            error = ImageEditTimeout("item ausente no resultado do lote OpenAI")
        elif outcome.error is not None:
            error = outcome.error
        else:
            try:
                edit = await ports.repo.get_edit(item["edicao_id"])
                if edit is None:
                    raise PhotoEditingConfigError("edicao_inexistente", item["edicao_id"])
                await _store_edit_output(
                    ports,
                    photo,
                    edit,
                    outcome.result,
                    model=record.modelo_id,
                    tipos=tuple(edit.tipos_edicao),
                    prompt_ref=str(item.get("prompt") or ""),
                    step=JobType.POLL_OPENAI_BATCH,
                    batch=True,
                )
                continue
            except Exception as exc:
                if is_retryable(exc) and not _is_last_attempt(ports, job):
                    raise  # the whole poll re-runs; applied photos are skipped
                error = exc
        reason = failure_reason(error)
        if is_retryable(error) and _tries_of(records, item) <= ports.config.max_auto_retries:
            edit = await ports.repo.get_edit(item["edicao_id"])
            if edit is not None and edit.status == "pendente":
                await ports.repo.update_edit(edit.id, status="falhou", erro=reason)
            moved = await ports.repo.transition_photo(
                photo.id,
                PhotoStatus.PRONTA,
                event_tipo="falha_transitoria",
                detalhe={"etapa": job.type, "erro": reason},
            )
            resubmit = resubmit or moved is not None
        else:
            logger.warning(
                "photo_editing.photo_failed foto_id=%s job=%s reason=%s",
                photo.id,
                job.type,
                reason,
            )
            await _fail_photo(ports, photo.id, reason)
    await ports.repo.update_openai_batch(
        record.id, status=OpenAIBatchStatus.CONCLUIDO, concluido_at=ports.clock()
    )
    if resubmit:
        await enqueue_openai_batch_submit(ports, record.lote_id)
    await enqueue_batch_ready_check(ports, record.lote_id)


async def handle_poll_openai_batch(ports: PhotoEditingPorts, job: Job) -> None:
    """Poll one provider batch; reschedule (5 / 15 / 30 min) until terminal,
    then apply its results. A failing POLL never strands the batch: a
    transient error reschedules the next poll, and past
    ``openai_batch_max_wait_seconds`` every waiting photo fails."""
    lote_openai_id = _payload(job, "lote_openai_id")
    consulta = job.payload.get("consulta")
    if not isinstance(consulta, int) or consulta < 0:
        raise DeadLetterError(f"job {job.id} ({job.type}) payload lacks 'consulta'")
    record = await ports.repo.get_openai_batch(lote_openai_id)
    if record is None:
        raise DeadLetterError(f"lote openai {lote_openai_id} não existe")
    if record.status is not OpenAIBatchStatus.ENVIADO or not record.openai_batch_id:
        return  # already applied / failed — idempotent
    now = ports.clock()
    overdue = (
        record.submetido_at is not None
        and (now - record.submetido_at).total_seconds() > ports.config.openai_batch_max_wait_seconds
    )
    try:
        adapter = ports.image_edit(record.org_id, record.modelo_id)
        polled = await adapter.poll_batch(record.openai_batch_id, org_id=record.org_id)
        await ports.repo.update_openai_batch(
            record.id,
            openai_status=polled.state.value,
            output_file_id=polled.output_file_id,
            error_file_id=polled.error_file_id,
            consultas=consulta + 1,
        )
        if not polled.state.is_terminal:
            if overdue:
                await _fail_record_photos(
                    ports,
                    record,
                    f"lote_openai_prazo_excedido: {polled.state.value} após "
                    f"{ports.config.openai_batch_max_wait_seconds}s",
                )
                await enqueue_batch_ready_check(ports, record.lote_id)
                return
            await enqueue_openai_batch_poll(ports, record.id, consulta + 1)
            return
        results = await adapter.fetch_batch_results(record.openai_batch_id, org_id=record.org_id)
    except DeadLetterError:
        raise
    except Exception as exc:
        reason = failure_reason(exc)
        if is_retryable(exc) and not overdue:
            logger.warning(
                "photo_editing.openai_batch_poll_retry lote_openai_id=%s reason=%s",
                record.id,
                reason,
            )
            await ports.repo.update_openai_batch(record.id, consultas=consulta + 1, erro=reason)
            await enqueue_openai_batch_poll(ports, record.id, consulta + 1)
            return
        await _fail_record_photos(ports, record, reason)
        await enqueue_batch_ready_check(ports, record.lote_id)
        raise DeadLetterError(reason) from exc
    await _apply_openai_batch_results(ports, job, record, results)


# ---------------------------------------------------------------------------
# fotos.avaliar
# ---------------------------------------------------------------------------


def parse_evaluation(data: dict[str, Any]) -> tuple[Decision, Decimal, str, bool]:
    """Validate the evaluator's JSON. Structural infidelity FORCES
    ``rejeitar`` regardless of what the model recommended."""
    try:
        recomendacao = Decision(data["recomendacao"])
        score = Decimal(str(data["score"]))
        motivo = data["motivo"]
        fiel = data["fidelidade_estrutural"]
    except (KeyError, ValueError, InvalidOperation) as exc:
        raise InvalidModelOutputError(f"avaliação inválida: {exc}") from exc
    if not isinstance(motivo, str) or not isinstance(fiel, bool):
        raise InvalidModelOutputError("avaliação inválida: tipos")
    if not (Decimal(0) <= score <= Decimal(10)):
        raise InvalidModelOutputError(f"score fora de 0-10: {score}")
    score = score.quantize(Decimal("0.01"))
    if not fiel and recomendacao is Decision.APROVAR:
        recomendacao = Decision.REJEITAR
        motivo = f"[estrutura alterada] {motivo}"
    return recomendacao, score, motivo, fiel


async def handle_avaliar(ports: PhotoEditingPorts, job: Job) -> None:
    photo = await _load_photo(ports, job)
    edicao_id = _payload(job, "edicao_id")

    async def body() -> None:
        current = photo
        if current.status is PhotoStatus.EDITADA:
            moved = await ports.repo.transition_photo(current.id, PhotoStatus.AVALIANDO)
            if moved is None:
                return
            current = moved
        elif current.status is not PhotoStatus.AVALIANDO:
            return
        edit = await ports.repo.get_edit(edicao_id)
        if edit is None:
            raise PhotoEditingConfigError("edicao_inexistente", edicao_id)
        batch = await _load_batch(ports, current.lote_id)
        guide = await _snapshot_guide(ports, batch)
        if not current.storage_path_editada:
            raise PhotoEditingConfigError("sem_imagem_editada", current.id)
        original = await ports.storage.get(current.storage_path_original)
        edited = await ports.storage.get(current.storage_path_editada)
        prompt = render_evaluator_prompt(edit.tipos_edicao, guia_texto=guide.texto)
        model = ports.config.evaluator_model
        catalog_entry(ports.config.llm_provider, model, "vision")  # fail before spend
        result = await ports.llm.analyze(
            images=[original, edited],
            prompt=prompt.text,
            response_schema=prompt.response_schema or {},
            model=model,
            org_id=current.org_id,
            schema_name="avaliacao_foto",
        )
        recomendacao, score, motivo, _fiel = parse_evaluation(result.data)
        await _record_cost_or_note(
            ports,
            current,
            result.usage,
            step=JobType.AVALIAR,
            category=CATEGORY_OPENAI_VISION,
            operation="vision",
            kind="vision",
            model=model,
            model_version=result.model_version,
        )
        evaluation = await ports.repo.add_evaluation(
            org_id=current.org_id,
            lote_id=current.lote_id,
            foto_id=current.id,
            edicao_id=edit.id,
            recomendacao=recomendacao,
            score=score,
            motivo=motivo,
            modelo_id=model,
            modelo_versao=result.model_version,
        )
        done = await ports.repo.transition_photo(
            current.id,
            PhotoStatus.AGUARDANDO_DECISAO,
            detalhe={"avaliacao_id": evaluation.id, "prompt": prompt.ref},
        )
        if done is not None:
            await enqueue_batch_ready_check(ports, current.lote_id)

    await _photo_step(ports, job, photo.id, body)


# ---------------------------------------------------------------------------
# fotos.lote_pronto
# ---------------------------------------------------------------------------


async def handle_lote_pronto(ports: PhotoEditingPorts, job: Job) -> None:
    lote_id = _payload(job, "lote_id")

    async def body() -> None:
        batch = await _load_batch(ports, lote_id)
        if batch.status is not BatchStatus.PROCESSANDO:
            return
        photos = await ports.repo.list_photos(lote_id)
        if not photos or any(p.status not in PROCESSING_DONE_STATES for p in photos):
            return
        falhou = sum(1 for p in photos if p.status is PhotoStatus.FALHOU)
        notice = BatchReadyNotice(
            lote_id=batch.id,
            org_id=batch.org_id,
            criado_por=batch.criado_por,
            nome=batch.nome,
            total_fotos=len(photos),
            aguardando_decisao=sum(
                1 for p in photos if p.status is PhotoStatus.AGUARDANDO_DECISAO
            ),
            falhou=falhou,
        )
        platform = await ports.repo.get_platform_settings()
        settings = await ports.repo.get_org_settings(batch.org_id)
        enabled = platform.notificacoes_globais_ativas and (
            settings is None or settings.notificacoes_ativas
        )
        # Notify BEFORE flipping the status: a crash in between re-notifies
        # (at-least-once) rather than silently never notifying.
        if enabled:
            await ports.notifier.batch_ready(notice)
        await ports.repo.update_batch(
            lote_id, status=BatchStatus.PRONTO, pronto_at=ports.clock()
        )
        await ports.repo.add_event(
            PhotoEvent(
                org_id=batch.org_id,
                lote_id=lote_id,
                tipo="lote_pronto",
                detalhe={
                    "fotos": len(photos),
                    "falhou": falhou,
                    "notificado": enabled,
                },
            )
        )

    await _plain_step(body)


# ---------------------------------------------------------------------------
# fotos.regen_guia / fotos.propor_regras (trailing debounce)
# ---------------------------------------------------------------------------


async def handle_regen_guia(ports: PhotoEditingPorts, job: Job) -> None:
    # A manual request (``pool.request_guide_regen``) runs now; only the
    # automatic, pool-change-triggered run waits for the pool to settle.
    manual = bool((job.payload or {}).get("manual"))

    async def body() -> None:
        now = ports.clock()
        window = ports.config.guide_regen_debounce_seconds
        last = await ports.repo.last_pool_change_at()
        if not manual and last is not None and (now - last).total_seconds() < window:
            await schedule_guide_regen(ports)  # pool still settling
            return
        await generate_draft_from_pool(ports)

    await _plain_step(body)


async def handle_propor_regras(ports: PhotoEditingPorts, job: Job) -> None:
    org_id = _payload(job, "org_id")

    async def body() -> None:
        now = ports.clock()
        window = ports.config.rule_proposal_debounce_seconds
        cursor = await ports.repo.get_cursor(org_id)
        pending = await ports.repo.list_rejections(
            org_id,
            after=cursor.ultima_execucao_em if cursor else None,
            limit=ports.config.max_rejections_per_proposal,
        )
        if not pending:
            return
        newest = pending[-1].created_at
        if newest is not None and (now - newest).total_seconds() < window:
            await schedule_rule_proposal(ports, org_id)  # rejections still arriving
            return
        await propose_rules(ports, org_id)

    await _plain_step(body)


# ---------------------------------------------------------------------------
# fotos.fx_backfill
# ---------------------------------------------------------------------------


async def handle_fx_backfill(ports: PhotoEditingPorts, job: Job) -> None:
    async def body() -> None:
        report = await backfill_fx(ports)
        logger.info(
            "photo_editing.fx_backfill resolved=%d still_pending=%d",
            report.resolved,
            report.still_pending,
        )

    await _plain_step(body)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

HandlerFn = Callable[[PhotoEditingPorts, Job], Awaitable[None]]

HANDLERS: dict[str, HandlerFn] = {
    JobType.INGEST: handle_ingest,
    JobType.SUBMIT_LOTE: handle_submit_lote,
    JobType.EDIT: handle_edit,
    JobType.AVALIAR: handle_avaliar,
    JobType.LOTE_PRONTO: handle_lote_pronto,
    JobType.REGEN_GUIA: handle_regen_guia,
    JobType.PROPOR_REGRAS: handle_propor_regras,
    JobType.FX_BACKFILL: handle_fx_backfill,
    JobType.SUBMIT_OPENAI_BATCH: handle_submit_openai_batch,
    JobType.POLL_OPENAI_BATCH: handle_poll_openai_batch,
}


def build_handlers(ports: PhotoEditingPorts) -> dict[str, JobHandler]:
    def bind(fn: HandlerFn) -> JobHandler:
        async def _handler(job: Job) -> None:
            await fn(ports, job)

        _handler.__name__ = fn.__name__
        return _handler

    return {job_type: bind(fn) for job_type, fn in HANDLERS.items()}


def build_worker(
    ports: PhotoEditingPorts,
    *,
    worker_id: str,
    poll_interval_seconds: float = 1.0,
    lease_seconds: float = 600.0,
) -> Worker:
    return Worker(
        ports.jobs,
        worker_id=worker_id,
        handlers=build_handlers(ports),
        retry_policy=ports.config.retry_policy(),
        poll_interval_seconds=poll_interval_seconds,
        lease_seconds=lease_seconds,
    )


__all__ = [
    "EditQuotaExceededError",
    "HANDLERS",
    "HandlerFn",
    "PhotoEditingConfigError",
    "build_handlers",
    "build_worker",
    "failure_reason",
    "handle_avaliar",
    "handle_edit",
    "handle_fx_backfill",
    "handle_ingest",
    "handle_lote_pronto",
    "handle_poll_openai_batch",
    "handle_propor_regras",
    "handle_regen_guia",
    "handle_submit_lote",
    "handle_submit_openai_batch",
    "is_retryable",
    "parse_evaluation",
]
