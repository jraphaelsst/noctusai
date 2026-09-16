"""Synchronous pipeline entry points + job enqueueing.

What a consumer's ROUTES call (the handlers in ``handlers.py`` are what its
WORKER calls):

- ``add_photo_bytes``   — store an upload, register the photo, enqueue ingest.
- ``submit_batch``      — validate, snapshot the effective guide, enqueue.
- ``retry_photo``       — manual retry of a ``falhou`` photo.
- ``schedule_guide_regen`` / ``schedule_rule_proposal`` — trailing debounce.
- ``request_guide_regen`` — manual guide rebuild (runs now).
- ``enqueue_fx_backfill`` — daily PTAX backfill.

Speed routing (``enqueue_photo_work``): an Urgente photo gets its own
``fotos.edit`` job; an Econômico photo joins the batch's next provider batch
(``fotos.submit_openai_batch``), which ``fotos.poll_openai_batch`` then
follows on the 5 / 15 / 30 min schedule. The Econômico gate is
``ports.capabilities(model).supports_batch`` — nothing else.

Every enqueue carries a dedupe key (``types.dedupe_*``), so a double click,
a retried request or a re-run handler never creates a second job.
Validation errors carry a ``code`` the consumer maps to its error envelope.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from noctusai_lib.domain.jobs import Job
from noctusai_lib.domain.photo_editing.guide import resolve_effective_guide
from noctusai_lib.domain.photo_editing.naming import upload_path
from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts
from noctusai_lib.domain.photo_editing.steps import resolve_rule_proposer_tunables
from noctusai_lib.domain.photo_editing.types import (
    Batch,
    BatchStatus,
    EditType,
    JobType,
    OrgSettings,
    Photo,
    PhotoEvent,
    PhotoStatus,
    Speed,
    batch_state_signature,
    debounce_bucket,
    dedupe_avaliar,
    dedupe_edit,
    dedupe_fx_backfill,
    dedupe_ingest,
    dedupe_lote_pronto,
    dedupe_notas_modelos,
    dedupe_poll_openai_batch,
    dedupe_propor_regras,
    dedupe_propor_regras_manual,
    dedupe_regen_guia,
    dedupe_regen_guia_manual,
    dedupe_submit,
    dedupe_submit_openai_batch,
)

#: The Econômico (Batch API) engine path exists (W4, resolves PROJECT.md C8).
#: Kept as a public constant for consumers that imported it; whether a given
#: org can USE Econômico is decided by ``ports.capabilities`` alone.
ECONOMICO_IMPLEMENTED = True

_UPLOAD_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "heic": "image/heic",
    "heif": "image/heif",
    "webp": "image/webp",
}


class SubmissionError(ValueError):
    """A batch cannot be submitted / extended. ``code`` is the API code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PhotoNotRetryableError(RuntimeError):
    code = "foto_nao_falhou"


class NotFoundError(LookupError):
    code = "nao_encontrado"


# ---------------------------------------------------------------------------
# Enqueue helpers
# ---------------------------------------------------------------------------


async def _enqueue(
    ports: PhotoEditingPorts,
    job_type: str,
    payload: dict,
    dedupe_key: str,
    *,
    scheduled_for: datetime | None = None,
) -> Job:
    return await ports.jobs.enqueue(
        type=job_type,
        payload=payload,
        max_retries=ports.config.max_auto_retries,
        scheduled_for=scheduled_for,
        dedupe_key=dedupe_key,
    )


async def enqueue_ingest(ports: PhotoEditingPorts, photo: Photo) -> Job:
    return await _enqueue(
        ports, JobType.INGEST, {"foto_id": photo.id}, dedupe_ingest(photo.id, photo.tentativas)
    )


async def enqueue_edit(ports: PhotoEditingPorts, photo: Photo) -> Job:
    return await _enqueue(
        ports, JobType.EDIT, {"foto_id": photo.id}, dedupe_edit(photo.id, photo.tentativas)
    )


async def enqueue_evaluation(ports: PhotoEditingPorts, foto_id: str, edicao_id: str) -> Job:
    return await _enqueue(
        ports,
        JobType.AVALIAR,
        {"foto_id": foto_id, "edicao_id": edicao_id},
        dedupe_avaliar(foto_id, edicao_id),
    )


async def enqueue_batch_ready_check(ports: PhotoEditingPorts, lote_id: str) -> Job:
    photos = await ports.repo.list_photos(lote_id)
    return await _enqueue(
        ports,
        JobType.LOTE_PRONTO,
        {"lote_id": lote_id},
        dedupe_lote_pronto(lote_id, batch_state_signature(photos)),
    )


async def enqueue_openai_batch_submit(ports: PhotoEditingPorts, lote_id: str) -> Job:
    """Ask for the batch's ready photos to be sent as ONE provider batch.
    Keyed by the batch state AND the number of provider batches already
    opened for it: every ingest / retry that changes the photo set may
    enqueue it, duplicates from one state collapse, and an automatic retry
    (photos back to the SAME ``pronta`` state as the first round) still gets
    a fresh key."""
    photos = await ports.repo.list_photos(lote_id)
    rounds = len(await ports.repo.list_openai_batches(lote_id))
    return await _enqueue(
        ports,
        JobType.SUBMIT_OPENAI_BATCH,
        {"lote_id": lote_id},
        dedupe_submit_openai_batch(lote_id, f"{batch_state_signature(photos)}:{rounds}"),
    )


async def enqueue_openai_batch_poll(
    ports: PhotoEditingPorts, lote_openai_id: str, consulta: int
) -> Job:
    """Schedule poll number ``consulta`` (0-based) of one provider batch,
    ``config.poll_delay_seconds(consulta)`` from now."""
    delay = ports.config.poll_delay_seconds(consulta)
    return await _enqueue(
        ports,
        JobType.POLL_OPENAI_BATCH,
        {"lote_openai_id": lote_openai_id, "consulta": consulta},
        dedupe_poll_openai_batch(lote_openai_id, consulta),
        scheduled_for=ports.clock() + timedelta(seconds=delay),
    )


async def enqueue_photo_work(ports: PhotoEditingPorts, batch: Batch, photo: Photo) -> Job:
    """Route a ``pronta`` photo by the batch's speed."""
    if Speed(batch.velocidade) is Speed.ECONOMICO:
        return await enqueue_openai_batch_submit(ports, batch.id)
    return await enqueue_edit(ports, photo)


def _window_end(at: datetime, window_seconds: int) -> datetime:
    bucket = debounce_bucket(at, window_seconds)
    return datetime.fromtimestamp((bucket + 1) * window_seconds, tz=timezone.utc)


async def schedule_guide_regen(ports: PhotoEditingPorts) -> Job:
    """Trailing debounce: one job per window, run at the window's end; the
    handler re-schedules itself while the pool is still changing."""
    now = ports.clock()
    window = ports.config.guide_regen_debounce_seconds
    return await _enqueue(
        ports,
        JobType.REGEN_GUIA,
        {},
        dedupe_regen_guia(debounce_bucket(now, window)),
        scheduled_for=_window_end(now, window),
    )


#: Double-click window for the manual "regenerate guide" button.
MANUAL_REGEN_WINDOW_SECONDS = 60


class PoolEmptyError(RuntimeError):
    """No active reference pair — there is nothing to build a guide from."""

    code = "pool_vazio"


async def request_guide_regen(ports: PhotoEditingPorts, *, requested_by: str) -> Job:
    """Manual rebuild: enqueue ``fotos.regen_guia`` to run NOW (the handler
    skips the pool-settling debounce for ``manual`` payloads). The result is
    a DRAFT that still needs activation. Refuses on an empty pool."""
    if await ports.repo.count_active_references() == 0:
        raise PoolEmptyError("o pool de referências está vazio")
    now = ports.clock()
    return await _enqueue(
        ports,
        JobType.REGEN_GUIA,
        {"manual": True, "por": requested_by},
        dedupe_regen_guia_manual(debounce_bucket(now, MANUAL_REGEN_WINDOW_SECONDS)),
    )


async def schedule_rule_proposal(ports: PhotoEditingPorts, org_id: str) -> Job:
    now = ports.clock()
    window, _limit = await resolve_rule_proposer_tunables(ports)
    return await _enqueue(
        ports,
        JobType.PROPOR_REGRAS,
        {"org_id": org_id},
        dedupe_propor_regras(org_id, debounce_bucket(now, window)),
        scheduled_for=_window_end(now, window),
    )


async def request_rule_proposal(ports: PhotoEditingPorts, org_id: str, *, requested_by: str) -> Job:
    """Manual "propor agora" button (W7): enqueue ``fotos.propor_regras`` to
    run NOW — the handler skips the rejection-settling debounce for
    ``manual`` payloads (mirrors :func:`request_guide_regen`). A double
    click within the window enqueues once. Unlike the guide's manual
    rebuild, an empty rejection queue is not refused — the handler already
    no-ops on nothing pending."""
    now = ports.clock()
    return await _enqueue(
        ports,
        JobType.PROPOR_REGRAS,
        {"org_id": org_id, "manual": True, "por": requested_by},
        dedupe_propor_regras_manual(org_id, debounce_bucket(now, MANUAL_REGEN_WINDOW_SECONDS)),
    )


async def enqueue_fx_backfill(
    ports: PhotoEditingPorts, day: date, *, dedupe_suffix: str | None = None
) -> Job:
    """One backfill per day by default; a scheduler that runs several times
    a day passes ``dedupe_suffix`` (e.g. the hour) to get one per run."""
    key = dedupe_fx_backfill(day.isoformat())
    if dedupe_suffix:
        key = f"{key}:{dedupe_suffix}"
    return await _enqueue(ports, JobType.FX_BACKFILL, {"dia": day.isoformat()}, key)


#: Manual "rewrite notes now" button: one job per window (double click = one).
MANUAL_NOTES_WINDOW_SECONDS = 60


async def enqueue_model_notes(
    ports: PhotoEditingPorts, *, slot: datetime | None = None
) -> Job:
    """Queue ``fotos.notas_modelos``.

    ``slot`` = the scheduled run this job belongs to (a timezone-aware
    instant): dedupe-keyed on its São Paulo date, so the cron path and a
    startup catch-up for the same slot collapse to ONE job, and the handler
    skips models noted since ``slot``. ``slot=None`` = a manual run that
    rewrites every note (short-window dedupe)."""
    if slot is None:
        bucket = debounce_bucket(ports.clock(), MANUAL_NOTES_WINDOW_SECONDS)
        return await _enqueue(
            ports,
            JobType.NOTAS_MODELOS,
            {"manual": True},
            f"{dedupe_notas_modelos('manual')}:{bucket}",
        )
    if slot.tzinfo is None:
        raise ValueError("slot must be timezone-aware")
    day = slot.astimezone(ZoneInfo(ports.config.fx_timezone)).date().isoformat()
    return await _enqueue(
        ports,
        JobType.NOTAS_MODELOS,
        {"desde": slot.isoformat(), "manual": False},
        dedupe_notas_modelos(day),
    )


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


async def _require_batch(ports: PhotoEditingPorts, lote_id: str) -> Batch:
    batch = await ports.repo.get_batch(lote_id)
    if batch is None:
        raise NotFoundError(f"lote {lote_id} não encontrado")
    return batch


async def _require_settings(ports: PhotoEditingPorts, org_id: str) -> OrgSettings:
    settings = await ports.repo.get_org_settings(org_id)
    return settings if settings is not None else OrgSettings(org_id=org_id)


async def add_photo_bytes(
    ports: PhotoEditingPorts,
    *,
    lote_id: str,
    data: bytes,
    extension: str,
    ordem: int | None = None,
    vista_codigo: str | None = None,
) -> Photo:
    """Store one upload (or a Vista-pulled photo) and enqueue its ingest.

    ``ordem`` defaults to "next in upload order"; a route receiving several
    files in one request should pass each file's index so concurrent
    inserts cannot collide on ``UNIQUE (lote_id, ordem)``.
    The raw bytes land under a throw-away token folder and are deleted by
    ingest once the normalized (GPS-stripped) copy exists.
    """
    batch = await _require_batch(ports, lote_id)
    if batch.status is not BatchStatus.RASCUNHO:
        raise SubmissionError("lote_ja_submetido", "o lote já foi submetido")
    settings = await _require_settings(ports, batch.org_id)
    if not data:
        raise SubmissionError("arquivo_vazio", "arquivo vazio")
    if len(data) > settings.limite_bytes_por_foto:
        raise SubmissionError(
            "arquivo_grande_demais",
            f"arquivo acima de {settings.limite_bytes_por_foto} bytes",
        )
    existing = await ports.repo.list_photos(lote_id)
    if len(existing) >= settings.limite_fotos_por_lote:
        raise SubmissionError(
            "lote_cheio", f"limite de {settings.limite_fotos_por_lote} fotos por lote"
        )
    ext = extension.lower().lstrip(".")
    content_type = _UPLOAD_CONTENT_TYPES.get(ext)
    if content_type is None:
        raise SubmissionError("formato_nao_suportado", f"formato .{ext} não suportado")
    path = upload_path(batch.org_id, lote_id, f"u-{uuid.uuid4().hex}", ext)
    await ports.storage.put(path, data, content_type=content_type)
    photo = await ports.repo.add_photo(
        org_id=batch.org_id,
        lote_id=lote_id,
        ordem=ordem if ordem is not None else (max((p.ordem for p in existing), default=0) + 1),
        storage_path_original=path,
        vista_codigo=vista_codigo,
    )
    await enqueue_ingest(ports, photo)
    return photo


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmissionPlan:
    batch: Batch
    settings: OrgSettings
    model_id: str
    tipos: tuple[EditType, ...]
    photos: list[Photo]


async def validate_submission(ports: PhotoEditingPorts, batch: Batch) -> SubmissionPlan:
    """Every precondition for running a batch. Raises ``SubmissionError``."""
    settings = await _require_settings(ports, batch.org_id)
    if not settings.modelo_editor_id:
        raise SubmissionError(
            "modelo_nao_configurado", "nenhum modelo de edição configurado para a organização"
        )
    caps = ports.capabilities(settings.modelo_editor_id)
    if not caps.known:
        raise SubmissionError(
            "modelo_desconhecido", f"modelo {settings.modelo_editor_id} não está no catálogo"
        )
    if not caps.priced:
        # Refused BEFORE any job exists: an unpriced model would only fail
        # later, per photo, after the upload round-trip (W8).
        raise SubmissionError(
            "modelo_sem_preco", f"modelo {settings.modelo_editor_id} não tem preço cadastrado"
        )
    if not settings.tipos_edicao_ativos:
        raise SubmissionError("sem_tipos_edicao", "nenhum tipo de edição ativo")
    if Speed(batch.velocidade) is Speed.ECONOMICO and not caps.supports_batch:
        raise SubmissionError("economico_indisponivel", "modo Econômico indisponível")
    photos = await ports.repo.list_photos(batch.id)
    if not photos:
        raise SubmissionError("lote_vazio", "o lote não tem fotos")
    if len(photos) > settings.limite_fotos_por_lote:
        raise SubmissionError(
            "lote_cheio", f"limite de {settings.limite_fotos_por_lote} fotos por lote"
        )
    return SubmissionPlan(
        batch=batch,
        settings=settings,
        model_id=settings.modelo_editor_id,
        tipos=tuple(settings.tipos_edicao_ativos),
        photos=photos,
    )


async def submit_batch(ports: PhotoEditingPorts, lote_id: str, *, submitted_by: str) -> Batch:
    """Route-side submit: validate, SNAPSHOT the effective guide + editor
    model onto the batch, mark it ``submetido`` and enqueue the pipeline.
    Idempotent: re-submitting an already-submitted batch re-enqueues under
    the same dedupe key (a no-op) and returns it unchanged."""
    batch = await _require_batch(ports, lote_id)
    if batch.status is not BatchStatus.RASCUNHO:
        await _enqueue(ports, JobType.SUBMIT_LOTE, {"lote_id": lote_id}, dedupe_submit(lote_id))
        return batch
    plan = await validate_submission(ports, batch)
    effective = await resolve_effective_guide(ports, batch.org_id)
    batch = await ports.repo.update_batch(
        lote_id,
        status=BatchStatus.SUBMETIDO,
        guia_efetivo_id=effective.id,
        guia_efetivo_sha256=effective.sha256,
        modelo_editor_id=plan.model_id,
        submetido_at=ports.clock(),
    )
    await ports.repo.add_event(
        PhotoEvent(
            org_id=batch.org_id,
            lote_id=lote_id,
            tipo="lote_submetido",
            detalhe={
                "por": submitted_by,
                "fotos": len(plan.photos),
                "guia_efetivo_sha256": effective.sha256,
                "modelo": plan.model_id,
            },
        )
    )
    await _enqueue(ports, JobType.SUBMIT_LOTE, {"lote_id": lote_id}, dedupe_submit(lote_id))
    return batch


# ---------------------------------------------------------------------------
# Manual retry
# ---------------------------------------------------------------------------


async def retry_photo(ports: PhotoEditingPorts, foto_id: str, *, requested_by: str) -> Photo:
    """Re-run a ``falhou`` photo as a NEW attempt (fresh dedupe key)."""
    photo = await ports.repo.get_photo(foto_id)
    if photo is None:
        raise NotFoundError(f"foto {foto_id} não encontrada")
    if PhotoStatus(photo.status) is not PhotoStatus.FALHOU:
        raise PhotoNotRetryableError("só é possível retentar fotos com falha")
    normalized = photo.largura_original is not None
    target = PhotoStatus.PRONTA if normalized else PhotoStatus.RECEBIDA
    moved = await ports.repo.transition_photo(
        foto_id,
        target,
        increment_tentativas=True,
        event_tipo="retry_manual",
        detalhe={"por": requested_by},
    )
    if moved is None:
        raise PhotoNotRetryableError("a foto mudou de estado; tente novamente")
    batch = await _require_batch(ports, moved.lote_id)
    if batch.status is BatchStatus.PRONTO:
        await ports.repo.update_batch(batch.id, status=BatchStatus.PROCESSANDO, pronto_at=None)
    if target is PhotoStatus.PRONTA:
        await enqueue_photo_work(ports, batch, moved)
    else:
        await enqueue_ingest(ports, moved)
    return moved


__all__ = [
    "ECONOMICO_IMPLEMENTED",
    "MANUAL_NOTES_WINDOW_SECONDS",
    "MANUAL_REGEN_WINDOW_SECONDS",
    "NotFoundError",
    "PhotoNotRetryableError",
    "PoolEmptyError",
    "SubmissionError",
    "SubmissionPlan",
    "add_photo_bytes",
    "enqueue_batch_ready_check",
    "enqueue_edit",
    "enqueue_evaluation",
    "enqueue_fx_backfill",
    "enqueue_ingest",
    "enqueue_model_notes",
    "enqueue_openai_batch_poll",
    "enqueue_openai_batch_submit",
    "enqueue_photo_work",
    "request_guide_regen",
    "request_rule_proposal",
    "retry_photo",
    "schedule_guide_regen",
    "schedule_rule_proposal",
    "submit_batch",
    "validate_submission",
]
