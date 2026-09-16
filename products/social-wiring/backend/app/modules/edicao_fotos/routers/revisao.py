"""`/api/edicao-fotos/revisao` — contract §4.

| Method | Path | Who |
|---|---|---|
| GET  | `/revisao/{lote_id}` | member who can see the batch → FE `FotoRevisao[]` |
| POST | `/revisao/{lote_id}/fotos/{foto_id}/decisao` | same → the updated `FotoRevisao` |

🔴 The AI verdict (`avaliacao`) is read and included ONLY for callers who may
see it (platform admin, agency admin). For a corretor the evaluation is never
even fetched, and the key is absent from each row — not `null`.

A batch holds at most 100 photos (owner limit), so the review list is one
unpaginated array — the shape the seed `PhotoReviewGrid` organ consumes.

Decisions are always changeable (including after download); `rejeitar`
requires a comment (422 `comentario_obrigatorio`). The engine records the
decision + the training-dataset row and feeds the learning loop.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from noctusai_lib.domain.photo_editing import (
    Actor,
    Decision,
    PhotoEditingPorts,
    record_decision,
)

from app.modules.edicao_fotos.deps import (
    can_see_verdict,
    get_edicao_ports,
    load_visible_batch,
    require_member,
)
from app.modules.edicao_fotos.errors import ENGINE_ERRORS, api_error, engine_error
from app.modules.edicao_fotos.schemas import DecisaoBody
from app.modules.edicao_fotos.services.review import review_rows

router = APIRouter(prefix="/api/edicao-fotos/revisao", tags=["edicao-fotos"])


@router.get("/{lote_id}")
async def list_revisao_route(
    lote_id: UUID,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> list[dict]:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    photos = await ports.repo.list_photos(batch.id)
    return await review_rows(ports, batch, photos, include_verdict=can_see_verdict(actor))


@router.post("/{lote_id}/fotos/{foto_id}/decisao")
async def decide_route(
    lote_id: UUID,
    foto_id: UUID,
    body: DecisaoBody,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    photo = await ports.repo.get_photo(str(foto_id))
    if photo is None or str(photo.lote_id) != str(batch.id):
        raise api_error(404, "foto_nao_encontrada", "Foto não encontrada neste lote.")
    try:
        outcome = await record_decision(
            ports,
            foto_id=photo.id,
            decisao=Decision(body.decisao),
            comentario=body.comentario,
            decidido_por=actor.user_id,
        )
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    [row] = await review_rows(ports, batch, [outcome.photo], include_verdict=can_see_verdict(actor))
    return row
