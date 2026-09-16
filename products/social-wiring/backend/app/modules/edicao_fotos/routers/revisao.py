"""`/api/edicao-fotos/revisao` — contract §4.

| Method | Path | Who |
|---|---|---|
| GET  | `/revisao/{lote_id}` | member who can see the batch |
| POST | `/revisao/{lote_id}/fotos/{foto_id}/decisao` | same |

🔴 The AI verdict (`avaliacao`) is read and included ONLY for callers who may
see it (platform admin, agency admin). For a corretor the evaluation is never
even fetched, and the key is absent from the response — not `null`.

Decisions are always changeable (including after download); `rejeitar`
requires a comment (422 `comentario_obrigatorio`). The engine records the
decision + the training-dataset row and feeds the learning loop.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

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
from app.modules.edicao_fotos.presenters import (
    batch_out,
    decision_out,
    evaluation_out,
    page_out,
    photo_out,
)
from app.modules.edicao_fotos.schemas import DecisaoBody

router = APIRouter(prefix="/api/edicao-fotos/revisao", tags=["edicao-fotos"])

SIGNED_URL_TTL_SECONDS = 3600


async def _signed(ports: PhotoEditingPorts, path: str | None) -> str | None:
    if not path:
        return None
    sign = getattr(ports.storage, "signed_url", None)
    if sign is None:
        # A storage port without signing cannot serve review thumbnails;
        # that is a wiring error, not an empty preview.
        raise api_error(503, "armazenamento_sem_url", "Armazenamento não gera URLs assinadas.")
    return await sign(path, expires_in_seconds=SIGNED_URL_TTL_SECONDS)


@router.get("/{lote_id}")
async def list_revisao_route(
    lote_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    photos = await ports.repo.list_photos(batch.id)
    decisions = await ports.repo.latest_decisions(batch.id)
    show_verdict = can_see_verdict(actor)
    start = (page - 1) * page_size
    items: list[dict[str, Any]] = []
    for photo in photos[start : start + page_size]:
        item = {
            **photo_out(photo),
            "url_original": await _signed(ports, photo.storage_path_original),
            "url_editada": await _signed(ports, photo.storage_path_editada),
            "decisao": decision_out(decisions.get(photo.id)),
        }
        if show_verdict:
            item["avaliacao"] = evaluation_out(await ports.repo.latest_evaluation(photo.id))
        items.append(item)
    return {
        "lote": batch_out(batch, photos),
        "pode_ver_veredito": show_verdict,
        **page_out(items, page=page, page_size=page_size, total=len(photos)),
    }


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
    return {"foto": photo_out(outcome.photo), "decisao": decision_out(outcome.decision)}
