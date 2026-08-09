"""Calculadora de Escopo — Módulo 1.

The spec: "inserir o volume de entregas desejado (ex: número de posts, vídeos,
artigos) e o sistema calcular o preço mínimo ideal com base na tabela de
custo/hora dos profissionais cadastrados."

So the chain is: volume → estimated hours → cost at the team's real hourly
rates → minimum price at the target margin. The cost half reuses the same
role-default/override model the BI and the DRE read, so a rate change moves
all three together instead of leaving the calculator quoting stale numbers.

**The suggestion is a floor, not a decision.** The spec explicitly allows
directors to override it, so `preco_sugerido` and `preco_final` are stored
separately — the gap between them is the discount granted, which is worth
knowing later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.repositories import Repositorios

__all__ = ["HORAS_POR_FORMATO", "ItemEscopo", "Estimativa", "OrcamentoService"]

#: Default hours per deliverable. Starting points, not truths — an agency
#: refines these from its own timesheet history, and Módulo 5's measured hours
#: are exactly the feedback loop that should replace them.
HORAS_POR_FORMATO: dict[str, float] = {
    "feed": 2.0,
    "carrossel": 3.5,
    "story": 0.5,
    "reels": 4.0,
    "video": 6.0,
    "artigo": 5.0,
}


@dataclass(frozen=True, slots=True)
class ItemEscopo:
    formato: str
    quantidade: int
    #: Overrides the default when the agency knows better for this client.
    horas_unitarias: float | None = None

    @property
    def horas(self) -> float:
        base = self.horas_unitarias
        if base is None:
            base = HORAS_POR_FORMATO.get(self.formato, 0.0)
        return round(base * self.quantidade, 2)


@dataclass(slots=True)
class Estimativa:
    horas: float
    custo: float
    preco_sugerido: float
    custo_hora_medio: float
    margem_alvo: float
    alertas: list[str] = field(default_factory=list)


class OrcamentoService:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def custo_hora_medio(self, org_id: str) -> tuple[float, list[str]]:
        """Average hourly cost across ACTIVE professionals.

        People with no resolvable rate are EXCLUDED and reported rather than
        counted as zero: averaging in a zero would drag the mean down and make
        the calculator quote below cost — the one failure mode that loses the
        agency money on every job it prices.
        """
        taxas: list[float] = []
        alertas: list[str] = []
        sem_taxa = 0
        for prof in self._repos.profissional.ativos(org_id):
            try:
                taxas.append(
                    self._repos.profissional.custo_hora_efetivo(
                        org_id, str(prof["id"]), funcoes=self._repos.funcao
                    )
                )
            except ValueError:
                sem_taxa += 1
        if sem_taxa:
            alertas.append(
                f"{sem_taxa} profissional(is) sem custo/hora definido — excluídos da média."
            )
        if not taxas:
            alertas.append(
                "Nenhum profissional com custo/hora definido: o preço sugerido é 0 "
                "e NÃO deve ser usado. Cadastre funções e custos antes de orçar."
            )
            return 0.0, alertas
        return round(sum(taxas) / len(taxas), 2), alertas

    def estimar(
        self, org_id: str, itens: list[ItemEscopo], *, margem_alvo: float = 50.0
    ) -> Estimativa:
        """Volume → hours → cost → minimum price.

        `margem_alvo` is a MARKUP on cost expressed as a percentage of the
        final price: at 50% the price is twice the cost. Anything at or above
        100% is rejected — the formula divides by (1 - margem/100), so 100%
        is an infinite price and beyond that a negative one.
        """
        if margem_alvo >= 100:
            raise ValueError("margem_alvo deve ser menor que 100%")
        if margem_alvo < 0:
            raise ValueError("margem_alvo não pode ser negativa")

        horas = round(sum(i.horas for i in itens), 2)
        taxa, alertas = self.custo_hora_medio(org_id)
        custo = round(horas * taxa, 2)
        preco = round(custo / (1 - margem_alvo / 100), 2) if custo else 0.0
        return Estimativa(
            horas=horas,
            custo=custo,
            preco_sugerido=preco,
            custo_hora_medio=taxa,
            margem_alvo=margem_alvo,
            alertas=alertas,
        )
