"""Automações v1 — stage-entry + SLA rules on both boards (roadmap R11, slice E2).

    ao_entrar_etapa   called after every successful mover-etapa (Comercial +
                      Esteira) and when a negócio is created (it enters the
                      funnel's entry stage). Runs the org's active
                      `entrada_etapa` rules for the card's CURRENT stage.
    varrer_sla        the 15-min job: every card sitting in a stage longer than
                      a `sla` rule's `sla_horas` gets an in-app
                      `sla_estourado` notification (+ the rule's own action).

ONE EXECUTION PER ENTRY — BY CONSTRUCTION
------------------------------------------
An execution is keyed on the `pipeline_movimentos` row that recorded the card's
entry into its current stage (migration 023). The engine CLAIMS the
(rule, card, entry) row before acting and the unique index refuses a second
claim, so a within-column reorder (no new entry row), a retried request, or a
move racing the SLA sweep never runs an action twice — and a card that leaves
and comes back IS a new entry and fires again.

FAILURES ARE RECORDED, NEVER SWALLOWED
--------------------------------------
Every action outcome lands in `automacao_execucao` (`sucesso` / `erro` with the
reason). The move itself is already committed when the engine runs, so an
automation failure never turns a successful drag into an error response — it
becomes an `erro` row the Automações log shows, plus a log line (WARNING for
an expected misconfiguration such as "SMTP não configurado", ERROR with the
traceback for anything unexpected). If even RECORDING fails, that is logged at
ERROR with the traceback; the move still stands.

Actions (`acao.tipo` → `params`):
    criar_checklist      {titulo, itens?: [str]}             Comercial only (the
                         negócio card hub's checklist service)
    definir_responsavel  {profissional_id}
    criar_tarefa         {titulo, prazo_dias?, responsavel_id?}  Esteira: a new
                         tarefa on the same pauta. Comercial: an item on the
                         negócio card's "Tarefas" checklist.
    notificar            {titulo?, mensagem?, usuario_ids?: [str]}
    enviar_email         {assunto, mensagem, para?}           seed `make_email_sender`
                         over slice B's `email_config.resolver_smtp` (org SMTP, logged platform fallback)
    enviar_whatsapp      {mensagem, para?}                    seed WAHA client over
                         the org's WAHA connection
Text fields accept `{nome}`, `{empresa}`, `{titulo}`, `{etapa}`, `{cliente}`.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.card_hub import services as card_hub_services
from noctusai_lib.integrations.email import OutgoingEmail
from noctusai_lib.integrations.persistence import get_record_store
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows, paged_rows
from noctusai_lib.integrations.whatsapp import get_whatsapp_client
from noctusai_lib.primitives.phone import phone_digits
from noctusai_lib.primitives.roles import ADMIN_ROLES

from app.pipelines import PIPELINE_COMERCIAL, PIPELINE_ESTEIRA
from app.services import quadro_comum as qc
from app.email_deps import get_email_sender_factory
from app.repositories import Repositorios
from app.services.canais_org import CanalNaoConfigurado, waha_da_org
from app.services.email_config import EmailSettings, resolver_smtp
from app.services.regras import RegraViolada
from app.services.notificacoes import notificar

logger = logging.getLogger(__name__)

__all__ = [
    "ACOES",
    "AcaoFalhou",
    "PortasAutomacao",
    "ao_entrar_etapa",
    "listar_execucoes",
    "varrer_sla",
]

PIPELINES = {"comercial": PIPELINE_COMERCIAL, "esteira": PIPELINE_ESTEIRA}
ACOES = (
    "criar_checklist",
    "definir_responsavel",
    "criar_tarefa",
    "notificar",
    "enviar_email",
    "enviar_whatsapp",
)
#: The negócio card-hub checklist `criar_tarefa` appends to on the funnel.
CHECKLIST_TAREFAS = "Tarefas"
#: Notification types (core `public.notifications.type`).
TIPO_NOTIFICACAO = "automacao"
TIPO_SLA = "sla_estourado"


class AcaoFalhou(Exception):
    """An action that cannot run for a reason the operator can fix (pt-BR,
    shown verbatim in the execuções log)."""


@dataclass
class PortasAutomacao:
    """Everything the engine touches — injected, never imported as globals.

    `db` is the client the pipeline tables are read/written through (the
    caller's RLS client on authenticated routes; the igig service-role client
    on the public webhooks and the SLA job). `admin_db` is the service-role
    client the negócio card hub writes through by construction
    (`app/card_hub.py`) — `None` on the Esteira move, which has no card hub.
    """

    db: Any
    admin_db: Optional[Any]
    core_db: Any
    cfg: Any
    #: `SmtpConfig -> EmailSender` — slice B's factory, which never hands back
    #: the seed Fake (a Fake would log an e-mail as sent that nobody received).
    email_sender: Callable[[Any], Any] = field(default_factory=get_email_sender_factory)
    whatsapp_client: Callable[..., Any] = get_whatsapp_client
    agora: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))


@dataclass
class _Contexto:
    pipeline: str
    gatilho: str
    card: dict
    etapa: dict
    lead: Optional[dict]
    cliente: Optional[dict]
    user_id: Optional[str]

    def rotulo(self) -> str:
        return str(self.card.get("titulo") or ("negócio" if self.pipeline == "comercial" else "tarefa"))

    def link(self) -> str:
        if self.pipeline == "comercial":
            return f"/comercial?negocio={self.card.get('id')}"
        return "/esteira"


# ── entry point: stage entry ─────────────────────────────────────────
async def ao_entrar_etapa(
    portas: PortasAutomacao,
    org_id: str,
    *,
    pipeline: str,
    card_id: str,
    user_id: Any = None,
) -> list[dict]:
    """Run the `entrada_etapa` rules of the card's current stage. Returns the
    execution rows written (empty when nothing applied). Never raises."""
    try:
        return await _ao_entrar_etapa(portas, org_id, pipeline, str(card_id), user_id)
    except Exception:  # noqa: BLE001 — the move is committed; see module docstring
        logger.exception(
            "automações: falha ao avaliar entrada org=%s pipeline=%s card=%s",
            org_id, pipeline, card_id,
        )
        return []


async def _ao_entrar_etapa(
    portas: PortasAutomacao, org_id: str, pipeline: str, card_id: str, user_id: Any
) -> list[dict]:
    cfg = PIPELINES[pipeline]
    card = _card(portas.db, cfg.card_table, org_id, card_id)
    if card is None:
        logger.warning("automações: card %s/%s não encontrado org=%s", pipeline, card_id, org_id)
        return []
    if pipeline == "comercial" and card.get("status") == "perdido":
        return []
    etapa_id = str(card.get("etapa_id") or "")
    regras = _regras(portas.db, org_id, pipeline=pipeline, gatilho="entrada_etapa", etapa_id=etapa_id)
    if not regras:
        return []
    entrada = _entrada_atual(portas.db, org_id, pipeline, card_id, etapa_id)
    if entrada is None:
        logger.info(
            "automações: card %s sem registro de entrada na etapa %s org=%s — nada disparado",
            card_id, etapa_id, org_id,
        )
        return []
    ctx = _contexto(portas, org_id, pipeline, "entrada_etapa", card, user_id)
    execucoes = []
    for regra in regras:
        execucao = await _executar_regra(portas, org_id, regra, ctx, str(entrada["id"]))
        if execucao is not None:
            execucoes.append(execucao)
    return execucoes


# ── entry point: SLA sweep ───────────────────────────────────────────
async def varrer_sla(portas: PortasAutomacao) -> dict:
    """Every org's active `sla` rules, every card past its SLA → one alert per
    (rule, card, entry). `portas.db` MUST be the service-role client: the
    sweep crosses orgs (every query below still filters `org_id`).

    Returns counts for the job log. One rule failing is logged and the sweep
    continues with the next — an org's broken rule must not starve another's.
    """
    regras = list(
        portas.db.table("automacao").select("*").eq("gatilho", "sla").eq("ativo", True)
        .execute().data or []
    )
    resumo = {"regras": len(regras), "estourados": 0, "execucoes": 0, "falhas_regra": 0}
    for regra in regras:
        try:
            estourados, execs = await _varrer_regra(portas, regra)
            resumo["estourados"] += estourados
            resumo["execucoes"] += execs
        except Exception:  # noqa: BLE001 — next rule still runs; see docstring
            resumo["falhas_regra"] += 1
            logger.exception("automações: varredura SLA falhou regra=%s org=%s",
                             regra.get("id"), regra.get("org_id"))
    logger.info("automações: varredura SLA %s", resumo)
    return resumo


async def _varrer_regra(portas: PortasAutomacao, regra: dict) -> tuple[int, int]:
    org_id = str(regra["org_id"])
    pipeline = str(regra["pipeline"])
    cfg = PIPELINES[pipeline]
    etapa_id = str(regra["etapa_id"])
    limite = timedelta(hours=int(regra.get("sla_horas") or 0))
    cards = paged_rows(
        portas.db, cfg.card_table, org_id,
        eq_filters={"etapa_id": etapa_id, **({"status": "aberto"} if pipeline == "comercial" else {})},
        select="*",
    )
    if not cards:
        return 0, 0
    entradas = _entradas_por_card(portas.db, org_id, pipeline, etapa_id, [str(c["id"]) for c in cards])
    agora = portas.agora()
    estourados = execs = 0
    for card in cards:
        entrada = entradas.get(str(card["id"]))
        desde = _quando(
            (entrada or {}).get("created_at") or card.get("stage_entered_at") or card.get("created_at")
        )
        if desde is None or agora - desde < limite:
            continue
        estourados += 1
        ctx = _contexto(portas, org_id, pipeline, "sla", card, None)
        execucao = await _executar_regra(
            portas, org_id, regra, ctx, str(entrada["id"]) if entrada else None
        )
        if execucao is not None:
            execs += 1
    return estourados, execs


# ── execution ────────────────────────────────────────────────────────
async def _executar_regra(
    portas: PortasAutomacao, org_id: str, regra: dict, ctx: _Contexto, movimento_id: Optional[str]
) -> Optional[dict]:
    """Claim → act → record. `None` when this (rule, card, entry) was already
    claimed (handled before, or being handled right now)."""
    execucao = _reivindicar(portas, org_id, regra, str(ctx.card["id"]), movimento_id)
    if execucao is None:
        return None
    acao = regra.get("acao") or {}
    tipo = acao.get("tipo")
    params = acao.get("params") or {}

    # The rule's own action FIRST (a `definir_responsavel` SLA rule must set
    # the owner before the alert picks its recipients), then — for an SLA
    # rule — the `sla_estourado` alert. An SLA rule whose action IS
    # `notificar` is just the alert, customised by its params. Each step is
    # attempted and recorded on its own: one failing never hides the other.
    passos: list[tuple[str, Callable[[], Awaitable[str]]]] = []
    if not (ctx.gatilho == "sla" and tipo == "notificar"):
        executor = _EXECUTORES.get(tipo)
        passos.append((str(tipo), (lambda: executor(portas, org_id, params, ctx)) if executor
                       else _falhar(f"Tipo de ação desconhecido: {tipo!r}.")))
    if ctx.gatilho == "sla":
        passos.append(("sla_estourado", lambda: _alertar_sla(
            portas, org_id, params if tipo == "notificar" else {}, ctx, regra)))

    partes, erros = [], []
    for nome, passo in passos:
        try:
            partes.append(await passo())
        except (AcaoFalhou, CanalNaoConfigurado) as exc:
            erros.append(str(exc))
            logger.warning("automação %s (%s) falhou org=%s card=%s: %s", regra.get("id"), nome,
                           org_id, ctx.card.get("id"), exc)
        except Exception as exc:  # noqa: BLE001 — recorded as `erro` below, traceback logged
            erros.append(f"Erro inesperado ({type(exc).__name__}): {exc}")
            logger.exception("automação %s (%s) falhou org=%s card=%s", regra.get("id"), nome,
                             org_id, ctx.card.get("id"))
    status = "erro" if erros else "sucesso"
    detalhe = " · ".join(erros + partes)
    return _finalizar(portas, org_id, execucao, status, detalhe)


def _falhar(mensagem: str) -> Callable[[], Awaitable[str]]:
    async def passo() -> str:
        raise AcaoFalhou(mensagem)

    return passo


def _reivindicar(
    portas: PortasAutomacao, org_id: str, regra: dict, card_id: str, movimento_id: Optional[str]
) -> Optional[dict]:
    existentes = (
        portas.db.table("automacao_execucao").select("id, movimento_id")
        .eq("org_id", org_id).eq("automacao_id", regra["id"]).eq("entidade_id", card_id)
        .execute().data or []
    )
    if any(str(e.get("movimento_id") or "") == str(movimento_id or "") for e in existentes):
        return None
    try:
        linhas = (
            portas.db.table("automacao_execucao").insert(
                {
                    "org_id": org_id,
                    "automacao_id": regra["id"],
                    "entidade_id": card_id,
                    "movimento_id": movimento_id,
                    "status": "executando",
                    "executado_em": portas.agora().isoformat(),
                }
            ).execute().data or []
        )
    except Exception as exc:  # noqa: BLE001 — only a unique violation means "already claimed"
        if _violacao_unica(exc):
            logger.info("automação %s já reivindicada card=%s entrada=%s", regra["id"], card_id,
                        movimento_id)
            return None
        raise
    if not linhas:
        raise RuntimeError("insert de automacao_execucao não retornou a linha")
    return linhas[0]


def _finalizar(portas: PortasAutomacao, org_id: str, execucao: dict, status: str, detalhe: str) -> dict:
    valores = {"status": status, "detalhe": (detalhe or "")[:2000], "executado_em": portas.agora().isoformat()}
    try:
        linhas = (
            portas.db.table("automacao_execucao").update(valores)
            .eq("id", execucao["id"]).eq("org_id", org_id).execute().data or []
        )
        return linhas[0] if linhas else {**execucao, **valores}
    except Exception:  # noqa: BLE001 — the action already ran; record the gap loudly
        logger.exception(
            "automações: ação executada mas o registro falhou execucao=%s status=%s detalhe=%s",
            execucao.get("id"), status, detalhe,
        )
        return {**execucao, **valores}


def _violacao_unica(exc: Exception) -> bool:
    code = str(getattr(exc, "code", "") or "")
    return code == "23505" or "duplicate key" in str(exc).lower()


# ── reads ────────────────────────────────────────────────────────────
def _card(db: Any, tabela: str, org_id: str, card_id: str) -> Optional[dict]:
    linhas = db.table(tabela).select("*").eq("id", card_id).eq("org_id", org_id).execute().data or []
    return linhas[0] if linhas else None


def _regras(db: Any, org_id: str, *, pipeline: str, gatilho: str, etapa_id: str) -> list[dict]:
    return list(
        db.table("automacao").select("*")
        .eq("org_id", org_id).eq("pipeline", pipeline).eq("etapa_id", etapa_id)
        .eq("gatilho", gatilho).eq("ativo", True)
        .execute().data or []
    )


def _mais_recente(linhas: list[dict]) -> Optional[dict]:
    # Stable sort + last: equal timestamps keep insertion order, so the last
    # row written wins — the database's own order when created_at ties.
    return sorted(linhas, key=lambda r: str(r.get("created_at") or ""))[-1] if linhas else None


def _entrada_atual(db: Any, org_id: str, pipeline: str, card_id: str, etapa_id: str) -> Optional[dict]:
    """The history row of the card's entry into its CURRENT stage, or `None`.

    The card's latest transition must point at `etapa_id`; if it does not, the
    history and the card disagree (a legacy card, or a write in flight) and no
    entry can be claimed.
    """
    linhas = (
        db.table("pipeline_movimentos").select("id, para_etapa_id, created_at")
        .eq("org_id", org_id).eq("pipeline", pipeline).eq("entidade_id", card_id)
        .order("created_at", desc=True).limit(50)
        .execute().data or []
    )
    ultima = _mais_recente(linhas)
    if ultima is None or str(ultima.get("para_etapa_id")) != etapa_id:
        return None
    return ultima


def _entradas_por_card(
    db: Any, org_id: str, pipeline: str, etapa_id: str, card_ids: list[str]
) -> dict[str, dict]:
    linhas = in_batched_rows(
        db, "pipeline_movimentos", org_id, "entidade_id", card_ids,
        select="id, entidade_id, para_etapa_id, pipeline, created_at",
    )
    por_card: dict[str, list[dict]] = {}
    for linha in linhas:
        if linha.get("pipeline") == pipeline:
            por_card.setdefault(str(linha["entidade_id"]), []).append(linha)
    saida = {}
    for card_id, historico in por_card.items():
        ultima = _mais_recente(historico)
        if ultima is not None and str(ultima.get("para_etapa_id")) == etapa_id:
            saida[card_id] = ultima
    return saida


def _quando(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("automações: data ilegível %r", valor)
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _talvez(db: Any, tabela: str, org_id: str, registro_id: Any) -> Optional[dict]:
    if not registro_id:
        return None
    linhas = (
        db.table(tabela).select("*").eq("id", str(registro_id)).eq("org_id", org_id).execute().data
        or []
    )
    return linhas[0] if linhas else None


def _contexto(
    portas: PortasAutomacao, org_id: str, pipeline: str, gatilho: str, card: dict, user_id: Any
) -> _Contexto:
    etapa = _talvez(portas.db, "pipeline_stages", org_id, card.get("etapa_id")) or {}
    lead = _talvez(portas.db, "lead", org_id, card.get("lead_id")) if pipeline == "comercial" else None
    cliente = _talvez(portas.db, "cliente", org_id, card.get("cliente_id"))
    return _Contexto(
        pipeline=pipeline, gatilho=gatilho, card=card, etapa=etapa, lead=lead, cliente=cliente,
        user_id=str(user_id) if user_id else None,
    )


# ── helpers for executors ────────────────────────────────────────────
class _Vars(dict):
    def __missing__(self, chave: str) -> str:
        return "{" + chave + "}"


def _render(texto: Optional[str], ctx: _Contexto) -> str:
    if not texto:
        return ""
    pessoa = ctx.lead or ctx.cliente or {}
    variaveis = _Vars(
        nome=pessoa.get("nome") or "",
        empresa=(ctx.lead or {}).get("empresa") or (ctx.cliente or {}).get("nome") or "",
        titulo=ctx.card.get("titulo") or "",
        etapa=ctx.etapa.get("label") or "",
        cliente=(ctx.cliente or {}).get("nome") or "",
    )
    try:
        return str(texto).format_map(variaveis)
    except (ValueError, IndexError) as exc:
        # A stray `{` in free text is the operator's prose, not a template.
        logger.debug("automações: texto não é template (%s) — enviado como está", exc)
        return str(texto)


def _usuario_do_profissional(db: Any, org_id: str, profissional_id: Any) -> Optional[str]:
    prof = _talvez(db, "profissional", org_id, profissional_id)
    return str(prof["usuario_id"]) if prof and prof.get("usuario_id") else None


def _admins_da_org(core_db: Any, org_id: str) -> list[str]:
    linhas = (
        core_db.table("noctus_users").select("id")
        .eq("org_id", org_id).in_("org_role", list(ADMIN_ROLES)).execute().data or []
    )
    return [str(r["id"]) for r in linhas if r.get("id")]


def _destinatarios(portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto) -> list[str]:
    ids = [str(u) for u in (params.get("usuario_ids") or []) if u]
    responsavel = _usuario_do_profissional(portas.db, org_id, ctx.card.get("responsavel_id"))
    if responsavel:
        ids.append(responsavel)
    if not ids and ctx.user_id:
        ids.append(ctx.user_id)
    if not ids and ctx.gatilho == "sla":
        # Nobody owns the card and nobody triggered it: the org's admins are
        # the last line — an SLA breach nobody hears about is the silent case.
        ids.extend(_admins_da_org(portas.core_db, org_id))
    return ids


def _notificar(
    portas: PortasAutomacao, org_id: str, ctx: _Contexto, *, tipo: str, titulo: str,
    mensagem: str, destinatarios: list[str], regra_id: Any = None,
) -> str:
    enviados = notificar(
        portas.core_db, org_id=org_id, user_ids=destinatarios, tipo=tipo, titulo=titulo,
        mensagem=mensagem,
        metadata={
            "pipeline": ctx.pipeline, "card_id": str(ctx.card.get("id")),
            "etapa_id": str(ctx.card.get("etapa_id")), "automacao_id": str(regra_id or ""),
            "link": ctx.link(),
        },
    )
    if not enviados:
        raise AcaoFalhou("Nenhum destinatário para a notificação (sem responsável nem usuários).")
    return f"Notificação enviada a {enviados} usuário(s)"


async def _alertar_sla(
    portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto, regra: dict
) -> str:
    horas = regra.get("sla_horas")
    titulo = _render(params.get("titulo"), ctx) or f"SLA estourado: {ctx.rotulo()}"
    mensagem = _render(params.get("mensagem"), ctx) or (
        f"“{ctx.rotulo()}” está em {ctx.etapa.get('label') or 'uma etapa'} há mais de {horas}h."
    )
    return _notificar(
        portas, org_id, ctx, tipo=TIPO_SLA, titulo=titulo, mensagem=mensagem,
        destinatarios=_destinatarios(portas, org_id, params, ctx), regra_id=regra.get("id"),
    )


# ── executors ────────────────────────────────────────────────────────
def _exigir_card_hub(portas: PortasAutomacao) -> None:
    if portas.admin_db is None:
        # A wiring fault, not an operator one: the negócio routes always pass
        # the card-hub client. Raised loudly so it can never pass as success.
        raise RuntimeError("card hub sem cliente service-role nestas portas de automação")


async def _criar_checklist(portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto) -> str:
    if ctx.pipeline != "comercial":
        raise AcaoFalhou("Checklists automáticos existem só no funil comercial (card do negócio).")
    from app.card_hub import CARD_HUB_NEGOCIO

    _exigir_card_hub(portas)
    card_id = str(ctx.card["id"])
    checklist = card_hub_services.create_checklist(
        CARD_HUB_NEGOCIO, portas.admin_db, org_id, card_id, titulo=_render(params.get("titulo"), ctx)
    )
    itens = [i for i in (params.get("itens") or []) if str(i).strip()]
    for texto in itens:
        card_hub_services.create_checklist_item(
            CARD_HUB_NEGOCIO, portas.admin_db, org_id, card_id, checklist["id"],
            texto=_render(texto, ctx),
        )
    return f"Checklist “{checklist.get('titulo')}” criado com {len(itens)} item(ns)"


async def _definir_responsavel(portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto) -> str:
    prof = _talvez(portas.db, "profissional", org_id, params.get("profissional_id"))
    if prof is None:
        raise AcaoFalhou("O profissional configurado nesta automação não existe mais.")
    tabela = PIPELINES[ctx.pipeline].card_table
    portas.db.table(tabela).update({"responsavel_id": prof["id"]}).eq("id", ctx.card["id"]).eq(
        "org_id", org_id
    ).execute()
    ctx.card["responsavel_id"] = prof["id"]
    return f"Responsável definido: {prof.get('nome') or prof['id']}"


async def _criar_tarefa(portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto) -> str:
    titulo = _render(params.get("titulo"), ctx)
    prazo_dias = params.get("prazo_dias")
    prazo = (date.today() + timedelta(days=int(prazo_dias))) if prazo_dias is not None else None
    if ctx.pipeline == "esteira":
        from app.services import esteira_quadro

        if not ctx.card.get("pauta_id"):
            raise AcaoFalhou("A tarefa de origem não tem pauta — não há onde criar a nova tarefa.")
        tarefa = esteira_quadro.criar_tarefa(
            portas.db, org_id,
            pauta_id=str(ctx.card["pauta_id"]),
            titulo=titulo,
            responsavel_id=params.get("responsavel_id") or ctx.card.get("responsavel_id"),
            prazo=prazo.isoformat() if prazo else None,
            user_id=ctx.user_id,
        )
        return f"Tarefa “{titulo}” criada na esteira ({tarefa.get('id')})"

    from app.card_hub import CARD_HUB_NEGOCIO

    _exigir_card_hub(portas)
    card_id = str(ctx.card["id"])
    existentes = card_hub_services.list_checklists(CARD_HUB_NEGOCIO, portas.admin_db, org_id, card_id)
    checklist = next(
        (c for c in existentes["items"] if c.get("titulo") == CHECKLIST_TAREFAS), None
    ) or card_hub_services.create_checklist(
        CARD_HUB_NEGOCIO, portas.admin_db, org_id, card_id, titulo=CHECKLIST_TAREFAS
    )
    texto = f"{titulo} (até {prazo.strftime('%d/%m/%Y')})" if prazo else titulo
    card_hub_services.create_checklist_item(
        CARD_HUB_NEGOCIO, portas.admin_db, org_id, card_id, checklist["id"], texto=texto
    )
    return f"Tarefa “{texto}” adicionada ao checklist {CHECKLIST_TAREFAS}"


async def _notificar_acao(portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto) -> str:
    titulo = _render(params.get("titulo"), ctx) or f"{ctx.rotulo()} entrou em {ctx.etapa.get('label') or 'nova etapa'}"
    mensagem = _render(params.get("mensagem"), ctx) or titulo
    return _notificar(
        portas, org_id, ctx, tipo=TIPO_NOTIFICACAO, titulo=titulo, mensagem=mensagem,
        destinatarios=_destinatarios(portas, org_id, params, ctx),
    )


async def _enviar_email(portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto) -> str:
    pessoa = ctx.lead if ctx.pipeline == "comercial" else ctx.cliente
    para = params.get("para") or (pessoa or {}).get("email")
    if not para:
        raise AcaoFalhou("Sem destinatário: o contato não tem e-mail e a automação não define `para`.")
    # Slice B's resolver is THE SMTP reader (org account → logged platform
    # fallback → refusal); it reads through the repositories, so it gets the
    # same client the engine runs on.
    try:
        config, origem = resolver_smtp(
            Repositorios(get_record_store(supabase_client=portas.db)), org_id,
            EmailSettings.de(portas.cfg, None),
        )
    except RegraViolada as exc:
        raise AcaoFalhou(exc.mensagem) from exc
    texto = _render(params.get("mensagem"), ctx)
    enviado = await portas.email_sender(config).send(
        OutgoingEmail(
            to=[str(para)],
            subject=_render(params.get("assunto"), ctx),
            text=texto,
            html="<p>" + html.escape(texto).replace("\n", "<br>") + "</p>",
        )
    )
    sufixo = " (SMTP da plataforma)" if origem == "plataforma" else ""
    return f"E-mail enviado para {para}{sufixo} — {enviado.message_id}"


async def _enviar_whatsapp(portas: PortasAutomacao, org_id: str, params: dict, ctx: _Contexto) -> str:
    pessoa = (ctx.lead if ctx.pipeline == "comercial" else ctx.cliente) or {}
    if params.get("para"):
        digitos = phone_digits(params["para"])
        chat_id = f"{digitos}@c.us" if digitos else None
    elif pessoa.get("waha_chat_id"):
        chat_id = str(pessoa["waha_chat_id"])
    else:
        digitos = phone_digits(pessoa.get("telefone"))
        chat_id = f"{digitos}@c.us" if digitos else None
    if not chat_id:
        raise AcaoFalhou("Sem destinatário: o contato não tem telefone válido e a automação não define `para`.")
    waha = waha_da_org(portas.db, org_id, portas.cfg)
    cliente = portas.whatsapp_client(base_url=waha.base_url, api_key=waha.api_key, session=waha.session)
    await cliente.send_text(chat_id, _render(params.get("mensagem"), ctx))
    return f"WhatsApp enviado para {chat_id}"


_EXECUTORES: dict[str, Callable[[PortasAutomacao, str, dict, _Contexto], Awaitable[str]]] = {
    "criar_checklist": _criar_checklist,
    "definir_responsavel": _definir_responsavel,
    "criar_tarefa": _criar_tarefa,
    "notificar": _notificar_acao,
    "enviar_email": _enviar_email,
    "enviar_whatsapp": _enviar_whatsapp,
}
assert set(_EXECUTORES) == set(ACOES), "every declared action needs an executor"


# ── read side (the execuções log) ────────────────────────────────────
def listar_execucoes(db: Any, org_id: str, *, limit: int = 50, automacao_id: Optional[str] = None) -> list[dict]:
    consulta = db.table("automacao_execucao").select("*").eq("org_id", org_id)
    if automacao_id:
        consulta = consulta.eq("automacao_id", automacao_id)
    linhas = list(consulta.order("executado_em", desc=True).limit(limit).execute().data or [])
    linhas.sort(key=lambda r: str(r.get("executado_em") or ""), reverse=True)
    regras = qc.por_ids(db, "automacao", org_id, (r.get("automacao_id") for r in linhas),
                        select="id, pipeline, etapa_id, gatilho, acao")
    return [
        {
            **linha,
            "automacao": (
                {
                    "id": regra["id"], "pipeline": regra.get("pipeline"),
                    "stage_id": regra.get("etapa_id"), "gatilho": regra.get("gatilho"),
                    "tipo": (regra.get("acao") or {}).get("tipo"),
                }
                if (regra := regras.get(str(linha.get("automacao_id")))) else None
            ),
        }
        for linha in linhas
    ]
