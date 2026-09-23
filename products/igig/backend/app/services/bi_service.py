"""BI Interno de Eficiência — Módulo 5.

The spec asks for two numbers per client: **taxa de refação** and **custo real
do job** from measured timesheet hours. Both are computable today from data
IgIg already has — `tarefa.refacoes`, `apontamento.minutos`, and the
role-default/override cost model from Módulo 2's decisions — so this module has
no external dependency and no placeholder.

Everything here is a pure aggregation over the repositories. It is a SERVICE
rather than router code because Módulo 6's DRE consumes the same numbers: the
margin per account is this cost set against the contract's revenue, and having
two definitions of "custo real do job" would make the two screens disagree.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.repositories import Repositorios

__all__ = ["EficienciaCliente", "BIService"]


@dataclass(slots=True)
class EficienciaCliente:
    """Efficiency rollup for one client."""

    cliente_id: str
    cliente_nome: str
    tarefas: int = 0
    refacoes: int = 0
    minutos: int = 0
    custo_reais: float = 0.0
    #: Tasks whose hours could not be costed (no rate for the person who
    #: logged them). Surfaced rather than silently treated as free — see
    #: `custo_indefinido` handling in :meth:`BIService.eficiencia_por_cliente`.
    apontamentos_sem_custo: int = 0
    alertas: list[str] = field(default_factory=list)

    @property
    def taxa_refacao(self) -> float:
        """Refações per task. 0 when there are no tasks (not a division error)."""
        return round(self.refacoes / self.tarefas, 3) if self.tarefas else 0.0

    @property
    def horas(self) -> float:
        return round(self.minutos / 60, 2)


@dataclass(slots=True)
class _Custos:
    """Rates keyed both ways, and the ONE rule for which key an apontamento uses.

    A segment recorded since migration 017 carries the timer's
    `profissional_id` (the team record `tarefa.responsavel_id` also points
    at); older segments only have the auth `usuario_id`, resolved through
    `profissional.usuario_id`.
    """

    por_profissional: dict[str, float | None] = field(default_factory=dict)
    por_usuario: dict[str, float | None] = field(default_factory=dict)

    def taxa(self, apontamento: dict) -> float | None:
        profissional_id = apontamento.get("profissional_id")
        if profissional_id:
            return self.por_profissional.get(str(profissional_id))
        return self.por_usuario.get(str(apontamento.get("usuario_id")))


class BIService:
    """Aggregations over tarefas, apontamentos and the custo/hora model."""

    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    def _custos(self, org_id: str) -> "_Custos":
        """Effective hourly rate per `profissional_id` AND per `usuario_id`.

        `None` means "this person has no resolvable rate" — distinct from 0.0,
        which is a real rate (an unpaid intern). Collapsing the two would
        silently understate the cost of every job they touched.
        """
        custos = _Custos()
        for prof in self._repos.profissional.listar(org_id):
            try:
                taxa: float | None = self._repos.profissional.custo_hora_efetivo(
                    org_id, str(prof["id"]), funcoes=self._repos.funcao
                )
            except ValueError:
                taxa = None
            custos.por_profissional[str(prof["id"])] = taxa
            if prof.get("usuario_id"):
                custos.por_usuario[str(prof["usuario_id"])] = taxa
        return custos

    def eficiencia_por_cliente(self, org_id: str) -> list[EficienciaCliente]:
        """Taxa de refação + custo real do job, per client.

        One pass over each collection rather than per-client queries: the
        report always renders every client, so N+1 round-trips would buy
        nothing.
        """
        clientes = {str(c["id"]): c for c in self._repos.cliente.listar(org_id)}
        resultado = {
            cid: EficienciaCliente(cliente_id=cid, cliente_nome=str(c.get("nome") or ""))
            for cid, c in clientes.items()
        }

        # pauta → cliente, so a tarefa can be attributed without a join.
        pauta_para_cliente = {
            str(p["id"]): str(p.get("cliente_id") or "")
            for p in self._repos.pauta.listar(org_id)
        }
        tarefa_para_cliente: dict[str, str] = {}

        for tarefa in self._repos.tarefa.listar(org_id):
            cliente_id = pauta_para_cliente.get(str(tarefa.get("pauta_id")), "")
            alvo = resultado.get(cliente_id)
            if alvo is None:
                continue
            tarefa_para_cliente[str(tarefa["id"])] = cliente_id
            alvo.tarefas += 1
            alvo.refacoes += int(tarefa.get("refacoes") or 0)

        custos = self._custos(org_id)
        for apontamento in self._repos.apontamento.listar(org_id):
            cliente_id = tarefa_para_cliente.get(str(apontamento.get("tarefa_id")), "")
            alvo = resultado.get(cliente_id)
            if alvo is None:
                continue
            minutos = int(apontamento.get("minutos") or 0)
            alvo.minutos += minutos
            taxa = custos.taxa(apontamento)
            if taxa is None:
                # Unknown rate: count it, never treat it as free.
                alvo.apontamentos_sem_custo += 1
                continue
            alvo.custo_reais += (minutos / 60) * taxa

        for alvo in resultado.values():
            alvo.custo_reais = round(alvo.custo_reais, 2)
            if alvo.apontamentos_sem_custo:
                alvo.alertas.append(
                    f"{alvo.apontamentos_sem_custo} apontamento(s) sem custo/hora definido — "
                    "o custo real está SUBESTIMADO."
                )

        return sorted(resultado.values(), key=lambda e: e.cliente_nome)

    def custo_da_tarefa(self, org_id: str, tarefa_id: str) -> tuple[float, list[str]]:
        """Measured cost of ONE tarefa, plus any alerts.

        Returns alerts rather than raising: a single un-costed segment should
        not blank out an otherwise useful number, but it must not be invisible
        either.
        """
        custos = self._custos(org_id)
        total = 0.0
        alertas: list[str] = []
        for apontamento in self._repos.apontamento.da_tarefa(org_id, tarefa_id):
            taxa = custos.taxa(apontamento)
            minutos = int(apontamento.get("minutos") or 0)
            if taxa is None:
                alertas.append(
                    f"apontamento {apontamento.get('id')} sem custo/hora — não somado"
                )
                continue
            total += (minutos / 60) * taxa
        return round(total, 2), alertas
