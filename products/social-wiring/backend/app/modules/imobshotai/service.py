"""ImobShotAI card service: the etapa projection and the card read models (contract §3, §4, §6).

`sincronizar_etapa` recomputes the etapa from the card's lotes and photos and hands the result to the store's atomic
`aplicar_etapa`, which writes (and records `etapa_mudou`) ONLY when it changed."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from noctusai_lib.domain.photo_editing import PhotoEditingPorts, PhotoStatus

from app.modules.imobshotai.etapa import derivar_etapa
from app.modules.imobshotai.repository import Card, ImobshotRepository, LoteRef

logger = logging.getLogger(__name__)

#: `(org_id, [codigo]) -> {codigo: imóvel}` — `imovel_hub.busca_service.enriquecer` in production.
ImovelLookup = Callable[[str, list[str]], dict[str, dict]]


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(fn, *args, **kwargs)


def _status(value: Any) -> str:
    return getattr(value, "value", value)


async def sincronizar_etapa(
    repo: ImobshotRepository, ports: PhotoEditingPorts, card_id: str, *, ator_id: Optional[str]
) -> bool:
    """Recompute + apply the card's etapa. Returns whether it changed."""
    lotes = (await _call(repo.lotes_dos_cards, [card_id])).get(card_id, [])
    fotos_por_lote = await asyncio.gather(*(ports.repo.list_photos(l.id) for l in lotes))
    etapa = derivar_etapa(
        (l.status, [PhotoStatus(p.status) for p in fotos]) for l, fotos in zip(lotes, fotos_por_lote)
    )
    capa: Optional[str] = None
    # Cover = the best approved photo: newest lote first (lotes arrive newest first), then upload order.
    for fotos in fotos_por_lote:
        aprovadas = sorted((p for p in fotos if PhotoStatus(p.status) is PhotoStatus.APROVADA), key=lambda p: p.ordem)
        if aprovadas:
            capa = str(aprovadas[0].id)
            break
    return await _call(repo.aplicar_etapa, card_id, etapa, capa, ator_id)


async def sincronizar_do_lote(
    repo: ImobshotRepository, ports: PhotoEditingPorts, lote_id: str, *, ator_id: Optional[str]
) -> bool:
    """Sync the card of `lote_id` (no-op for a plain Edição de Imagem lote).

    A projection failure must not undo the action that triggered it (a decision, a submit): it is logged and the
    next call site recomputes the same value from the source rows."""
    try:
        card_id = await _call(repo.card_id_do_lote, str(lote_id))
        if card_id is None:
            return False
        return await sincronizar_etapa(repo, ports, card_id, ator_id=ator_id)
    except Exception:
        logger.exception("imobshotai: falha ao sincronizar a etapa do card do lote %s", lote_id)
        return False


async def resumos(
    repo: ImobshotRepository,
    ports: PhotoEditingPorts,
    cards: list[Card],
    *,
    org_id: str,
    imovel_lookup: ImovelLookup,
    assinar: Callable[[PhotoEditingPorts, Optional[str]], Any],
) -> list[dict[str, Any]]:
    """`CardResumo` for each card — batched reads only (lotes, photo states, cover rows, imóveis): no per-card query."""
    if not cards:
        return []
    ids = [c.id for c in cards]
    lotes = await _call(repo.lotes_dos_cards, ids)
    todos = [l.id for ls in lotes.values() for l in ls]
    estados = await ports.repo.photo_states_for_batches(todos) if todos else {}
    capas_ids = [c.capa_foto_id for c in cards if c.capa_foto_id]
    capas = {f.id: f for f in await _call(repo.fotos_por_ids, capas_ids)} if capas_ids else {}
    imoveis = await _call(imovel_lookup, org_id, sorted({c.imovel_codigo for c in cards}))
    urls = await asyncio.gather(
        *(assinar(ports, capas[c.capa_foto_id].storage_path_editada) if c.capa_foto_id in capas else _none() for c in cards)
    )
    out = []
    for card, url in zip(cards, urls):
        sts = [PhotoStatus(s) for l in lotes.get(card.id, []) for s in estados.get(l.id, [])]
        imovel = imoveis.get(card.imovel_codigo) or {}
        out.append(
            {
                "id": card.id,
                "imovel": {
                    "org_id": card.org_id,
                    "codigo": card.imovel_codigo,
                    "titulo": imovel.get("titulo"),
                    "bairro": imovel.get("bairro"),
                },
                "etapa": card.etapa,
                "etapa_desde": _iso(card.etapa_desde),
                "capa_url": url,
                "total_fotos": len(sts),
                "fotos_aprovadas": sum(1 for s in sts if s is PhotoStatus.APROVADA),
                "total_videos": 0,
                "criado_em": _iso(card.created_at),
                "atualizado_em": _iso(card.updated_at),
            }
        )
    return out


async def _none() -> None:
    return None


def card_visivel(lotes: list[LoteRef], *, user_id: str, admin: bool) -> bool:
    return admin or any(l.criado_por == user_id for l in lotes)


__all__ = [
    "ImovelLookup",
    "card_visivel",
    "resumos",
    "sincronizar_do_lote",
    "sincronizar_etapa",
]
