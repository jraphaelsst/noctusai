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

import calendar
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from noctusai_lib.integrations.email import Attachment, OutgoingEmail
from noctusai_lib.integrations.email.errors import EmailError
from noctusai_lib.integrations.persistence import RecordNotFound, SupabaseRecordStore, UniqueViolation

from app.email_deps import EmailSenderFactory
from app.repositories import Repositorios
from app.services import documentos_pdf, email_config
from app.services.bi_service import BIService
from app.services.email_config import EmailSettings
from app.services.regras import RegraViolada
from app.services.varredura import linhas_cross_org

logger = logging.getLogger(__name__)

__all__ = [
    "Excedente",
    "LinhaDRE",
    "ResumoFinanceiro",
    "FinanceiroService",
    "proxima_competencia",
    "competencia_anterior",
    "limites_da_competencia",
    "alertas_de_margem",
    "cliente_bloqueado_no_portal",
    "atualizar_inadimplencia",
    "enviar_fatura",
    "FATURA_FECHADA",
]

_COMPETENCIA = re.compile(r"^(\d{4})-(\d{2})$")

#: Statuses an invoice cannot be re-sent from / add lines to. Canonical here;
#: `financeiro_router.py` imports it rather than keeping its own copy.
FATURA_FECHADA = frozenset({"paga", "cancelada"})


def limites_da_competencia(competencia: str) -> tuple[str, str]:
    """First and last instant of a `YYYY-MM` month, as ISO strings.

    🔴 The last day comes from the calendar, never a literal `-31`: Postgres
    rejects `2026-02-31T23:59:59` as a timestamp, so every month shorter than
    31 days 500'd in production (smoke finding 1, 2026-09-22) while the SQLite
    suite — which compares these as TEXT — stayed green.

    Raises ``ValueError`` on anything that is not a real `YYYY-MM`; the router
    turns that into a 422 instead of letting `int()` crash into a 500.
    """
    casou = _COMPETENCIA.match(competencia or "")
    if not casou:
        raise ValueError(f"competência inválida: {competencia!r}; esperado AAAA-MM")
    ano, mes = int(casou.group(1)), int(casou.group(2))
    if not 1 <= mes <= 12:
        raise ValueError(f"competência inválida: {competencia!r}; mês fora de 01-12")
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return (
        f"{ano:04d}-{mes:02d}-01T00:00:00",
        f"{ano:04d}-{mes:02d}-{ultimo_dia:02d}T23:59:59.999999",
    )


def proxima_competencia(competencia: str) -> str:
    """'2026-08' → '2026-09'. December rolls the year."""
    ano, mes = (int(p) for p in competencia.split("-"))
    return f"{ano + 1}-01" if mes == 12 else f"{ano}-{mes + 1:02d}"


def competencia_anterior(competencia: str) -> str:
    """'2026-09' → '2026-08'. January rolls back the year. Inverse of
    :func:`proxima_competencia` — used to find which delivery month's
    excedentes land on a given invoice month (see `gerar_faturas_da_competencia`)."""
    ano, mes = (int(p) for p in competencia.split("-"))
    return f"{ano - 1}-12" if mes == 1 else f"{ano}-{mes - 1:02d}"


def _vencimento(competencia: str, dia_vencimento: int | None) -> str | None:
    """The invoice due date for a competência, given the contract's
    `dia_vencimento`. `None` when the contract names no day — an invoice
    without a due date is legitimate (the payment terms are handled
    manually), not an error."""
    if not dia_vencimento:
        return None
    ano, mes = (int(p) for p in competencia.split("-"))
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(int(dia_vencimento), ultimo_dia)
    return f"{ano:04d}-{mes:02d}-{dia:02d}"


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


def alertas_de_margem(alertas_de_custo: list[str]) -> list[str]:
    """Reword a BI "custo real" alert as its margin mirror image.

    Un-costed hours understate cost, which means they OVERSTATE any margin
    computed from that cost — the same fact, read from the other side. Used
    by both `FinanceiroService.dre` and `relatorios._relatorio_financeiro` so
    the two surfaces say it identically instead of drifting (finding #15,
    2026-09 audit: the relatório used to drop this warning entirely).
    """
    return [
        # The article moves with the noun: "O custo real está SUBESTIMADO" →
        # "A margem está SUPERESTIMADA". Replacing only the noun phrase left
        # "o margem", which reads as a typo in a warning meant to be taken
        # seriously.
        a.replace("o custo real está SUBESTIMADO", "a margem está SUPERESTIMADA")
         .replace("custo real está SUBESTIMADO", "margem está SUPERESTIMADA")
        for a in alertas_de_custo
    ]


@dataclass(slots=True)
class ResumoFinanceiro:
    competencia: str | None
    #: Current monthly recurring revenue — the sum of every ACTIVE contract's
    #: `valor_mensal`, independent of `competencia` (a snapshot of NOW, not of
    #: the filtered month).
    mrr: float
    #: Open invoices (not paga, not cancelada) — `competencia`-scoped when given.
    a_receber: float
    #: Paid invoices — `competencia`-scoped when given.
    recebido: float
    inadimplente_valor: float
    inadimplente_qtd: int


class FinanceiroService:
    def __init__(self, repos: Repositorios) -> None:
        self._repos = repos

    # ── Excedentes ──────────────────────────────────────────────────
    def _entregue_em(self, org_id: str, pauta: dict) -> str | None:
        """The date a pauta was actually DELIVERED, or `None` when it never
        was — two signals, in this priority:

          1. `pauta.publicado_em` — `publicacao_publisher` actually posted
             it; the strongest signal there is.
          2. The EARLIEST `aprovacao.decisao == 'aprovado'` recorded against
             any of the pauta's tarefas — the client signed off, which is
             what "delivered" means in practice today, since no channel's
             real publish is homologated yet (`publicado_em` never fires).

        Replaces the previous `data_publicacao` (the SCHEDULED date) signal:
        a piece that slipped, or was pulled after being scheduled, used to
        still bill as delivered (finding #10).
        """
        if pauta.get("publicado_em"):
            return str(pauta["publicado_em"])
        aprovados: list[str] = []
        for tarefa in self._repos.tarefa.do_pauta(org_id, str(pauta["id"])):
            for aprovacao in self._repos.aprovacao.da_tarefa(org_id, str(tarefa["id"])):
                if aprovacao.get("decisao") == "aprovado" and aprovacao.get("decidido_em"):
                    aprovados.append(str(aprovacao["decidido_em"]))
        return min(aprovados) if aprovados else None

    def _contrato_do_pauta_plano(
        self, org_id: str, orcamento_item_id: str, cache: dict[str, str | None]
    ) -> str | None:
        """The ONE contrato a PLAN pauta belongs to, via `orcamento_item_id`
        → `orcamento_item.orcamento_id` → `contrato.orcamento_id`. Memoized
        per :meth:`excedentes` call — every pauta a recurring item generated
        asks the same question."""
        if orcamento_item_id in cache:
            return cache[orcamento_item_id]
        contrato_id: str | None = None
        try:
            item = self._repos.orcamento_item.buscar(org_id, orcamento_item_id)
            contratos = self._repos.contrato.do_orcamento(org_id, str(item["orcamento_id"]))
            if len(contratos) == 1:
                contrato_id = str(contratos[0]["id"])
            elif len(contratos) > 1:
                logger.warning(
                    "excedentes: org=%s orçamento=%s tem %d contratos — pauta do plano "
                    "não atribuída a nenhum.", org_id, item["orcamento_id"], len(contratos),
                )
        except RecordNotFound:
            logger.warning(
                "excedentes: org=%s orcamento_item %s inexistente para uma pauta do plano",
                org_id, orcamento_item_id,
            )
        cache[orcamento_item_id] = contrato_id
        return contrato_id

    def excedentes(self, org_id: str, competencia: str) -> list[Excedente]:
        """Delivered-vs-contracted for every active PACKAGED contract in a
        month — see :meth:`_entregue_em` for what "delivered" means.

        **A plan pauta can never be an excedente**, no matter how many of it
        a given month produces. `contrato.posts_por_mes` is priced off a flat
        `dias_semana × qtd_por_dia × 4 semanas` convention
        (`orcamentos.quantidade_mensal`) — a real calendar does not have
        exactly 4 of every weekday every month (a 31-day month starting on a
        Monday has 5), so a month where the SAME recurring item produces one
        extra piece is not the client asking for more; it is the calendar.
        Billing that variance as an excedente would charge for pieces that
        ARE the retainer. So a pauta traced back to the accepted orçamento's
        own recurring item (`gerada_automaticamente=True` with an
        `orcamento_item_id`) is excluded from the excedente count on BOTH
        sides — it never contributes to `entregues` for billing purposes and
        can never trigger one.

        **Excedentes are hand-added pautas beyond the plan** — anything NOT
        traced to the plan (created directly on the Calendário Editorial, or
        a "Nova tarefa" pointing at a pauta with no orçamento origin), still
        measured against the SAME `posts_por_mes` the plan itself is priced
        from. Worked example: `scratchpad/kb/delta-closeout.md`.

        Attribution: a plan pauta's contrato is unambiguous
        (`orcamento_item_id` → one orçamento → at most one contrato, since
        the product issues at most one contrato per orçamento). An EXTRA
        pauta only carries `cliente_id`, so it is attributed to that
        cliente's active packaged contrato IF there is exactly one — a
        cliente with two is logged and skipped rather than guessed (finding
        #10's original ambiguity, now narrowed to hand-created pautas only —
        the plan side no longer has this problem at all).
        """
        inicio, fim = limites_da_competencia(competencia)
        clientes = {str(c["id"]): c for c in self._repos.cliente.listar(org_id)}

        contratos_ativos = self._repos.contrato.ativos(org_id)
        pacote_por_cliente: dict[str, list[dict]] = {}
        for c in contratos_ativos:
            if int(c.get("posts_por_mes") or 0):
                pacote_por_cliente.setdefault(str(c.get("cliente_id") or ""), []).append(c)

        plano_por_contrato: dict[str, int] = {}
        extras_por_contrato: dict[str, int] = {}
        cache_item_contrato: dict[str, str | None] = {}

        for pauta in self._repos.pauta.listar(org_id):
            entregue_em = self._entregue_em(org_id, pauta)
            if not entregue_em or not (inicio[:10] <= entregue_em[:10] <= fim[:10]):
                continue
            if pauta.get("gerada_automaticamente") and pauta.get("orcamento_item_id"):
                contrato_id = self._contrato_do_pauta_plano(
                    org_id, str(pauta["orcamento_item_id"]), cache_item_contrato,
                )
                if contrato_id:
                    plano_por_contrato[contrato_id] = plano_por_contrato.get(contrato_id, 0) + 1
                continue
            cliente_id = str(pauta.get("cliente_id") or "")
            candidatos = pacote_por_cliente.get(cliente_id, [])
            if len(candidatos) != 1:
                if len(candidatos) > 1:
                    logger.warning(
                        "excedentes: org=%s cliente=%s tem %d contratos ativos com "
                        "pacote — pauta extra não atribuída a nenhum.",
                        org_id, cliente_id, len(candidatos),
                    )
                continue
            contrato_id = str(candidatos[0]["id"])
            extras_por_contrato[contrato_id] = extras_por_contrato.get(contrato_id, 0) + 1

        saida: list[Excedente] = []
        for contrato in contratos_ativos:
            pacote = int(contrato.get("posts_por_mes") or 0)
            if not pacote:
                continue  # no package ⇒ nothing to exceed
            contrato_id = str(contrato["id"])
            cliente_id = str(contrato.get("cliente_id") or "")
            extras = extras_por_contrato.get(contrato_id, 0)
            plano = plano_por_contrato.get(contrato_id, 0)
            excedentes_qtd = max(0, extras - pacote)
            unitario = float(contrato.get("valor_excedente") or 0)
            saida.append(Excedente(
                cliente_id=cliente_id,
                cliente_nome=str(clientes.get(cliente_id, {}).get("nome") or ""),
                contrato_id=contrato_id,
                competencia=competencia,
                contratados=pacote,
                entregues=plano + extras,
                excedentes=excedentes_qtd,
                valor_unitario=unitario,
                valor_total=round(excedentes_qtd * unitario, 2),
                competencia_cobranca=proxima_competencia(competencia),
            ))
        return sorted(saida, key=lambda e: e.cliente_nome)

    # ── DRE ─────────────────────────────────────────────────────────
    def dre(
        self, org_id: str, competencia: str | None = None, *, custo_por_competencia: bool = False
    ) -> list[LinhaDRE]:
        """Revenue vs real hour-cost, per client.

        `competencia` always filters REVENUE. What it does to COST depends on
        `custo_por_competencia`:

        - `False` (the default — what the M6 DRE screen always passes): cost
          is the full measured history. The hours booked against a client are
          not partitioned by invoice month on that screen by design — the UI
          says so explicitly ("custo real é sempre o histórico completo") —
          and pretending otherwise there would produce a margin that looks
          precise and is not.
        - `True`: cost is scoped to the SAME `competencia` as revenue — hours
          apontadas in that month, via `BIService.eficiencia_por_cliente`'s
          own `competencia` filter. Requires `competencia`; a caller asking
          for a month-scoped cost with no month makes no sense and raises
          rather than silently falling back to all-time (finding: the
          Dashboard's "Margem no mês" compared a month's revenue against
          all-time cost — a margin that got MORE wrong every month the
          agency operated, never shown as anything but a precise number).
        """
        if custo_por_competencia and not competencia:
            raise ValueError("custo_por_competencia requer uma competência")
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

        custo_competencia = competencia if custo_por_competencia else None
        for eficiencia in BIService(self._repos).eficiencia_por_cliente(org_id, custo_competencia):
            alvo = linhas.get(eficiencia.cliente_id)
            if alvo is None:
                continue
            alvo.custo = eficiencia.custo_reais
            alvo.alertas = alertas_de_margem(eficiencia.alertas)

        for alvo in linhas.values():
            alvo.receita = round(alvo.receita, 2)
        return sorted(linhas.values(), key=lambda l: l.cliente_nome)

    # ── Fechamento mensal ───────────────────────────────────────────
    def gerar_faturas_da_competencia(self, org_id: str, competencia: str) -> dict:
        """Open (or find) this month's invoice for every active contract.

        Idempotent per contrato ativo × competência: a contract that already
        has a non-cancelled invoice for this month is reported under
        `existentes` rather than billed a second time — the same guarantee
        the manual `POST /faturas` unique index gives, applied to the whole
        active book at once. Each NEW invoice carries a "Retainer mensal"
        line (`contrato.valor_mensal`) plus any excedentes DELIVERED the
        month before and billed onto this one (see the module docstring —
        the charge always lands on the month after the work).

        An invoice that ALREADY EXISTED for this competência (e.g. the close
        ran once before the excedentes were finished being computed) also
        gets its excedente line added here if it is missing one — idempotent
        by description (`descricao == "Excedentes de {mes_entrega}"`), so
        re-running never duplicates the line (finding #11, 2026-09 audit: this
        used to be silently skipped for every already-existing invoice).

        A concurrent close racing this one on the SAME contract+competência
        is caught at the unique index rather than surfacing as a 500 — the
        just-created row (by the other request) is looked up and reported
        under `existentes`, exactly like a genuinely pre-existing one
        (finding #9, 2026-09 audit).
        """
        limites_da_competencia(competencia)  # raises ValueError on malformed
        mes_entrega = competencia_anterior(competencia)
        excedentes_por_contrato = {
            e.contrato_id: e
            for e in self.excedentes(org_id, mes_entrega)
            if e.competencia_cobranca == competencia
        }
        existentes_por_contrato = {
            str(f["contrato_id"]): f
            for f in self._repos.fatura.da_competencia(org_id, competencia)
            # A cancelled invoice does not hold the slot — the DB's own
            # unique index (`idx_igig_fatura_competencia`) excludes it too.
            if f.get("contrato_id") and f.get("status") != "cancelada"
        }
        descricao_excedente = f"Excedentes de {mes_entrega}"

        criadas: list[dict] = []
        existentes: list[dict] = []
        for contrato in self._repos.contrato.ativos(org_id):
            contrato_id = str(contrato["id"])
            excedente = excedentes_por_contrato.get(contrato_id)

            ja_existente = existentes_por_contrato.get(contrato_id)
            if ja_existente is not None:
                self._garantir_linha_excedente(
                    org_id, ja_existente, excedente, descricao_excedente
                )
                existentes.append(ja_existente)
                continue

            try:
                fatura = self._repos.fatura.criar(org_id, {
                    "cliente_id": contrato["cliente_id"],
                    "contrato_id": contrato_id,
                    "competencia": competencia,
                    "vencimento": _vencimento(competencia, contrato.get("dia_vencimento")),
                })
            except UniqueViolation:
                # Another request closed this exact contrato+competência
                # first — the unique index caught the race. Not a 500: the
                # slot is filled either way, so this is "already existed".
                # Catching the specific member (not `PersistenceError`) means
                # an unrelated write failure here surfaces as a real error
                # instead of being silently folded into "already existed".
                logger.info(
                    "gerar_competencia: corrida no índice único org=%s contrato=%s "
                    "competencia=%s — tratando como já existente", org_id, contrato_id, competencia,
                )
                ja_criada = next(
                    (f for f in self._repos.fatura.da_competencia(org_id, competencia)
                     if str(f.get("contrato_id")) == contrato_id and f.get("status") != "cancelada"),
                    None,
                )
                if ja_criada is not None:
                    existentes.append(ja_criada)
                continue

            self._repos.fatura_item.criar(org_id, {
                "fatura_id": fatura["id"],
                "descricao": "Retainer mensal",
                "tipo": "mensalidade",
                "quantidade": 1,
                "valor_unit": float(contrato.get("valor_mensal") or 0),
            })
            if excedente is not None and excedente.excedentes > 0:
                self._repos.fatura_item.criar(org_id, {
                    "fatura_id": fatura["id"],
                    "descricao": descricao_excedente,
                    "tipo": "excedente",
                    "quantidade": excedente.excedentes,
                    "valor_unit": excedente.valor_unitario,
                })
            itens = self._repos.fatura_item.da_fatura(org_id, fatura["id"])
            criadas.append(self._repos.fatura.recalcular_total(org_id, fatura["id"], itens))

        return {"criadas": criadas, "existentes": existentes}

    def _garantir_linha_excedente(
        self, org_id: str, fatura: dict, excedente: Excedente | None, descricao: str
    ) -> None:
        """Add the "Excedentes de {mês}" line to an ALREADY-EXISTING invoice
        if it should have one and does not yet — the idempotency check is the
        line's own description, so calling this twice never duplicates it. A
        closed invoice (`paga`/`cancelada`) is left alone: it cannot accept
        new lines (see `financeiro_router.adicionar_item`'s own guard)."""
        if excedente is None or excedente.excedentes <= 0:
            return
        if fatura.get("status") in ("paga", "cancelada"):
            return
        itens = self._repos.fatura_item.da_fatura(org_id, str(fatura["id"]))
        if any(i.get("descricao") == descricao for i in itens):
            return
        self._repos.fatura_item.criar(org_id, {
            "fatura_id": fatura["id"],
            "descricao": descricao,
            "tipo": "excedente",
            "quantidade": excedente.excedentes,
            "valor_unit": excedente.valor_unitario,
        })
        itens = self._repos.fatura_item.da_fatura(org_id, str(fatura["id"]))
        fatura.update(self._repos.fatura.recalcular_total(org_id, str(fatura["id"]), itens))

    # ── Resumo ───────────────────────────────────────────────────────
    def resumo(self, org_id: str, competencia: str | None = None) -> ResumoFinanceiro:
        """A receber, recebido, inadimplente e MRR — the financeiro snapshot.

        `competencia` scopes `a_receber`/`recebido`/`inadimplente_*`; `mrr` is
        always the CURRENT active book, since a recurring-revenue figure
        filtered to a past month would answer a different question than "what
        do we bill every month right now".
        """
        if competencia:
            limites_da_competencia(competencia)  # raises ValueError on malformed
        mrr = round(
            sum(float(c.get("valor_mensal") or 0) for c in self._repos.contrato.ativos(org_id)), 2
        )

        faturas = (
            self._repos.fatura.da_competencia(org_id, competencia)
            if competencia else self._repos.fatura.listar(org_id)
        )
        a_receber = 0.0
        recebido = 0.0
        for fatura in faturas:
            status = fatura.get("status")
            if status == "cancelada":
                continue
            valor = float(fatura.get("valor_total") or 0)
            if status == "paga":
                recebido += valor
            else:
                a_receber += valor

        atrasadas = self.inadimplentes(org_id)
        if competencia:
            atrasadas = [f for f in atrasadas if f["competencia"] == competencia]

        return ResumoFinanceiro(
            competencia=competencia,
            mrr=mrr,
            a_receber=round(a_receber, 2),
            recebido=round(recebido, 2),
            inadimplente_valor=round(sum(f["valor_total"] for f in atrasadas), 2),
            inadimplente_qtd=len(atrasadas),
        )

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


def cliente_bloqueado_no_portal(
    repos: Repositorios, org_id: str, cliente_id: str, *,
    dias_bloqueio: int, hoje: date | None = None,
) -> bool:
    """Should the Módulo 4 approval portal refuse this cliente right now?

    Pure and side-effect-free — this only ANSWERS, it never writes anything
    and never renders a response. The portal router (owned by another
    slice — this module does NOT touch `esteira_router.py`) calls it once
    the aprovação token has resolved the org+cliente, and on `True` answers
    with a pt-BR "Portal temporariamente indisponível, contate a agência."
    instead of the normal approval UI.

    OFF by default: `dias_bloqueio <= 0` (the `IGIG_PORTAL_BLOQUEIO_DIAS`
    env setting, 0/absent) always returns `False` — blocking a client's
    ability to approve work is a decision an agency opts into, never a side
    effect of the daily inadimplência sweep landing.

    Reads live overdue state via `FinanceiroService.inadimplentes` (the SAME
    query the Financeiro page's red banner uses) rather than the cliente's
    `status` column — the portal block must not wait for the daily job to
    have run today.
    """
    if dias_bloqueio <= 0:
        return False
    referencia = hoje or date.today()
    for fatura in FinanceiroService(repos).inadimplentes(org_id, hoje=referencia):
        if fatura["cliente_id"] == cliente_id and fatura["dias_atraso"] > dias_bloqueio:
            return True
    return False


async def atualizar_inadimplencia(db: Any, *, hoje: date | None = None) -> dict:
    """Daily cross-org sweep — the writer `ClienteRepository.marcar_inadimplente`
    never had (finding #12, 2026-09 audit).

      1. Every `aberta`/`enviada` fatura past its `vencimento` → `vencida`.
      2. Every cliente with at least one `vencida` fatura (from today's sweep
         OR an earlier one) → `inadimplente`.
      3. Every `inadimplente` cliente with NONE → back to `ativo` — the "back
         to ativo when cleared" half nothing else in the product does.

    `db` is the igig SERVICE-ROLE client — the sweep crosses every org, the
    same shape `automacoes.varrer_sla`/`job_automacoes_sla` uses, and for the
    same reason: `Repositorios`/`RecordStore` require an `org_id` on every
    call by construction (the SQLite dev adapter cannot even express a
    cross-org query), so the cross-org DISCOVERY step goes through
    `app.services.varredura.linhas_cross_org` (paged, raw client); every
    row-level write below still goes through `Repositorios` (built over the
    SAME client), scoped to that row's own `org_id`.
    """
    referencia = hoje or date.today()
    repos = Repositorios(SupabaseRecordStore(db))
    resumo = {"faturas_vencidas": 0, "clientes_inadimplentes": 0, "clientes_normalizados": 0}

    vencidas_por_org: dict[str, set[str]] = {}

    abertas = linhas_cross_org(
        db, "fatura",
        filtros=lambda q: q.not_.in_("status", ["paga", "cancelada", "vencida"]),
        label="igig.fatura (inadimplência: abertas)",
    )
    for fatura in abertas:
        vencimento = fatura.get("vencimento")
        if not vencimento:
            continue
        if date.fromisoformat(str(vencimento)[:10]) >= referencia:
            continue
        org_id = str(fatura["org_id"])
        repos.fatura.atualizar(org_id, str(fatura["id"]), {"status": "vencida"})
        resumo["faturas_vencidas"] += 1
        vencidas_por_org.setdefault(org_id, set()).add(str(fatura["cliente_id"]))

    # Every fatura ALREADY `vencida` (from an earlier day's sweep) also keeps
    # its cliente inadimplente — the status must not clear itself just
    # because no NEW invoice crossed the line today.
    ja_vencidas = linhas_cross_org(
        db, "fatura", select="id,org_id,cliente_id",
        filtros=lambda q: q.eq("status", "vencida"),
        label="igig.fatura (inadimplência: já vencidas)",
    )
    for linha in ja_vencidas:
        vencidas_por_org.setdefault(str(linha["org_id"]), set()).add(str(linha["cliente_id"]))

    clientes = linhas_cross_org(
        db, "cliente",
        filtros=lambda q: q.in_("status", ["ativo", "inadimplente"]),
        label="igig.cliente (inadimplência: candidatos)",
    )
    for cliente in clientes:
        org_id = str(cliente["org_id"])
        cliente_id = str(cliente["id"])
        tem_vencida = cliente_id in vencidas_por_org.get(org_id, set())
        status_atual = cliente.get("status")
        if tem_vencida and status_atual != "inadimplente":
            repos.cliente.marcar_inadimplente(org_id, cliente_id)
            resumo["clientes_inadimplentes"] += 1
        elif not tem_vencida and status_atual == "inadimplente":
            repos.cliente.ativar(org_id, cliente_id)
            resumo["clientes_normalizados"] += 1

    logger.info("atualizar_inadimplencia: %s", resumo)
    return resumo


async def enviar_fatura(
    repos: Repositorios, org_id: str, fatura_id: str, *,
    sender_factory: EmailSenderFactory, settings: EmailSettings, agencia: str,
) -> tuple[dict, str]:
    """E-mail the fatura's PDF to the cliente. Returns ``(fatura_atualizada,
    message_id)`` — the "Enviar fatura" action (achado 12 (parcial), 2026-09
    audit: no status ever moved a fatura to `enviada`).

    Reuses the SAME SMTP-resolution seam `orcamento_email.enviar_orcamento`
    uses (`email_config.resolver_smtp` — 409 `smtp_nao_configurado` when
    nothing usable is configured). Unlike an orçamento — whose PDF a director
    may hand-edit before sending, so it is generated once and stored — a
    fatura's PDF is a pure, deterministic render of its own rows every time,
    so it is built fresh here rather than round-tripped through storage.
    """
    try:
        fatura = repos.fatura.buscar(org_id, fatura_id)
    except RecordNotFound:
        raise RegraViolada(404, "fatura_nao_encontrada", "Fatura não encontrada.")
    if fatura.get("status") in FATURA_FECHADA:
        raise RegraViolada(
            409, "fatura_fechada", f"Fatura {fatura['status']} não pode ser enviada.",
        )
    try:
        cliente = repos.cliente.buscar(org_id, str(fatura["cliente_id"]))
    except RecordNotFound:
        raise RegraViolada(404, "cliente_nao_encontrado", "Cliente não encontrado.")
    destinatario = cliente.get("email")
    if not destinatario:
        raise RegraViolada(
            422, "email_destinatario_ausente", "O cliente não tem e-mail cadastrado.",
        )

    config, origem = email_config.resolver_smtp(repos, org_id, settings)
    itens = repos.fatura_item.da_fatura(org_id, fatura_id)
    pdf = documentos_pdf.renderizar_fatura_pdf(fatura, itens, cliente=cliente, agencia=agencia)

    competencia = str(fatura.get("competencia") or "")
    nome_cliente = html.escape(str(cliente.get("nome") or ""))
    assunto = f"Fatura — {competencia}"
    email = OutgoingEmail(
        to=[str(destinatario)],
        cc=[],
        subject=assunto,
        html=(
            f"<p>Olá, {nome_cliente}!</p>"
            f"<p>Segue em anexo a fatura referente à competência {html.escape(competencia)}.</p>"
        ),
        text=f"Olá, {cliente.get('nome') or ''}! Segue em anexo a fatura referente à "
             f"competência {competencia}.",
        attachments=[Attachment(
            filename=f"fatura-{competencia}.pdf", content=pdf, mime_type="application/pdf",
        )],
    )
    try:
        enviado = await sender_factory(config).send(email)
    except EmailError as erro:
        logger.error("envio da fatura falhou org=%s fatura=%s: %s", org_id, fatura_id, erro)
        raise RegraViolada(502, "envio_falhou", f"Falha ao enviar o e-mail: {erro}") from erro

    atualizado = repos.fatura.marcar_enviada(org_id, fatura_id)
    logger.info(
        "fatura enviada org=%s fatura=%s smtp=%s message_id=%s",
        org_id, fatura_id, origem, enviado.message_id,
    )
    return atualizado, enviado.message_id
