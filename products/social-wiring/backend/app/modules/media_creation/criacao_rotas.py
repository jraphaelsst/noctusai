"""Criação production routes -- DATA (criacao-pipeline-contract 1).

A route says which jobs Criação runs, which Esteira stages the card skips, and whether Edição carries a sub-step. It is
keyed by ``(formato, modo_producao)`` and stored on ``cs_posts.criacao_rota`` (CHECK-enum, migration 362). Stages are
named by ROLE (``esteira_config.ROLE_*``), never by slug or label: the list of stages is data on the board
(``data/esteira_etapas.json`` / ``pipeline_stages``), and a skipped stage is whatever stage carries the role.

A skipped stage is TRAVERSED, not jumped over: the system mover walks the card through it with ``motivo='rota:pulado'``
so the history shows the card passed there (the metrics for "time in stage" stay honest).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.modules.media_creation.esteira_config import ROLE_EDICAO

#: ``modo_producao`` default when the caller does not name one.
MODO_NARRADO = "narrado"
MODO_AVATAR = "avatar"
MODO_GRAVADO = "gravado"


@dataclass(frozen=True)
class Rota:
    """One production route. ``passos`` are the Criação jobs in dependency order (the S6 worker's job graph)."""

    chave: str
    passos: tuple[str, ...]
    etapas_puladas: frozenset[str] = frozenset()
    #: sub-step of the Edição stage, when the route carries one (avatar videos: the captions burn-in).
    subpasso_edicao: Optional[str] = None


ROTAS: dict[str, Rota] = {
    r.chave: r
    for r in (
        Rota("reel_narrado", ("tts", "render_motion", "mux"), frozenset({ROLE_EDICAO})),
        Rota("carrossel", ("layout", "render_slides"), frozenset({ROLE_EDICAO})),
        Rota("estatico", ("layout", "render_estatico"), frozenset({ROLE_EDICAO})),
        Rota("avatar", ("tts", "heygen_avatar", "poll"), frozenset(), subpasso_edicao="legendas"),
        Rota("gravado", (), frozenset()),
    )
}

#: ``(formato, modo_producao)`` -> route key. ``cs_posts.formato`` is reel | carrossel | story | feed (342).
ROTA_POR_FORMATO: dict[tuple[str, str], str] = {
    ("reel", MODO_NARRADO): "reel_narrado",
    ("reel", MODO_AVATAR): "avatar",
    ("reel", MODO_GRAVADO): "gravado",
    ("carrossel", MODO_NARRADO): "carrossel",
    ("feed", MODO_NARRADO): "estatico",
    ("story", MODO_NARRADO): "estatico",
}


def resolver_rota(formato: Optional[str], modo_producao: Optional[str] = None) -> Optional[Rota]:
    """The route for ``(formato, modo_producao)`` (``modo`` defaults to narrado); ``None`` = no automatic route."""
    chave = ROTA_POR_FORMATO.get((str(formato or ""), modo_producao or MODO_NARRADO))
    return ROTAS[chave] if chave else None


def rota_da_chave(chave: Optional[str]) -> Optional[Rota]:
    return ROTAS.get(str(chave)) if chave else None


__all__ = ["MODO_AVATAR", "MODO_GRAVADO", "MODO_NARRADO", "ROTAS", "ROTA_POR_FORMATO", "Rota", "resolver_rota", "rota_da_chave"]
