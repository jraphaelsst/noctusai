"""Synchronous pipeline entry points + job enqueueing.

What a consumer's ROUTES call (the handlers in ``handlers.py`` are what its
WORKER calls):

- ``add_photo_bytes``   — store an upload, register the photo, enqueue ingest.
- ``submit_batch``      — validate, snapshot the effective guide, enqueue.
- ``retry_photo``       — manual retry of a ``falhou`` photo.
- ``schedule_guide_regen`` / ``schedule_rule_proposal`` — trailing debounce.
- ``enqueue_fx_backfill`` — daily PTAX backfill.

Every enqueue carries a dedupe key (``types.dedupe_*``), so a double click,
a retried request or a re-run handler never creates a second job.
Validation errors carry a ``code`` the consumer maps to its error envelope.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from noctusai_lib.domain.jobs import Job
from noctusai_lib.domain.photo_editing.guide import resolve_effective_guide
from noctusai_lib.domain.photo_editing.naming import upload_path
from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts
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
    dedupe_propor_regras,
    dedupe_regen_guia,
    dedupe_submit,
)
from noctusai_lib.integrations.image_edit import capabilities_for_model

#: Econômico (Batch API) has no engine path in R1 — PROJECT.md C8.
ECONOMICO_IMPLEMENTED = False

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


async def schedule_rule_proposal(ports: PhotoEditingPorts, org_id: str) -> Job:
    now = ports.clock()
    window = ports.config.rule_proposal_debounce_seconds
    return await _enqueue(
        ports,
        JobType.PROPOR_REGRAS,
        {"org_id": org_id},
        dedupe_propor_regras(org_id, debounce_bucket(now, window)),
        scheduled_for=_window_end(now, window),
    )


async def enqueue_fx_backfill(ports: PhotoEditingPorts, day: date) -> Job:
    return await _enqueue(
        ports, JobType.FX_BACKFILL, {"dia": day.isoformat()}, dedupe_fx_backfill(day.isoformat())
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
    caps = capabilities_for_model(settings.modelo_editor_id)
    if not caps.known:
        raise SubmissionError(
            "modelo_desconhecido", f"modelo {settings.modelo_editor_id} não está no catálogo"
        )
    if not settings.tipos_edicao_ativos:
        raise SubmissionError("sem_tipos_edicao", "nenhum tipo de edição ativo")
    if Speed(batch.velocidade) is Speed.ECONOMICO and not (
        ECONOMICO_IMPLEMENTED and caps.supports_batch
    ):
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
        await enqueue_edit(ports, moved)
    else:
        await enqueue_ingest(ports, moved)
    return moved


__all__ = [
    "ECONOMICO_IMPLEMENTED",
    "NotFoundError",
    "PhotoNotRetryableError",
    "SubmissionError",
    "SubmissionPlan",
    "add_photo_bytes",
    "enqueue_batch_ready_check",
    "enqueue_edit",
    "enqueue_evaluation",
    "enqueue_fx_backfill",
    "enqueue_ingest",
    "retry_photo",
    "schedule_guide_regen",
    "schedule_rule_proposal",
    "submit_batch",
    "validate_submission",
]
