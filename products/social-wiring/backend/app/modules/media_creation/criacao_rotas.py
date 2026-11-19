"""CoreStudio criação routes as DATA (criacao-pipeline-contract.md sections 1 and 5).

A route is the job graph a post's media is produced by, keyed ``(formato, modo_producao)``. Adding a route is a row in
:data:`ROTAS`, never an ``if``. Only ``reel_narrado`` has handlers today (the pilot); every other route is DECLARED here
(so the board, the status line and the refusal are all derived from one place) and refuses visibly with the coded
``rota_nao_implementada`` -- never a silent skip, never a half-run graph.

``modo`` is the second key of the contract. ``cs_posts`` has no ``modo_producao`` column: the chosen route is stored in
``cs_posts.criacao_rota`` (migration 362); when that is empty the route is the default of the post's ``formato``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from noctusai_lib.domain.media_production import StepSpec

#: Coded refusal (HTTP 409): the route exists in the contract but has no handlers yet.
ROTA_NAO_IMPLEMENTADA = "rota_nao_implementada"
ROTA_DESCONHECIDA = "rota_desconhecida"

PASSO_TTS = "tts"
PASSO_RENDER = "render_motion"
PASSO_MUX = "mux"


@dataclass(frozen=True)
class PassoDef:
    passo: str
    rotulo: str  # pt-BR gerund shown on the card ("Sintetizando voz (1/3)")
    depende_de: tuple[str, ...] = ()
    #: expected duration in seconds: the progress weight (contract 3) -- a render dominates the bar.
    peso: float = 1.0


@dataclass(frozen=True)
class Rota:
    chave: str
    formato: str
    modo: Optional[str]
    passos: tuple[PassoDef, ...]
    #: the Edição stage is traversed with ``motivo='rota:pulado'`` unless the route needs it (avatar: legendas).
    edicao: bool
    implementada: bool = False
    #: this formato's default route when the post names none.
    padrao: bool = False

    def specs(self, entradas: dict[str, dict], estimativas: dict[str, object] | None = None) -> tuple[StepSpec, ...]:
        """The seed graph of this route; ``entradas`` = per-step inputs, ``estimativas`` = per-step USD pre-flight."""
        estimativas = estimativas or {}
        return tuple(
            StepSpec(
                p.passo, p.rotulo, p.depende_de, p.peso,
                estimativas.get(p.passo), dict(entradas.get(p.passo) or {}),
            )
            for p in self.passos
        )


ROTAS: tuple[Rota, ...] = (
    Rota(
        "reel_narrado", "reel", "narrado",
        (
            PassoDef(PASSO_TTS, "Sintetizando voz", (), 8),
            PassoDef(PASSO_RENDER, "Renderizando vídeo", (PASSO_TTS,), 90),
            PassoDef(PASSO_MUX, "Mixando áudio", (PASSO_RENDER,), 6),
        ),
        edicao=False, implementada=True, padrao=True,
    ),
    Rota(
        "carrossel", "carrossel", None,
        (PassoDef("layout", "Desenhando os slides"), PassoDef("render_slides", "Renderizando os slides", ("layout",))),
        edicao=False, padrao=True,
    ),
    Rota(
        "estatico", "feed", None,
        (PassoDef("layout", "Desenhando a imagem"), PassoDef("render_estatico", "Renderizando a imagem", ("layout",))),
        edicao=False, padrao=True,
    ),
    Rota(
        "avatar", "reel", "avatar",
        (
            PassoDef(PASSO_TTS, "Sintetizando voz", (), 8),
            PassoDef("heygen_avatar", "Gerando o avatar", (PASSO_TTS,), 60),
            PassoDef("poll_avatar", "Aguardando o avatar", ("heygen_avatar",), 120),
        ),
        edicao=True,
    ),
    Rota("gravado", "reel", "gravado", (), edicao=True),
)


class RotaError(Exception):
    def __init__(self, status: int, codigo: str, detail: str):
        super().__init__(detail)
        self.status, self.codigo, self.detail = status, codigo, detail


def rota_por_chave(chave: str) -> Rota:
    for r in ROTAS:
        if r.chave == chave:
            return r
    raise RotaError(422, ROTA_DESCONHECIDA, f"Rota de criação desconhecida: {chave}")


def resolver_rota(formato: str, chave: Optional[str] = None) -> Rota:
    """The post's route: its stored ``criacao_rota`` or the default of its ``formato``."""
    if chave:
        rota = rota_por_chave(chave)
    else:
        rota = next((r for r in ROTAS if r.formato == formato and r.padrao), None)
        if rota is None:
            raise RotaError(422, ROTA_DESCONHECIDA, f"O formato {formato} não tem rota de criação.")
    if not rota.implementada:
        raise RotaError(
            409, ROTA_NAO_IMPLEMENTADA,
            f"A rota {rota.chave} ainda não está disponível — por enquanto só o reel narrado é produzido automaticamente.",
        )
    return rota
