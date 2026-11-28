"""Freeze the approved content into the run's input (pure).

The roteiro's spoken text is tokenised ONCE here, with the same ``blocos_de_fala`` the narrated route uses, so word ids
(``w0..wN``) mean the same thing to the planner, the voice retime and every later check. The roteiro / headline hashes pin
what was approved: a plan, a render and a review package all name the version they were made from.
"""
from __future__ import annotations

from noctusai_lib.domain.media_production import StepError

from app.modules.media_creation.criacao_handlers import SEM_FALA, blocos_de_fala
from app.modules.media_creation.direcao.tipos import EntradaCongelada, Palavra, sha256_texto


class EntradaInvalida(StepError):
    """The approved content cannot be turned into a run (coded; ``codigo`` is the card's failure code)."""

    def __init__(self, codigo: str, message: str = "") -> None:
        super().__init__(codigo, message)
        self.codigo = codigo


def congelar_entrada(
    *, org_id: str, post_id: str, marca_id: str, rodada: int, headline_id: str, headline: str, roteiro_id: str,
    roteiro_versao: int, roteiro: str,
) -> EntradaCongelada:
    tokens = [t for bloco in blocos_de_fala(roteiro) for t in bloco.split()]
    if not tokens:
        raise EntradaInvalida(SEM_FALA, "o roteiro não tem texto de fala")
    return EntradaCongelada(
        org_id=str(org_id), post_id=str(post_id), marca_id=str(marca_id), rodada=int(rodada), headline_id=str(headline_id),
        headline=headline or "", roteiro_id=str(roteiro_id), roteiro_versao=int(roteiro_versao),
        roteiro_sha256=sha256_texto(roteiro), headline_sha256=sha256_texto(headline or ""),
        palavras=tuple(Palavra(f"w{i}", t) for i, t in enumerate(tokens)),
    )


__all__ = ["EntradaInvalida", "congelar_entrada"]
