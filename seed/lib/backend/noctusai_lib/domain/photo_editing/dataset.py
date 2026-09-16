"""Review decisions + the append-only training dataset.

Every human decision is two appends: a ``fotos_decisoes`` row (the latest
per photo is the current decision — decisions are always changeable) and
a ``fotos_dataset`` row carrying everything a future trainable model needs
(original + edited paths, edit types, the effective-guide sha, the AI
verdict, the human verdict and comment). Neither is ever updated.

A rejection with a comment also feeds the learning loop: it bumps the
org's proposal cursor and schedules the (debounced) rule proposer.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from noctusai_lib.domain.photo_editing.pipeline import NotFoundError, schedule_rule_proposal
from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts
from noctusai_lib.domain.photo_editing.types import (
    DECIDABLE_STATES,
    Batch,
    DatasetRecord,
    Decision,
    EditAttempt,
    Evaluation,
    Photo,
    PhotoStatus,
    ProposalCursor,
    ReviewDecision,
)


class CommentRequiredError(ValueError):
    """``rejeitar`` without a comment (HTTP 422)."""

    code = "comentario_obrigatorio"


class PhotoNotDecidableError(RuntimeError):
    """The photo has not reached review yet, or failed (HTTP 409)."""

    code = "foto_nao_decidivel"


def build_dataset_record(
    *,
    batch: Batch,
    photo: Photo,
    decision: ReviewDecision,
    edit: EditAttempt | None,
    evaluation: Evaluation | None,
) -> DatasetRecord:
    if not batch.guia_efetivo_sha256:
        raise ValueError(f"lote {batch.id} has no effective-guide snapshot")
    return DatasetRecord(
        org_id=photo.org_id,
        lote_id=photo.lote_id,
        foto_id=photo.id,
        decisao_id=decision.id,
        tipos_edicao=edit.tipos_edicao if edit else (),
        guia_efetivo_sha256=batch.guia_efetivo_sha256,
        decisao_final=decision.decisao,
        storage_path_original=photo.storage_path_original,
        storage_path_editada=photo.storage_path_editada,
        avaliacao_score=evaluation.score if evaluation else None,
        avaliacao_recomendacao=evaluation.recomendacao if evaluation else None,
        comentario=decision.comentario,
    )


@dataclass(frozen=True)
class DecisionOutcome:
    decision: ReviewDecision
    photo: Photo
    dataset_record: DatasetRecord


async def record_decision(
    ports: PhotoEditingPorts,
    *,
    foto_id: str,
    decisao: Decision,
    comentario: str | None,
    decidido_por: str,
) -> DecisionOutcome:
    decisao = Decision(decisao)
    comentario = (comentario or "").strip() or None
    if decisao is Decision.REJEITAR and comentario is None:
        raise CommentRequiredError("comentário obrigatório ao rejeitar")
    repo = ports.repo
    photo = await repo.get_photo(foto_id)
    if photo is None:
        raise NotFoundError(f"foto {foto_id} não encontrada")
    if PhotoStatus(photo.status) not in DECIDABLE_STATES:
        raise PhotoNotDecidableError(f"foto em estado {photo.status.value}")
    batch = await repo.get_batch(photo.lote_id)
    if batch is None:
        raise NotFoundError(f"lote {photo.lote_id} não encontrado")

    target = PhotoStatus.APROVADA if decisao is Decision.APROVAR else PhotoStatus.REJEITADA
    if photo.status is not target:
        moved = await repo.transition_photo(
            foto_id, target, event_tipo="decisao", detalhe={"por": decidido_por}
        )
        if moved is None:
            raise PhotoNotDecidableError("a foto mudou de estado; tente novamente")
        photo = moved

    decision = await repo.add_decision(
        org_id=photo.org_id,
        lote_id=photo.lote_id,
        foto_id=foto_id,
        decisao=decisao,
        comentario=comentario,
        decidido_por=decidido_por,
    )
    record = build_dataset_record(
        batch=batch,
        photo=photo,
        decision=decision,
        edit=await repo.latest_edit(foto_id),
        evaluation=await repo.latest_evaluation(foto_id),
    )
    await repo.add_dataset_record(record)

    if decisao is Decision.REJEITAR:
        cursor = await repo.get_cursor(photo.org_id) or ProposalCursor(org_id=photo.org_id)
        await repo.save_cursor(
            dataclasses.replace(
                cursor, rejeicoes_desde_ultima=cursor.rejeicoes_desde_ultima + 1
            )
        )
        await schedule_rule_proposal(ports, photo.org_id)
    return DecisionOutcome(decision=decision, photo=photo, dataset_record=record)


__all__ = [
    "CommentRequiredError",
    "DecisionOutcome",
    "PhotoNotDecidableError",
    "build_dataset_record",
    "record_decision",
]
