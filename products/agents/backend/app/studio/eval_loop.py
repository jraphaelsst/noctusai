"""The eval-loop gate's pure rules (owner spec 2026-11-09, G1-G7). No IO: every function takes plain data.

A LOOP refines one suite of one agent over planned rounds. A ROUND is one run started with the loop's id. The rules:

* G1 target (``alvo``: the platform config, default 95%, frozen on the loop), floor = the agent's ``publicacao_limiar`` (``piso``)
* G2 planned rounds N; checkpoints at 5, 10, 15 (those <= N)
* G3 stop at the target
* G4 two CONSECUTIVE scored rounds without a score improvement stop the loop (above or below the floor)
* G5 every round that did not raise the score is an overcall, listed with its cost
* G6 a round on an unchanged content hash is refused beyond the consolidation passes (:func:`checar_admissao`)
* G7 spend per round against the loop budget; reaching it stops the loop for an owner decision

"Improved" means strictly above the best score of the earlier scored rounds. The first scored round is the baseline: it
is neither an improvement nor an overcall. A round with no score (the run failed before measuring: harness error,
cancelled, spec refused) is NEUTRAL for G4/G5 but its cost still counts for G7.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

__all__ = [
    "CHECKPOINTS", "EPS", "MAX_FALHAS_NA_MENSAGEM", "SEM_MELHORA_MAX", "Recusa", "Rodada", "LoopDef", "Decisao", "Parada",
    "MOTIVOS_PARADA", "avaliar_rodada", "checar_admissao", "melhorou", "checkpoints_atingidos", "serie_de_scores",
    "partes_alteradas", "ordenar",
]

#: G2: the rounds at which the owner is shown progress (only those <= the planned rounds apply).
CHECKPOINTS = (5, 10, 15)
#: G4: this many consecutive scored rounds without improvement stop the loop.
SEM_MELHORA_MAX = 2
#: float noise: a score within EPS of the best is NOT an improvement.
EPS = 1e-9
#: how many still-failing cases a stop message names (the rest are counted).
MAX_FALHAS_NA_MENSAGEM = 12

MOTIVOS_PARADA = ("alvo_atingido", "sem_melhora", "orcamento_atingido", "rodadas_esgotadas", "parado_manualmente")


@dataclass(frozen=True)
class Rodada:
    seq: int
    run_id: UUID
    run_tipo: str
    compiled_hash: str
    status: str = "executando"  # executando | concluida | falhou | cancelada
    score: float | None = None
    custo_usd: float = 0.0
    falhas: tuple[str, ...] = ()
    melhorou: bool | None = None
    overcall: bool = False
    partes: Mapping[str, str] | None = None

    @property
    def aberta(self) -> bool:
        return self.status == "executando"

    @property
    def pontuada(self) -> bool:
        return not self.aberta and self.score is not None


@dataclass(frozen=True)
class LoopDef:
    id: UUID
    suite: str
    rodadas_planejadas: int
    alvo: float
    piso: float
    orcamento_usd: float
    gasto_usd: float = 0.0
    status: str = "ativo"
    motivo_parada: str | None = None

    @property
    def restante_usd(self) -> float:
        return max(0.0, round(self.orcamento_usd - self.gasto_usd, 4))


@dataclass(frozen=True)
class Recusa:
    """A run start the gate refuses: an HTTP 409 ``code`` + pt-BR message."""

    code: str
    mensagem: str


@dataclass(frozen=True)
class Parada:
    motivo: str  # one of MOTIVOS_PARADA
    status: str  # 'parado' | 'concluido'
    detalhe: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decisao:
    """What closing a round decided: its own flags + whether the loop stops + the checkpoint reached (if any)."""

    melhorou: bool | None
    overcall: bool
    sem_melhora_seguidas: int
    gasto_usd: float
    parada: Parada | None = None
    checkpoint: int | None = None


def ordenar(rodadas: Sequence[Rodada]) -> list[Rodada]:
    return sorted(rodadas, key=lambda r: r.seq)


def serie_de_scores(rodadas: Sequence[Rodada]) -> list[float]:
    """The scored rounds' scores in order (the series G4 reads)."""
    return [r.score for r in ordenar(rodadas) if r.pontuada and r.score is not None]


def melhorou(rodadas_anteriores: Sequence[Rodada], score: float) -> bool | None:
    """``None`` = the baseline (no earlier scored round); else strictly above the best earlier score."""
    anteriores = serie_de_scores(rodadas_anteriores)
    if not anteriores:
        return None
    return score > max(anteriores) + EPS


def _seguidas_sem_melhora(scores: Sequence[float]) -> int:
    """Trailing run of rounds that did not raise the best-so-far (the baseline never counts)."""
    melhor: float | None = None
    seguidas = 0
    for s in scores:
        if melhor is None:
            melhor = s
        elif s > melhor + EPS:
            melhor, seguidas = s, 0
        else:
            seguidas += 1
    return seguidas


def partes_alteradas(antes: Mapping[str, str] | None, depois: Mapping[str, str] | None) -> list[str] | None:
    """The compiled-spec parts whose hash differs between two rounds. ``None`` = unknowable (a round without part hashes)."""
    if antes is None or depois is None:
        return None
    return sorted(k for k in set(antes) | set(depois) if antes.get(k) != depois.get(k))


def checkpoints_atingidos(loop: LoopDef, rodadas: Sequence[Rodada]) -> list[dict[str, Any]]:
    """G2: for each checkpoint <= the planned rounds, whether it was reached and the score/spend at that round."""
    fechadas = [r for r in ordenar(rodadas) if not r.aberta]
    out = []
    for cp in CHECKPOINTS:
        if cp > loop.rodadas_planejadas:
            continue
        no_cp = [r for r in fechadas if r.seq <= cp]
        atingido = len(fechadas) >= cp
        out.append({
            "rodada": cp, "atingido": atingido,
            "score": (serie_de_scores(no_cp) or [None])[-1] if atingido else None,
            "gasto_usd": round(sum(r.custo_usd for r in no_cp), 4) if atingido else None,
        })
    return out


def avaliar_rodada(loop: LoopDef, anteriores: Sequence[Rodada], *, seq: int, status: str, score: float | None,
                   custo_usd: float, falhas: Sequence[str], compiled_hash: str,
                   partes: Mapping[str, str] | None = None) -> Decisao:
    """Close one round: G5 flags, then the stop rules in order G3 (target) -> G7 (budget) -> G4 (no improvement) ->
    planned rounds exhausted. ``anteriores`` are the loop's OTHER rounds (open ones ignored)."""
    fechadas = [r for r in ordenar(anteriores) if not r.aberta and r.seq != seq]
    gasto = round(loop.gasto_usd + (custo_usd or 0.0), 4)
    if score is None:  # neutral: nothing measured about the agent; the cost still counts
        flag_melhorou, overcall, seguidas = None, False, _seguidas_sem_melhora(serie_de_scores(fechadas))
        novos_scores = serie_de_scores(fechadas)
    else:
        flag_melhorou = melhorou(fechadas, score)
        overcall = flag_melhorou is False
        novos_scores = serie_de_scores(fechadas) + [score]
        seguidas = _seguidas_sem_melhora(novos_scores)

    n_fechadas = len(fechadas) + 1
    parada = None
    if score is not None and score >= loop.alvo - EPS:
        parada = Parada("alvo_atingido", "concluido", {"score": score, "alvo": loop.alvo})
    elif gasto >= loop.orcamento_usd - EPS:
        parada = Parada("orcamento_atingido", "parado", {"gasto_usd": gasto, "orcamento_usd": loop.orcamento_usd})
    elif seguidas >= SEM_MELHORA_MAX:
        ultimas = [r for r in fechadas if r.pontuada][-1:]  # the previous scored round, to say what changed since
        mudou = partes_alteradas(ultimas[0].partes, partes) if ultimas else None
        parada = Parada("sem_melhora", "parado", {
            "seguidas": seguidas, "hash_anterior": ultimas[0].compiled_hash if ultimas else None,
            "hash_atual": compiled_hash, "conteudo_mudou": (ultimas[0].compiled_hash != compiled_hash) if ultimas else None,
            "partes_alteradas": mudou,
        })
    elif n_fechadas >= loop.rodadas_planejadas:
        parada = Parada("rodadas_esgotadas", "concluido", {"rodadas": n_fechadas})
    checkpoint = next((cp for cp in CHECKPOINTS if cp == n_fechadas and cp <= loop.rodadas_planejadas), None)
    return Decisao(melhorou=flag_melhorou, overcall=overcall, sem_melhora_seguidas=seguidas, gasto_usd=gasto,
                   parada=parada, checkpoint=checkpoint)


def checar_admissao(loop: LoopDef, rodadas: Sequence[Rodada], *, compiled_hash: str, limite_passes_consolidacao: int,
                    ) -> Recusa | None:
    """Whether a new round may start (G6 + G7 + the loop's own status). Order: closed loop, round in flight, spent budget,
    planned rounds, then G6. ``limite_passes_consolidacao`` = the longest streak any active case of the suite needs to
    consolidate (``ConfigConsolidacao.limite``): re-running an unchanged hash is only meaningful while a clean streak is
    accumulating, never to re-measure a failure nobody fixed."""
    if loop.status != "ativo":
        return Recusa("loop_encerrado", f"O loop foi encerrado ({loop.motivo_parada or loop.status}). Inicie um novo loop.")
    rs = ordenar(rodadas)
    if any(r.aberta for r in rs):
        return Recusa("rodada_em_andamento", "Já há uma rodada deste loop em andamento. Aguarde terminar ou cancele a run.")
    if loop.gasto_usd >= loop.orcamento_usd - EPS:
        return Recusa("orcamento_do_loop_atingido",
                      f"O orçamento do loop (US$ {loop.orcamento_usd:.2f}) foi atingido. A decisão de continuar é do dono.")
    if len(rs) >= loop.rodadas_planejadas:
        return Recusa("rodadas_esgotadas", f"As {loop.rodadas_planejadas} rodadas planejadas do loop acabaram.")
    mesmas = [r for r in rs if r.compiled_hash == compiled_hash and not r.aberta]
    if mesmas:
        ultima = mesmas[-1]
        if ultima.falhas:
            nomes = ", ".join(ultima.falhas[:MAX_FALHAS_NA_MENSAGEM])
            return Recusa(
                "hash_inalterado",
                f"O conteúdo do agente não mudou desde a rodada {ultima.seq}, que ainda tinha casos falhando ({nomes}). "
                "Corrija o conteúdo e rode de novo: rodar sem corrigir só repete o mesmo resultado.")
        if len(mesmas) >= limite_passes_consolidacao:
            return Recusa(
                "hash_inalterado",
                f"O conteúdo do agente não mudou em {len(mesmas)} rodadas seguidas, que já cobrem as passagens de "
                f"consolidação ({limite_passes_consolidacao}). Altere o conteúdo ou encerre o loop.")
    return None
