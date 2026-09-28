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
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from noctusai_lib.integrations.persistence import PersistenceError, SupabaseRecordStore

from app.repositories import Repositorios
from app.services.bi_service import BIService

logger = logging.getLogger(__name__)

__all__ = [
    "Excedente",
    "LinhaDRE",
    "ResumoFinanceiro",
    "FinanceiroService",
    "proxima_competencia",
    "competencia_anterior",
    "limites_da_competencia",
    "cliente_bloqueado_no_portal",
    "atualizar_inadimplencia",
]

_COMPETENCIA = re.compile(r"^(\d{4})-(\d{2})$")


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
    def excedentes(self, org_id: str, competencia: str) -> list[Excedente]:
        """Delivered-vs-contracted for every active contract in a month.

        "Delivered" means a pauta whose `data_publicacao` falls in the month.
        Counting tarefas instead would double-count a piece that took several
        steps, and counting publicacoes would miss anything published manually.

        Counted PER CONTRATO, never blindly per cliente: `igig.pauta` has no
        `contrato_id` column today, so when a cliente has exactly ONE active
        packaged contract (the shape every worked example in the product
        guide assumes) attributing its delivered pautas to that contract is
        unambiguous. When a cliente has MORE THAN ONE, which contract a given
        piece counts against cannot be determined from the schema — the
        previous behaviour counted the SAME delivered total against EACH of
        the client's contracts (finding #10, 2026-09 audit), which is a
        double-bill waiting to happen. Rather than guess, that case is
        SKIPPED (logged, never silently charged) until `pauta` carries a real
        `contrato_id` — a Calendário Editorial change outside this slice.
        """
        inicio, fim = limites_da_competencia(competencia)
        entregues: dict[str, int] = {}
        for pauta in self._repos.pauta.no_periodo(org_id, inicio, fim):
            cid = str(pauta.get("cliente_id") or "")
            entregues[cid] = entregues.get(cid, 0) + 1

        clientes = {str(c["id"]): c for c in self._repos.cliente.listar(org_id)}
        contratos_com_pacote_por_cliente: dict[str, list[dict]] = {}
        for contrato in self._repos.contrato.ativos(org_id):
            if not int(contrato.get("posts_por_mes") or 0):
                continue  # no package ⇒ nothing to exceed
            cid = str(contrato.get("cliente_id") or "")
            contratos_com_pacote_por_cliente.setdefault(cid, []).append(contrato)

        saida: list[Excedente] = []
        for cliente_id, contratos in contratos_com_pacote_por_cliente.items():
            if len(contratos) > 1:
                logger.warning(
                    "excedentes: org=%s cliente=%s tem %d contratos ativos com "
                    "pacote — sem `pauta.contrato_id` não é possível atribuir "
                    "peças entregues a um único contrato; nenhum excedente "
                    "calculado para este cliente nesta competência.",
                    org_id, cliente_id, len(contratos),
                )
                continue
            contrato = contratos[0]
            pacote = int(contrato.get("posts_por_mes") or 0)
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
                # The article moves with the noun: "O custo real está
                # SUBESTIMADO" → "A margem está SUPERESTIMADA". Replacing only
                # the noun phrase left "o margem", which reads as a typo in a
                # warning whose whole job is to be taken seriously.
                a.replace("o custo real está SUBESTIMADO", "a margem está SUPERESTIMADA")
                 .replace("custo real está SUBESTIMADO", "margem está SUPERESTIMADA")
                for a in eficiencia.alertas
            ]

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
            except PersistenceError:
                # Another request closed this exact contrato+competência
                # first — the unique index caught the race. Not a 500: the
                # slot is filled either way, so this is "already existed".
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
    cross-org query), so the cross-org DISCOVERY step reads the raw client
    directly; every row-level write below still goes through `Repositorios`
    (built over the SAME client), scoped to that row's own `org_id`.
    """
    referencia = hoje or date.today()
    repos = Repositorios(SupabaseRecordStore(db))
    resumo = {"faturas_vencidas": 0, "clientes_inadimplentes": 0, "clientes_normalizados": 0}

    vencidas_por_org: dict[str, set[str]] = {}

    abertas = (
        db.table("fatura").select("*").not_.in_("status", ["paga", "cancelada", "vencida"])
        .execute().data or []
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
    ja_vencidas = db.table("fatura").select("org_id,cliente_id").eq("status", "vencida").execute().data or []
    for linha in ja_vencidas:
        vencidas_por_org.setdefault(str(linha["org_id"]), set()).add(str(linha["cliente_id"]))

    clientes = db.table("cliente").select("*").in_("status", ["ativo", "inadimplente"]).execute().data or []
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
