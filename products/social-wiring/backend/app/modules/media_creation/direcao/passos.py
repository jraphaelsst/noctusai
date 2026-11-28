"""The stages of a Diretor de Edição production run -- DATA (project ``diretor-edicao-reels``, contract section 4).

A run is a graph of seed ``media_production`` steps, one ledger row each (``cs_criacao_jobs``, migration 363: wall/cpu time,
vendor, units, cost, measurements, ``nao_medido``). The stages are the SKELETON: what each one DECIDES is behind a port
(:mod:`portas`) whose Real implementation is an open owner decision.

    recepcao -> estilo -> plano -> midia -> montagem -> checagens -> pacote
                                                                     (human review: the existing Aprovação final stage)

This module imports nothing from the product (``criacao_rotas`` imports it): constants, the stage table, the outcome enum
and the graph builder only.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.domain.media_production import GraphSpec, StepSpec
from noctusai_lib.domain.media_production.types import CANCELADO as PASSO_CANCELADO
from noctusai_lib.domain.media_production.types import CONCLUIDO as PASSO_CONCLUIDO
from noctusai_lib.domain.media_production.types import FALHOU as PASSO_FALHOU

from app.modules.media_creation.direcao.tipos import EntradaCongelada

ROTA_DIRIGIDO = "reel_dirigido"

PASSO_RECEPCAO = "direcao_recepcao"
PASSO_ESTILO = "direcao_estilo"
PASSO_PLANO = "direcao_plano"
PASSO_MIDIA = "direcao_midia"
PASSO_MONTAGEM = "direcao_montagem"
PASSO_CHECAGENS = "direcao_checagens"
PASSO_PACOTE = "direcao_pacote"

PASSOS_DIRECAO: tuple[str, ...] = (
    PASSO_RECEPCAO, PASSO_ESTILO, PASSO_PLANO, PASSO_MIDIA, PASSO_MONTAGEM, PASSO_CHECAGENS, PASSO_PACOTE,
)


@dataclass(frozen=True)
class Estagio:
    #: pt-BR gerund shown on the card ("Planejando as cenas (3/7)").
    rotulo: str
    #: expected duration in seconds -- the progress-bar weight ONLY. NOC-REMEDIATE[direcao-pesos-provisorios]: replace by
    #: the measured medians of the ledger (cs_criacao_jobs.duracao_s per passo) once the first real runs exist -- 2026-11-27.
    peso: float
    #: the stages whose output this one reads (the graph edges).
    depende_de: tuple[str, ...]
    #: which port decides here (None = deterministic, decision-free).
    porta: Optional[str] = None


ESTAGIOS: dict[str, Estagio] = {
    PASSO_RECEPCAO: Estagio("Recebendo o conteúdo aprovado", 1, ()),
    PASSO_ESTILO: Estagio("Escolhendo o estilo", 1, (PASSO_RECEPCAO,), porta="ResolvedorDeEstilo"),
    PASSO_PLANO: Estagio("Planejando as cenas", 20, (PASSO_RECEPCAO, PASSO_ESTILO), porta="PlanejadorDeCenas"),
    PASSO_MIDIA: Estagio("Gerando a mídia", 60, (PASSO_RECEPCAO, PASSO_PLANO), porta="GeradorDeMidia"),
    PASSO_MONTAGEM: Estagio("Montando o vídeo", 90, (PASSO_RECEPCAO, PASSO_PLANO, PASSO_MIDIA), porta="Montador"),
    PASSO_CHECAGENS: Estagio("Conferindo as medições", 6, (PASSO_PLANO, PASSO_MIDIA, PASSO_MONTAGEM)),
    PASSO_PACOTE: Estagio(
        "Preparando para revisão", 2, (PASSO_RECEPCAO, PASSO_PLANO, PASSO_MIDIA, PASSO_MONTAGEM, PASSO_CHECAGENS)
    ),
}

# ── the outcome enum of a run (closed; derived from the ledger, never a free string) ───────────────────────────────────

ENTREGUE_PARA_REVISAO = "entregue_para_revisao"
FALHOU = "falhou"
CANCELADO = "cancelado"
EM_ANDAMENTO = "em_andamento"
RESULTADOS = (ENTREGUE_PARA_REVISAO, FALHOU, CANCELADO, EM_ANDAMENTO)
# The HUMAN outcome that follows is not repeated here: ``midia_aprovada`` / ``midia_reprovada`` (migration 364) on the post.


def resultado_da_rodada(rows: list[Any], rodada: int) -> str:
    """The outcome of one ``rodada`` from its ledger rows (``PassoRow``-shaped: ``.rodada``, ``.status``)."""
    mine = [r for r in rows if r.rodada == rodada]
    if not mine:
        return EM_ANDAMENTO
    if any(r.status == PASSO_FALHOU for r in mine):
        return FALHOU
    if all(r.status == PASSO_CONCLUIDO for r in mine):
        return ENTREGUE_PARA_REVISAO
    if any(r.status == PASSO_CANCELADO for r in mine):
        return CANCELADO
    return EM_ANDAMENTO


def montar_grafo(
    entrada: EntradaCongelada, *, estimativas: Optional[dict[str, Decimal]] = None
) -> GraphSpec:
    """The seed graph of one run over ``entrada`` (``rodada`` is the entry's). ``estimativas`` = per-stage pre-flight USD
    (checked against the org quota before the stage runs; ``None`` = no vendor spend to check)."""
    estimativas = estimativas or {}
    specs: list[StepSpec] = []
    for nome in PASSOS_DIRECAO:
        e = ESTAGIOS[nome]
        entradas = {"entrada": entrada.para_dict()} if nome == PASSO_RECEPCAO else {}
        specs.append(StepSpec(nome, e.rotulo, e.depende_de, e.peso, estimativas.get(nome), entradas))
    return GraphSpec(entrada.org_id, entrada.post_id, tuple(specs), entrada.rodada)


__all__ = [
    "CANCELADO", "ENTREGUE_PARA_REVISAO", "EM_ANDAMENTO", "ESTAGIOS", "Estagio", "FALHOU", "PASSOS_DIRECAO", "PASSO_CHECAGENS",
    "PASSO_ESTILO", "PASSO_MIDIA", "PASSO_MONTAGEM", "PASSO_PACOTE", "PASSO_PLANO", "PASSO_RECEPCAO", "RESULTADOS",
    "ROTA_DIRIGIDO", "montar_grafo", "resultado_da_rodada",
]
