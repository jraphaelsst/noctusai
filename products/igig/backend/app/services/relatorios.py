"""Relatórios — comercial e financeiro (roadmap E1).

``gerar_relatorio`` is PURE DATA: given a ``Repositorios`` (the same seam
every other service composes) it returns a typed, dependency-free dataclass —
no FastAPI import, no HTTP concern, nothing that only makes sense inside a
request. That is deliberate: a future scheduled job, a cron-style worker, or
an MCP tool should be able to call

    gerar_relatorio(repos, org_id, "financeiro", date(2026, 8, 1), date(2026, 8, 31))

directly — the exact same call the HTTP route makes internally — and get the
identical structure back, with no server running. ``para_pdf``/``para_csv``
are pure renderers OVER that structure; they take no repository at all.

**Comercial.** Funnel movement, won/lost, loss reasons + dwell time,
orçamento funnel, avg ticket — read from `negocio` + `pipeline_movimentos` +
`orcamento` (the wave-2 CRM foundation, migrations 017/018), never from the
legacy Módulo-1 calculator.

**Financeiro.** Faturamento/recebido/a-receber/inadimplência plus a DRE-lite
per cliente. Revenue is scoped to `[inicio, fim]` by the invoice's
`competencia`; COST is not — it comes from `BIService`, the same source
`FinanceiroService.dre` uses, and that service's cost is measured over the
FULL apontamento history (there is no per-period cost breakdown yet). Stated
here, and carried into `alertas`, so nobody reads a period DRE as more precise
than it is.
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Literal

from app.repositories import Repositorios
from app.services.bi_service import BIService
from app.services.financeiro_service import FinanceiroService, limites_da_competencia

logger = logging.getLogger(__name__)

__all__ = [
    "TipoRelatorio",
    "PeriodoRelatorio",
    "EtapaFunil",
    "MotivoPerda",
    "RelatorioComercial",
    "ClienteFinanceiro",
    "RelatorioFinanceiro",
    "Relatorio",
    "gerar_relatorio",
    "para_pdf",
    "para_csv",
]

TipoRelatorio = Literal["comercial", "financeiro"]


# ── Date helpers ─────────────────────────────────────────────────────
def _competencia_no_periodo(competencia: str | None, inicio: date, fim: date) -> bool:
    """True when the calendar month `competencia` names overlaps [inicio, fim]."""
    if not competencia:
        return False
    try:
        ini_str, fim_str = limites_da_competencia(competencia)
    except ValueError:
        return False
    return date.fromisoformat(ini_str[:10]) <= fim and date.fromisoformat(fim_str[:10]) >= inicio


def _parse_dt(valor: object) -> datetime | None:
    if not valor:
        return None
    dt = datetime.fromisoformat(str(valor))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _data_no_periodo(valor: object, inicio: date, fim: date) -> bool:
    dt = _parse_dt(valor)
    if dt is None:
        return False
    return inicio <= dt.date() <= fim


# ── Comercial ────────────────────────────────────────────────────────
@dataclass(slots=True)
class PeriodoRelatorio:
    inicio: date
    fim: date


@dataclass(slots=True)
class EtapaFunil:
    etapa_id: str
    etapa_label: str
    #: Movements INTO this stage in the period.
    entradas: int = 0
    #: Movements OUT of this stage in the period (the next move recorded
    #: FROM here) — the funnel's "how many kept moving" half.
    saidas: int = 0

    @property
    def taxa_conversao(self) -> float:
        """Saídas over entradas. 0 when there were no entradas — not a
        division error; an empty stage converted nothing, it did not fail."""
        return round((self.saidas / self.entradas) * 100, 1) if self.entradas else 0.0


@dataclass(slots=True)
class MotivoPerda:
    motivo: str
    #: The stage the deal was in when it was marked perdido — a reason means
    #: something different at "Proposta enviada" than at "Primeiro contato".
    etapa_label: str
    quantidade: int
    valor_total: float


@dataclass(slots=True)
class RelatorioComercial:
    periodo: PeriodoRelatorio
    funil: list[EtapaFunil]
    negocios_ganhos: int
    negocios_ganhos_valor: float
    negocios_perdidos: int
    negocios_perdidos_valor: float
    motivos_perda: list[MotivoPerda]
    #: Average days between a lost deal entering its final stage and being
    #: marked perdido. 0 when nothing was lost in the period.
    dwell_time_medio_dias: float
    orcamentos_enviados: int
    orcamentos_aceitos: int
    orcamentos_recusados: int
    #: Average `total_mensal` of orçamentos ACCEPTED in the period. 0 when
    #: none were accepted — not a division error.
    ticket_medio: float
    alertas: list[str] = field(default_factory=list)


def _relatorio_comercial(
    repos: Repositorios, org_id: str, inicio: date, fim: date
) -> RelatorioComercial:
    stages = {
        str(s["id"]): s
        for s in repos.etapa.listar(org_id)
        if s.get("pipeline") == "comercial"
    }
    funil = {
        eid: EtapaFunil(etapa_id=eid, etapa_label=str(s.get("label") or eid))
        for eid, s in stages.items()
    }
    for mov in repos.movimento.listar(org_id):
        if mov.get("pipeline") != "comercial":
            continue
        if not _data_no_periodo(mov.get("created_at"), inicio, fim):
            continue
        destino = funil.get(str(mov.get("para_etapa_id")))
        if destino is not None:
            destino.entradas += 1
        origem = funil.get(str(mov.get("de_etapa_id")))
        if origem is not None:
            origem.saidas += 1

    negocios_ganhos = 0
    negocios_ganhos_valor = 0.0
    negocios_perdidos = 0
    negocios_perdidos_valor = 0.0
    dwell_dias: list[float] = []
    motivos: dict[tuple[str, str], MotivoPerda] = {}

    # Accepted orçamento's total_mensal is the REAL closed value; a negócio's
    # `valor_estimado` is only ever an estimate, kept as the fallback for
    # deals with no accepted proposal to point at.
    orcamentos = {str(o["id"]): o for o in repos.orcamento.listar(org_id)}

    for negocio in repos.negocio.listar(org_id):
        status = negocio.get("status")
        if status == "ganho" and _data_no_periodo(negocio.get("ganho_em"), inicio, fim):
            negocios_ganhos += 1
            orcamento = orcamentos.get(str(negocio.get("orcamento_aceito_id") or ""))
            valor = (
                float(orcamento["total_mensal"])
                if orcamento and orcamento.get("total_mensal")
                else float(negocio.get("valor_estimado") or 0)
            )
            negocios_ganhos_valor += valor
        elif status == "perdido" and _data_no_periodo(negocio.get("perdido_em"), inicio, fim):
            negocios_perdidos += 1
            valor = float(negocio.get("valor_estimado") or 0)
            negocios_perdidos_valor += valor

            entrada = _parse_dt(negocio.get("stage_entered_at"))
            saida = _parse_dt(negocio.get("perdido_em"))
            if entrada is not None and saida is not None:
                dwell_dias.append((saida - entrada).total_seconds() / 86400)

            etapa_label = str(
                stages.get(str(negocio.get("perdido_stage_id") or ""), {}).get("label")
                or "Sem etapa"
            )
            motivo = str(negocio.get("motivo_perda") or "Sem motivo").strip() or "Sem motivo"
            chave = (motivo, etapa_label)
            linha = motivos.setdefault(
                chave, MotivoPerda(motivo=motivo, etapa_label=etapa_label, quantidade=0, valor_total=0.0)
            )
            linha.quantidade += 1
            linha.valor_total += valor

    orcamentos_enviados = 0
    orcamentos_aceitos = 0
    orcamentos_recusados = 0
    tickets: list[float] = []
    for orcamento in orcamentos.values():
        if _data_no_periodo(orcamento.get("enviado_em"), inicio, fim):
            orcamentos_enviados += 1
        if _data_no_periodo(orcamento.get("aceito_em"), inicio, fim):
            orcamentos_aceitos += 1
            tickets.append(float(orcamento.get("total_mensal") or 0))
        if _data_no_periodo(orcamento.get("recusado_em"), inicio, fim):
            orcamentos_recusados += 1

    return RelatorioComercial(
        periodo=PeriodoRelatorio(inicio=inicio, fim=fim),
        funil=sorted(funil.values(), key=lambda e: e.etapa_label),
        negocios_ganhos=negocios_ganhos,
        negocios_ganhos_valor=round(negocios_ganhos_valor, 2),
        negocios_perdidos=negocios_perdidos,
        negocios_perdidos_valor=round(negocios_perdidos_valor, 2),
        motivos_perda=sorted(motivos.values(), key=lambda m: -m.quantidade),
        dwell_time_medio_dias=round(sum(dwell_dias) / len(dwell_dias), 1) if dwell_dias else 0.0,
        orcamentos_enviados=orcamentos_enviados,
        orcamentos_aceitos=orcamentos_aceitos,
        orcamentos_recusados=orcamentos_recusados,
        ticket_medio=round(sum(tickets) / len(tickets), 2) if tickets else 0.0,
    )


# ── Financeiro ───────────────────────────────────────────────────────
@dataclass(slots=True)
class ClienteFinanceiro:
    cliente_id: str
    cliente_nome: str
    faturamento: float = 0.0
    recebido: float = 0.0
    a_receber: float = 0.0
    #: Measured cost, ALL-TIME (see the module docstring) — not period-scoped.
    custo: float = 0.0

    @property
    def margem(self) -> float:
        return round(self.faturamento - self.custo, 2)

    @property
    def margem_percentual(self) -> float:
        return round((self.margem / self.faturamento) * 100, 1) if self.faturamento else 0.0


@dataclass(slots=True)
class RelatorioFinanceiro:
    periodo: PeriodoRelatorio
    faturamento: float
    recebido: float
    a_receber: float
    inadimplencia_valor: float
    inadimplencia_qtd: int
    clientes: list[ClienteFinanceiro]
    alertas: list[str] = field(default_factory=list)


def _relatorio_financeiro(
    repos: Repositorios, org_id: str, inicio: date, fim: date
) -> RelatorioFinanceiro:
    clientes = {
        str(c["id"]): ClienteFinanceiro(cliente_id=str(c["id"]), cliente_nome=str(c.get("nome") or ""))
        for c in repos.cliente.listar(org_id)
    }

    faturamento = 0.0
    recebido = 0.0
    a_receber = 0.0
    for fatura in repos.fatura.listar(org_id):
        if fatura.get("status") == "cancelada":
            continue
        if not _competencia_no_periodo(fatura.get("competencia"), inicio, fim):
            continue
        valor = float(fatura.get("valor_total") or 0)
        faturamento += valor
        alvo = clientes.get(str(fatura.get("cliente_id") or ""))
        if alvo is not None:
            alvo.faturamento += valor
        if fatura.get("status") == "paga":
            recebido += valor
            if alvo is not None:
                alvo.recebido += valor
        else:
            a_receber += valor
            if alvo is not None:
                alvo.a_receber += valor

    alertas: list[str] = []
    for eficiencia in BIService(repos).eficiencia_por_cliente(org_id):
        alvo = clientes.get(eficiencia.cliente_id)
        if alvo is not None:
            alvo.custo = eficiencia.custo_reais
    if any(c.custo for c in clientes.values()):
        alertas.append(
            "O custo por cliente é medido sobre TODO o histórico de apontamentos, "
            "não apenas sobre o período deste relatório — a margem por período "
            "acima é aproximada."
        )

    inadimplentes = [
        f for f in FinanceiroService(repos).inadimplentes(org_id)
        if _competencia_no_periodo(f.get("competencia"), inicio, fim)
    ]

    return RelatorioFinanceiro(
        periodo=PeriodoRelatorio(inicio=inicio, fim=fim),
        faturamento=round(faturamento, 2),
        recebido=round(recebido, 2),
        a_receber=round(a_receber, 2),
        inadimplencia_valor=round(sum(float(f["valor_total"]) for f in inadimplentes), 2),
        inadimplencia_qtd=len(inadimplentes),
        clientes=sorted(clientes.values(), key=lambda c: c.cliente_nome),
        alertas=alertas,
    )


# ── Wrapper + entrypoint ─────────────────────────────────────────────
@dataclass(slots=True)
class Relatorio:
    tipo: TipoRelatorio
    periodo: PeriodoRelatorio
    comercial: RelatorioComercial | None = None
    financeiro: RelatorioFinanceiro | None = None


def gerar_relatorio(
    repos: Repositorios, org_id: str, tipo: str, inicio: date, fim: date
) -> Relatorio:
    """Pure data. Callable from a route, a scheduled job, or an MCP tool —
    nothing here depends on a request being in flight.

    Raises ``ValueError`` on an invalid `tipo` or an inverted period; callers
    that sit behind HTTP turn that into a 422, same convention as every other
    service in this product (`limites_da_competencia`, `OrcamentoService.estimar`).
    """
    if inicio > fim:
        raise ValueError(f"período inválido: início ({inicio}) é depois do fim ({fim})")
    if tipo == "comercial":
        return Relatorio(
            tipo="comercial",
            periodo=PeriodoRelatorio(inicio=inicio, fim=fim),
            comercial=_relatorio_comercial(repos, org_id, inicio, fim),
        )
    if tipo == "financeiro":
        return Relatorio(
            tipo="financeiro",
            periodo=PeriodoRelatorio(inicio=inicio, fim=fim),
            financeiro=_relatorio_financeiro(repos, org_id, inicio, fim),
        )
    raise ValueError(f"tipo de relatório inválido: {tipo!r} (use 'comercial' ou 'financeiro')")


# ── Renderers ────────────────────────────────────────────────────────
def para_csv(relatorio: Relatorio) -> bytes:
    """A flat CSV — one section per collection the report carries.

    UTF-8 with a BOM: the sheet has accented pt-BR labels (`título`, `região`
    never appear here today, but the client names and motivo de perda text
    do), and Excel on Windows silently mis-decodes a BOM-less UTF-8 CSV.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([f"Relatório: {relatorio.tipo}",
                      f"Período: {relatorio.periodo.inicio} a {relatorio.periodo.fim}"])
    writer.writerow([])

    if relatorio.comercial is not None:
        c = relatorio.comercial
        writer.writerow(["Etapa", "Entradas", "Saídas", "Taxa de conversão (%)"])
        for etapa in c.funil:
            writer.writerow([etapa.etapa_label, etapa.entradas, etapa.saidas, etapa.taxa_conversao])
        writer.writerow([])
        writer.writerow(["Negócios ganhos", c.negocios_ganhos, "Valor", c.negocios_ganhos_valor])
        writer.writerow(["Negócios perdidos", c.negocios_perdidos, "Valor", c.negocios_perdidos_valor])
        writer.writerow(["Dwell time médio (dias)", c.dwell_time_medio_dias])
        writer.writerow([])
        writer.writerow(["Motivo de perda", "Etapa", "Quantidade", "Valor"])
        for m in c.motivos_perda:
            writer.writerow([m.motivo, m.etapa_label, m.quantidade, m.valor_total])
        writer.writerow([])
        writer.writerow(["Orçamentos enviados", c.orcamentos_enviados])
        writer.writerow(["Orçamentos aceitos", c.orcamentos_aceitos])
        writer.writerow(["Orçamentos recusados", c.orcamentos_recusados])
        writer.writerow(["Ticket médio", c.ticket_medio])

    if relatorio.financeiro is not None:
        f = relatorio.financeiro
        writer.writerow(["Faturamento", f.faturamento])
        writer.writerow(["Recebido", f.recebido])
        writer.writerow(["A receber", f.a_receber])
        writer.writerow(["Inadimplência (valor)", f.inadimplencia_valor])
        writer.writerow(["Inadimplência (qtd)", f.inadimplencia_qtd])
        writer.writerow([])
        writer.writerow(["Cliente", "Faturamento", "Recebido", "A receber", "Custo", "Margem", "Margem %"])
        for cl in f.clientes:
            writer.writerow([
                cl.cliente_nome, cl.faturamento, cl.recebido, cl.a_receber,
                cl.custo, cl.margem, cl.margem_percentual,
            ])
        for alerta in f.alertas:
            writer.writerow([])
            writer.writerow(["Alerta", alerta])

    return ("﻿" + buffer.getvalue()).encode("utf-8")


def para_pdf(relatorio: Relatorio) -> bytes:
    """A plain, readable one-column report — same rendering choice as
    `contrato_documento.gerar_pdf_contrato` (reportlab platypus, no template
    engine): until the agency supplies real templates, inventing a templating
    layer here would be speculative."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Relatório {relatorio.tipo}",
    )
    estilos = getSampleStyleSheet()
    titulo = "Relatório Comercial" if relatorio.tipo == "comercial" else "Relatório Financeiro"
    corpo: list = [
        Paragraph(titulo, estilos["Title"]),
        Paragraph(
            f"Período: {relatorio.periodo.inicio.isoformat()} a {relatorio.periodo.fim.isoformat()}",
            estilos["Normal"],
        ),
        Spacer(1, 0.5 * cm),
    ]

    def _tabela(cabecalho: list[str], linhas: list[list[object]]) -> Table:
        dados = [cabecalho] + [[str(v) for v in linha] for linha in linhas]
        tabela = Table(dados, hAlign="LEFT")
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ]))
        return tabela

    if relatorio.comercial is not None:
        c = relatorio.comercial
        corpo.append(Paragraph("Funil por etapa", estilos["Heading2"]))
        corpo.append(_tabela(
            ["Etapa", "Entradas", "Saídas", "Conversão %"],
            [[e.etapa_label, e.entradas, e.saidas, e.taxa_conversao] for e in c.funil],
        ))
        corpo.append(Spacer(1, 0.4 * cm))
        corpo.append(Paragraph(
            f"Ganhos: {c.negocios_ganhos} (R$ {c.negocios_ganhos_valor:,.2f})   ·  "
            f"Perdidos: {c.negocios_perdidos} (R$ {c.negocios_perdidos_valor:,.2f})   ·  "
            f"Dwell time médio: {c.dwell_time_medio_dias} dia(s)",
            estilos["Normal"],
        ))
        corpo.append(Spacer(1, 0.4 * cm))
        corpo.append(Paragraph("Motivos de perda", estilos["Heading2"]))
        corpo.append(_tabela(
            ["Motivo", "Etapa", "Qtd", "Valor"],
            [[m.motivo, m.etapa_label, m.quantidade, m.valor_total] for m in c.motivos_perda],
        ))
        corpo.append(Spacer(1, 0.4 * cm))
        corpo.append(Paragraph(
            f"Orçamentos — enviados: {c.orcamentos_enviados} · "
            f"aceitos: {c.orcamentos_aceitos} · recusados: {c.orcamentos_recusados} · "
            f"ticket médio: R$ {c.ticket_medio:,.2f}",
            estilos["Normal"],
        ))

    if relatorio.financeiro is not None:
        f = relatorio.financeiro
        corpo.append(Paragraph(
            f"Faturamento: R$ {f.faturamento:,.2f}   ·  "
            f"Recebido: R$ {f.recebido:,.2f}   ·  "
            f"A receber: R$ {f.a_receber:,.2f}   ·  "
            f"Inadimplência: R$ {f.inadimplencia_valor:,.2f} ({f.inadimplencia_qtd})",
            estilos["Normal"],
        ))
        corpo.append(Spacer(1, 0.4 * cm))
        corpo.append(Paragraph("Por cliente", estilos["Heading2"]))
        corpo.append(_tabela(
            ["Cliente", "Faturamento", "Recebido", "A receber", "Custo", "Margem", "Margem %"],
            [
                [cl.cliente_nome, cl.faturamento, cl.recebido, cl.a_receber,
                 cl.custo, cl.margem, cl.margem_percentual]
                for cl in f.clientes
            ],
        ))
        for alerta in f.alertas:
            corpo.append(Spacer(1, 0.3 * cm))
            corpo.append(Paragraph(f"<i>{alerta}</i>", estilos["Normal"]))

    doc.build(corpo)
    return buffer.getvalue()
