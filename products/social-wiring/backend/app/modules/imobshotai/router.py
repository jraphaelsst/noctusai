"""`/api/imobshotai` — IMOBSHOTAI-CONTRACT.md §1, §3, §4. Every route is tier `org` (auth → 401, role → 403).

| Method | Path | Who |
|---|---|---|
| POST | `/lotes` | member — get-or-create the imóvel's card + a lote linked to it |
| GET  | `/cards` | member — the board (admins: the org; a corretor: cards holding a lote they created) |
| GET  | `/cards/{card_id}` | member who can see the card (404 otherwise, never 403) |
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from noctusai_lib.domain.photo_editing import Actor, PhotoEditingPorts, PhotoStatus

from app.modules.edicao_fotos.deps import get_edicao_ports, get_imovel_lookup, require_member
from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.presenters import lote_resumo_out, page_out
from app.modules.edicao_fotos.schemas import ImovelRef
from app.modules.edicao_fotos.services.lotes import ImovelLookup, canonical, criar_lote
from app.modules.edicao_fotos.services.review import signed_url
from app.modules.imobshotai.deps import get_imobshot_repository
from app.modules.imobshotai.repository import ImobshotRepository
from app.modules.imobshotai.schemas import LoteIniciarBody
from app.modules.imobshotai.service import card_visivel, resumos, sincronizar_etapa

router = APIRouter(prefix="/api/imobshotai", tags=["imobshotai"])

ETAPAS = (
    "fotos_enviadas", "fotos_em_edicao", "fotos_em_revisao", "fotos_aprovadas",
    "video_em_montagem", "video_renderizando", "video_em_revisao", "concluido", "arquivado",
)
MAX_EVENTOS = 50


def _admin(actor: Actor) -> bool:
    return actor.is_platform_admin or actor.is_agency_admin


@router.post("/lotes", status_code=201)
async def iniciar_lote_route(
    body: LoteIniciarBody,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    repo: ImobshotRepository = Depends(get_imobshot_repository),
    imovel_lookup: ImovelLookup = Depends(get_imovel_lookup),
) -> dict:
    codigo = canonical(body.imovel_codigo)
    nome = body.nome or f"Fotos {codigo} {datetime.now().strftime('%d/%m')}"
    card_holder: dict[str, Any] = {}

    async def criar_card() -> None:
        card_holder["card"], _ = await asyncio.to_thread(
            repo.obter_ou_criar_card, actor.org_id, codigo, actor.user_id
        )

    batch = await criar_lote(
        ports=ports,
        actor=actor,
        nome=nome,
        imovel=ImovelRef(org_id=UUID(actor.org_id), codigo=codigo),
        velocidade=body.velocidade,
        imovel_lookup=imovel_lookup,
        antes_de_criar=criar_card,
    )
    card = card_holder["card"]
    linked = await asyncio.to_thread(repo.vincular_lote, card.id, batch.id, actor.user_id)
    if not linked:
        raise RuntimeError(f"lote {batch.id} could not be linked to card {card.id}")
    await sincronizar_etapa(repo, ports, card.id, ator_id=actor.user_id)
    card = await asyncio.to_thread(repo.get_card, actor.org_id, card.id)
    [resumo] = await resumos(
        repo, ports, [card], org_id=actor.org_id, imovel_lookup=imovel_lookup, assinar=signed_url
    )
    return {"card": resumo, "lote": lote_resumo_out(batch, [])}


@router.get("/cards")
async def listar_cards_route(
    etapa: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=40),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    repo: ImobshotRepository = Depends(get_imobshot_repository),
    imovel_lookup: ImovelLookup = Depends(get_imovel_lookup),
) -> dict:
    if etapa is not None and etapa not in ETAPAS:
        raise api_error(422, "etapa_invalida", "Etapa inválida.")
    cards, total = await asyncio.to_thread(
        repo.list_cards,
        actor.org_id,
        etapa=etapa,
        q=q,
        criado_por=None if _admin(actor) else actor.user_id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    items = await resumos(
        repo, ports, cards, org_id=actor.org_id, imovel_lookup=imovel_lookup, assinar=signed_url
    )
    return page_out(items, page=page, page_size=page_size, total=total)


@router.get("/cards/{card_id}")
async def card_route(
    card_id: UUID,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    repo: ImobshotRepository = Depends(get_imobshot_repository),
    imovel_lookup: ImovelLookup = Depends(get_imovel_lookup),
) -> dict:
    card = await asyncio.to_thread(repo.get_card, actor.org_id, str(card_id))
    lotes = (await asyncio.to_thread(repo.lotes_dos_cards, [str(card_id)])).get(str(card_id), []) if card else []
    if card is None or not card_visivel(lotes, user_id=actor.user_id, admin=_admin(actor)):
        # 404 for "not yours" too: nothing about another org's / another corretor's card leaks.
        raise api_error(404, "card_nao_encontrado", "Card não encontrado.")
    [resumo] = await resumos(
        repo, ports, [card], org_id=actor.org_id, imovel_lookup=imovel_lookup, assinar=signed_url
    )
    batches = await asyncio.gather(*(ports.repo.get_batch(l.id) for l in lotes))
    fotos_por_lote = await asyncio.gather(*(ports.repo.list_photos(l.id) for l in lotes))
    estados = await ports.repo.photo_states_for_batches([l.id for l in lotes]) if lotes else {}
    fotos: list[dict[str, Any]] = []
    for lote_fotos in fotos_por_lote:
        for p in lote_fotos:
            fotos.append(
                {
                    "id": str(p.id),
                    "lote_id": str(p.lote_id),
                    "comodo": None,
                    "status": getattr(p.status, "value", p.status),
                    "original_url": await signed_url(ports, p.storage_path_original),
                    "editada_url": await signed_url(ports, p.storage_path_editada),
                }
            )
    eventos = await asyncio.to_thread(repo.eventos, card.id, MAX_EVENTOS)
    return {
        **resumo,
        "lotes": [lote_resumo_out(b, [PhotoStatus(s) for s in estados.get(b.id, [])]) for b in batches if b],
        "fotos": fotos,
        "videos": [],
        "eventos": [
            {
                "tipo": e.tipo,
                "etapa_de": e.etapa_de,
                "etapa_para": e.etapa_para,
                "ator_id": e.actor_id,
                "em": e.at.isoformat(),
                "detalhe": e.detalhe,
            }
            for e in eventos
        ],
    }


__all__ = ["router"]
