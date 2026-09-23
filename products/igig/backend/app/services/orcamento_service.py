"""Custo/hora spine for orçamentos — Módulo 1.

The spec: "o sistema calcular o preço mínimo ideal com base na tabela de
custo/hora dos profissionais cadastrados." The chain is: item volume →
estimated hours (`produto_servico.horas_estimadas` × quantidade mensal) → cost
at the team's REAL average hourly rate → the orçamento's live estimated margin
(`app/services/orcamentos.py::calcular_totais`). The rate half reuses the same
role-default/override model the BI and the DRE read, so a rate change moves
all three together instead of leaving the calculator quoting stale numbers.

The wave-2 orçamento (itens + recurrence, `routers/orcamento_router.py`)
replaced the old free-form `estimar` calculator; only the rate stays here.
"""
from __future__ import annotations

from app.repositories import Repositorios

__all__ = ["OrcamentoService"]


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
                "Nenhum profissional com custo/hora definido: custo e margem "
                "estimados ficam sem base e NÃO devem ser usados. Cadastre funções "
                "e custos antes de orçar."
            )
            return 0.0, alertas
        return round(sum(taxas) / len(taxas), 2), alertas
