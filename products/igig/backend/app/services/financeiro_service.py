"""Financeiro — faturamento, excedentes e DRE (Módulo 6).

Two computations the agency's margin depends on:

**Itens excedentes.** The spec: "verifica se o número de posts produzidos
excedeu o pacote mensal contratado. Se sim, calcula e soma o valor adicional na
fatura do mês subsequente." So the count is of DELIVERED work in a competência,
compared against `contrato.posts_por_mes`, and the charge lands on the NEXT
month's invoice — billing it in the same month would invoice work the client
has not yet been billed the retainer for.

**DRE.** Revenue (invoiced) against the real cost of the hours booked to that
client. The cost comes from :class:`BIService`, not a second implementation —
"custo real do job" must mean one thing, or the DRE and the BI screen will
quietly disagree about the same client.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.repositories import Repositorios
from app.services.bi_service import BIService

__all__ = ["Excedente", "LinhaDRE", "FinanceiroService", "proxima_competencia"]


def proxima_competencia(competencia: str) -> str:
    """'2026-08' → '2026-09'. December rolls the year."""
    ano, mes = (int(p) for p in competencia.split("-"))
    return f"{ano + 1}-01" if mes == 12 else f"{ano}-{mes + 1:02d}"


@dataclass(slots=True)
class Excedente:
    cliente_id: str
    cliente_nome: str
    contrato_id: str
    competencia: str
    contratados: int
    entregues: int
    #: Never negative: delivering under the package is not a credit, and
    #: treating it as one would silently discount the retainer.
    excedentes: int
    valor_unitario: float
    valor_total: float
    #: The invoice this should land on — the month AFTER the work.
    competencia_cobranca: str


@dataclass(slots=True)
class LinhaDRE:
    cliente_id: str
    cliente_nome: str
    receita: float = 0.0
    custo: float = 0.0
    alertas: list[str] = field(default_factory=list)

    @property
    def margem(self) -> float:
        return round(self.receita - self.custo, 2)

    @property
    def margem_percentual(self) -> float:
        """Margin over revenue. 0 when there is no revenue — NOT a division error."""
        return round((self.margem / self.receita) * 100, 1) if self.receita else 0.0


class FinanceiroService:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    # ── Excedentes ──────────────────────────────────────────────────
    def excedentes(self, org_id: str, competencia: str) -> list[Excedente]:
        """Delivered-vs-contracted for every active contract in a month.

        "Delivered" means a pauta whose `data_publicacao` falls in the month.
        Counting tarefas instead would double-count a piece that took several
        steps, and counting publicacoes would miss anything published manually.
        """
        inicio = f"{competencia}-01T00:00:00"
        fim = f"{competencia}-31T23:59:59"
        entregues: dict[str, int] = {}
        for pauta in self._repos.pauta.no_periodo(org_id, inicio, fim):
            cid = str(pauta.get("cliente_id") or "")
            entregues[cid] = entregues.get(cid, 0) + 1

        clientes = {str(c["id"]): c for c in self._repos.cliente.listar(org_id)}
        saida: list[Excedente] = []
        for contrato in self._repos.contrato.ativos(org_id):
            cliente_id = str(contrato.get("cliente_id") or "")
            pacote = int(contrato.get("posts_por_mes") or 0)
            if not pacote:
                continue  # no package ⇒ nothing to exceed
            feitos = entregues.get(cliente_id, 0)
            extras = max(0, feitos - pacote)
            unitario = float(contrato.get("valor_excedente") or 0)
            saida.append(Excedente(
                cliente_id=cliente_id,
                cliente_nome=str(clientes.get(cliente_id, {}).get("nome") or ""),
                contrato_id=str(contrato["id"]),
                competencia=competencia,
                contratados=pacote,
                entregues=feitos,
                excedentes=extras,
                valor_unitario=unitario,
                valor_total=round(extras * unitario, 2),
                competencia_cobranca=proxima_competencia(competencia),
            ))
        return sorted(saida, key=lambda e: e.cliente_nome)

    # ── DRE ─────────────────────────────────────────────────────────
    def dre(self, org_id: str, competencia: str | None = None) -> list[LinhaDRE]:
        """Revenue vs real hour-cost, per client.

        `competencia` filters REVENUE only. Cost is the full measured history:
        the hours booked against a client are not partitioned by invoice month,
        and pretending otherwise would produce a margin that looks precise and
        is not. Stated here so the number is read correctly.
        """
        clientes = {str(c["id"]): c for c in self._repos.cliente.listar(org_id)}
        linhas = {
            cid: LinhaDRE(cliente_id=cid, cliente_nome=str(c.get("nome") or ""))
            for cid, c in clientes.items()
        }

        for fatura in self._repos.fatura.listar(org_id):
            if fatura.get("status") == "cancelada":
                continue
            if competencia and fatura.get("competencia") != competencia:
                continue
            alvo = linhas.get(str(fatura.get("cliente_id") or ""))
            if alvo is not None:
                alvo.receita += float(fatura.get("valor_total") or 0)

        for eficiencia in BIService(self._repos).eficiencia_por_cliente(org_id):
            alvo = linhas.get(eficiencia.cliente_id)
            if alvo is None:
                continue
            alvo.custo = eficiencia.custo_reais
            # Un-costed hours mean the margin is OVERSTATED here — the mirror
            # image of the BI screen's warning, and worth saying in those terms.
            alvo.alertas = [
                a.replace("custo real está SUBESTIMADO", "margem está SUPERESTIMADA")
                for a in eficiencia.alertas
            ]

        for alvo in linhas.values():
            alvo.receita = round(alvo.receita, 2)
        return sorted(linhas.values(), key=lambda l: l.cliente_nome)

    # ── Régua de cobrança ───────────────────────────────────────────
    def inadimplentes(self, org_id: str, *, hoje: date | None = None) -> list[dict]:
        """Overdue invoices, with days late.

        Drives both the dunning sequence and the Módulo 4 portal block. Returns
        data rather than acting on it: deciding to block a client's approval
        portal is a business action, not a side effect of running a report.
        """
        referencia = hoje or date.today()
        atrasadas: list[dict] = []
        for fatura in self._repos.fatura.listar(org_id):
            if fatura.get("status") in ("paga", "cancelada"):
                continue
            vencimento = fatura.get("vencimento")
            if not vencimento:
                continue
            venc = date.fromisoformat(str(vencimento)[:10])
            if venc >= referencia:
                continue
            atrasadas.append({
                "fatura_id": str(fatura["id"]),
                "cliente_id": str(fatura.get("cliente_id") or ""),
                "competencia": fatura.get("competencia"),
                "valor_total": float(fatura.get("valor_total") or 0),
                "vencimento": str(vencimento),
                "dias_atraso": (referencia - venc).days,
            })
        return sorted(atrasadas, key=lambda f: -f["dias_atraso"])
