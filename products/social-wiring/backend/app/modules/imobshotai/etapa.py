"""The card stage (etapa) projection — contract §6. Pure: no IO, so the table is testable row by row."""
from __future__ import annotations

from typing import Iterable

from noctusai_lib.domain.photo_editing import PhotoStatus

FOTOS_ENVIADAS = "fotos_enviadas"
FOTOS_EM_EDICAO = "fotos_em_edicao"
FOTOS_EM_REVISAO = "fotos_em_revisao"
FOTOS_APROVADAS = "fotos_aprovadas"

#: A photo in one of these states still has pipeline work to go (editing in progress).
ESTADOS_EM_EDICAO = frozenset(
    {
        PhotoStatus.RECEBIDA,
        PhotoStatus.NORMALIZANDO,
        PhotoStatus.PRONTA,
        PhotoStatus.EDITANDO,
        PhotoStatus.EM_LOTE_OPENAI,
        PhotoStatus.EDITADA,
        PhotoStatus.AVALIANDO,
    }
)


def derivar_etapa(lotes: Iterable[tuple[str, Iterable[PhotoStatus]]]) -> str:
    """`lotes` = `(status do lote, estados das fotos)` for EVERY lote of the card.

    A `rascunho` lote is not in the pipeline yet: its photos (uploaded, not submitted) never count as
    editing and it never counts as in-edit — a card with only drafts is `fotos_enviadas`."""
    em_edicao = False
    aguardando = False
    aprovada = False
    for status_lote, estados in lotes:
        status_lote = getattr(status_lote, "value", status_lote)
        ativo = status_lote != "rascunho"
        if ativo and status_lote in ("submetido", "processando"):
            em_edicao = True
        for estado in estados:
            estado = PhotoStatus(estado)
            if estado is PhotoStatus.APROVADA:
                aprovada = True
            elif estado is PhotoStatus.AGUARDANDO_DECISAO:
                aguardando = True
            elif ativo and estado in ESTADOS_EM_EDICAO:
                em_edicao = True
    if aprovada and not em_edicao and not aguardando:
        return FOTOS_APROVADAS
    if aguardando and not em_edicao:
        return FOTOS_EM_REVISAO
    if em_edicao:
        return FOTOS_EM_EDICAO
    return FOTOS_ENVIADAS


__all__ = [
    "ESTADOS_EM_EDICAO",
    "FOTOS_APROVADAS",
    "FOTOS_EM_EDICAO",
    "FOTOS_EM_REVISAO",
    "FOTOS_ENVIADAS",
    "derivar_etapa",
]
