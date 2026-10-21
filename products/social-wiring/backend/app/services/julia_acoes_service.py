"""Apply the actions agents returned in a turn (contract A4 / julia-v2 section 8.1).

agents never writes SW tables: the model's tools only RECORD intent in agents and the turn response carries the
operational actions back; SW applies them HERE, after the reply was sent, idempotently:

  for each action in `seq` order
    1. insert into `julia_acoes_aplicadas` ON CONFLICT (org_id, lote_hash, seq) DO NOTHING
       -> nothing inserted means "this batch already applied it" -> skip (replay-safe);
    2. dispatch to the HANDLER REGISTRY by `tipo`;
    3. an UNKNOWN handler -> event `acao_sem_handler` + log;
       a handler that raises -> event `acao_falhou` + log. NEVER an exception that
       propagates: applying actions runs after the reply and must not undo or hide it.

Handler registry (waves append ONE line each, nobody edits `aplicar`):

    HANDLERS: dict[str, Handler]
    Handler = Callable[[AcaoCtx, dict], dict | None | Awaitable[dict | None]]

  here    encerrar · intencao_visita (records the intent and STOPS: visit scheduling is out of Julia v2, D11)
  envio   lead_pronto (the computed stage reached the CRM send, Q6) · captacao
  other   consentimento_credito · (visitas module: pedido_visita, not offered to Julia v2)

`salvar_slots` / `definir_operacao` / `qualificar_lead` are RETIRED (julia-v2 D4): the qualification state is agents',
SW mirrors it from the turn response (`julia_espelho_service`) and never writes `julia_contatos.slots/operacao` from a
model action. An agents build that still sent one gets an `acao_sem_handler` event, never a silent write.

`handler(ctx, payload)` gets the RAW payload; the ledger stores a sanitised copy. The returned dict (or None) is stored
as `resultado`. `registrar_handler(tipo, fn)` binds one at runtime (tests / late binding).

Closing an episode (`fechar_interacao`) asks agents for the narrative summary (`AgentsClient.resumo`) and stores it on the
`julia_interacoes` row; a failed `/resumo` still closes the episode (event `resumo_falhou`) -- the summary is enrichment,
the close is the state change.
"""
from __future__ import annotations

import hashlib
import inspect
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Sequence, Union, Mapping
from uuid import UUID

from app.clients.agents import AgentsClient, AgentsClientError, MOTIVO_ENCERRAR_PEDIU_PARAR, ResumoRequest, TurnResult
from app.services import julia_contatos_service as contatos
from app.services import julia_eventos_service as eventos
from app.services import julia_notificacoes_service as notificacoes
from app.services import julia_slots_sensiveis as sensiveis

logger = logging.getLogger(__name__)

PREFERENCIA_HORARIO_MAX = 120
CODIGO_IMOVEL_MAX = 40
MOTIVOS_ENCERRAR = frozenset({"lead_encerrou", "sem_interesse", "invalido", "outro", MOTIVO_ENCERRAR_PEDIU_PARAR})


@dataclass
class AcaoCtx:
    """Everything a handler may need; `contato` / `interacao` are re-read before EACH action."""

    client: Any  # schema-scoped service-role client
    org_id: UUID | str
    contato: dict[str, Any]
    interacao: Optional[dict[str, Any]]
    lote_hash: str
    seq: int
    tipo: str
    conversation_id: Optional[str] = None
    agents_client: Optional[AgentsClient] = None
    core_client: Any = None
    connection_id: Optional[UUID | str] = None
    chat_id: Optional[str] = None


HandlerResult = Optional[dict[str, Any]]
Handler = Callable[[AcaoCtx, dict[str, Any]], Union[HandlerResult, Awaitable[HandlerResult]]]


def lote_hash_de(conversation_id: str, provider_message_ids: Sequence[str]) -> str:
    """The idempotency key of one batch: agents replays the SAME actions for the same
    `provider_message_id`s, so the same batch must hash to the same key."""
    raw = f"{conversation_id}|{'|'.join(provider_message_ids)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sanitizar_payload(payload: dict[str, Any], org_id: Optional[UUID | str] = None) -> dict[str, Any]:
    """The ledger copy: a CPF is stored as hash + last 3 digits only (contract 17, wave 5); the
    sensitive slots of a `salvar_slots` batch (cpf / renda, wave 2) are protected the same way."""
    out = dict(payload)
    slots = out.get("slots")
    if isinstance(slots, dict):
        out["slots"] = {
            k: (sensiveis.proteger(str(k), v, str(org_id or "")) or "[protegido]")
            if str(k) in sensiveis.SENSIVEIS and isinstance(v, (str, int, float)) and not isinstance(v, bool) else v
            for k, v in slots.items()
        }
    cpf = out.pop("cpf", None)
    if cpf:
        digitos = re.sub(r"\D", "", str(cpf))
        out["cpf_hash"] = hashlib.sha256(digitos.encode("utf-8")).hexdigest()
        out["cpf_final"] = digitos[-3:]
    return out


# ── episode close (agents summarises) ───────────────────────────────────────
def _dt(value: Any) -> Optional[datetime]:
    return contatos._ts(value)  # noqa: SLF001 - same-package helper, one parser


async def fechar_interacao(
    client: Any,
    *,
    org_id: UUID | str,
    contato: dict[str, Any],
    interacao: dict[str, Any],
    agents_client: Optional[AgentsClient],
    conversation_id: Optional[str],
    agora: Optional[datetime] = None,
    origem: str = "silencio",
) -> dict[str, Any]:
    """Close an open episode: ask agents for the narrative `/resumo` (when there is a thread to summarise and a
    client), then stamp `encerrada_at` + summary/slots/desfecho/custo. The slots are the MIRROR of agents' computed
    qualification already on the contato (never what the summary says); the desfecho is display-only."""
    if interacao.get("encerrada_at"):
        return interacao
    agora = agora or datetime.now(timezone.utc)
    patch: dict[str, Any] = {"encerrada_at": agora.isoformat(), "slots": dict(contato.get("slots") or {})}
    if agents_client is None or not conversation_id:
        logger.info("julia: closing interacao=%s without a summary (no agents client / thread)", interacao["id"])
    else:
        try:
            res = await agents_client.resumo(conversation_id, ResumoRequest(desde=_dt(interacao.get("iniciada_at"))))
        except AgentsClientError as exc:
            logger.error("julia: /resumo failed (%s) interacao=%s -- closing without a summary", type(exc).__name__, interacao["id"])
            eventos.emitir(client, org_id, "resumo_falhou", contato["id"],
                           {"interacao_id": str(interacao["id"]), "erro": type(exc).__name__, "codigo": exc.code})
        else:
            patch.update(resumo=res.resumo, intencoes=list(res.intencoes), desfecho=res.desfecho, custo_usd=res.custo_usd)
            if contato.get("operacao"):
                patch["operacao"] = contato["operacao"]
    # `encerrada_at IS NULL` in the WHERE: a concurrent close wins, ours is a no-op.
    client.table(contatos.T_INTERACOES).update(patch).eq("id", str(interacao["id"])).is_("encerrada_at", "null").execute()
    if patch.get("intencoes"):
        notificacoes.avisar_cobranca(client, org_id, contato, interacao, patch["intencoes"])
    fechada = {**interacao, **patch}
    for hook in tuple(POS_FECHAR):
        try:
            out = hook(client, org_id, contato, fechada, origem)
            if inspect.isawaitable(out):
                await out
        except Exception as exc:
            # a policy hook (wave 13: the Google review ask) must never undo the close
            logger.error("julia: pos-fechar hook %s failed (org=%s) (%s)", getattr(hook, "__name__", "?"), org_id, type(exc).__name__)
    return fechada


# ── built-in handlers ───────────────────────────────────────────────────────
async def _h_encerrar(ctx: AcaoCtx, payload: dict[str, Any]) -> HandlerResult:
    # The lead asked to stop: agents ALREADY recorded the lead-level opt-out (who/why/notification are its), so SW
    # never calls opt-out again; it stops every SW-side follow-up of the lead and leaves a timeline record.
    pediu_parar = payload.get("lead_opt_out") is True or payload.get("motivo") == MOTIVO_ENCERRAR_PEDIU_PARAR
    motivo = MOTIVO_ENCERRAR_PEDIU_PARAR if pediu_parar else (
        payload.get("motivo") if payload.get("motivo") in MOTIVOS_ENCERRAR else "outro")
    agora = datetime.now(timezone.utc)
    # gen + 1 first: every job queued for this contato is now stale (contract 0.2).
    contatos.bump_gen(ctx.client, ctx.contato["id"], encerrado_at=agora.isoformat())
    if pediu_parar:
        logger.info("julia: lead asked to stop (agents recorded the opt-out) org=%s contato=%s -- follow-ups stopped", ctx.org_id, ctx.contato["id"])
        eventos.emitir(ctx.client, ctx.org_id, "lead_opt_out", ctx.contato["id"],
                       {"origem": "agente", "motivo": MOTIVO_ENCERRAR_PEDIU_PARAR,
                        "interacao_id": str(ctx.interacao["id"]) if ctx.interacao else None})
    fechada = None
    if ctx.interacao is not None:
        fechada = await fechar_interacao(
            ctx.client, org_id=ctx.org_id, contato=ctx.contato, interacao=ctx.interacao,
            agents_client=ctx.agents_client, conversation_id=ctx.conversation_id, agora=agora,
            origem="encerrar",
        )
    for hook in tuple(POS_ENCERRAR):
        try:
            hook(ctx, motivo)
        except Exception as exc:
            # a policy hook (wave 3: WhatsApp invalido -> send to the SW) must never undo the close
            logger.error("julia: pos-encerrar hook %s failed (org=%s) (%s)", getattr(hook, "__name__", "?"), ctx.org_id, type(exc).__name__)
    return {"motivo": motivo, "interacao_id": str(ctx.interacao["id"]) if ctx.interacao else None,
            "desfecho": (fechada or {}).get("desfecho")}


#: Hooks run after ANY episode close (`fechar_interacao`: the `encerrar` action AND the 24 h-silence close at the
#: next inbound): `hook(client, org_id, contato, interacao_fechada, origem)` (`origem` = `encerrar` | `silencio`), sync or async. Wave 13 binds the Google
#: review ask here (`registrar_pos_fechar`); a failing hook is logged and never undoes the close.
POS_FECHAR: list[Callable[..., Any]] = []


def registrar_pos_fechar(fn: Callable[..., Any]) -> None:
    """Idempotent: binding the same function twice keeps one entry."""
    if fn not in POS_FECHAR:
        POS_FECHAR.append(fn)


#: Hooks run after an `encerrar` closed the episode: `hook(ctx, motivo)`. Wave 3 binds the
#: "WhatsApp invalido" policy here (`registrar_pos_encerrar`); the list is the registry, nobody edits `_h_encerrar`.
POS_ENCERRAR: list[Callable[[AcaoCtx, str], Any]] = []


def registrar_pos_encerrar(fn: Callable[[AcaoCtx, str], Any]) -> None:
    """Idempotent: binding the same function twice keeps one entry."""
    if fn not in POS_ENCERRAR:
        POS_ENCERRAR.append(fn)


#: Hooks run after a handler of action `tipo` SUCCEEDED: `hook(ctx, payload, resultado)` (sync or async). Wave 13
#: binds the credit-analysis trigger onto `pedido_visita` here (`registrar_pos_acao`) -- composing the wave-5
#: handler, never forking it. A failing hook is logged and never undoes the action.
POS_ACAO: dict[str, list[Callable[..., Any]]] = {}


def registrar_pos_acao(tipo: str, fn: Callable[..., Any]) -> None:
    """Idempotent: binding the same function twice keeps one entry."""
    hooks = POS_ACAO.setdefault(tipo, [])
    if fn not in hooks:
        hooks.append(fn)


def _h_intencao_visita(ctx: AcaoCtx, payload: dict[str, Any]) -> HandlerResult:
    """The lead wants to visit a listing: record the INTENT and stop (julia-v2 D11 -- Julia schedules nothing; the
    Visitas module stays as it is and is not reachable from her). The event is what the team sees."""
    codigo = str(payload.get("codigo") or "").strip()[:CODIGO_IMOVEL_MAX]
    if not codigo:
        return {"erro": "codigo_invalido"}
    preferencia = str(payload.get("preferencia_horario") or "").strip()[:PREFERENCIA_HORARIO_MAX] or None
    eventos.emitir(ctx.client, ctx.org_id, "intencao_visita", ctx.contato["id"],
                   {"codigo": codigo, "preferencia_horario": preferencia})
    return {"codigo": codigo, "registrada": True}


#: THE registry. Waves append `"<tipo>": <fn>` (or call `registrar_handler`).
HANDLERS: dict[str, Handler] = {
    "encerrar": _h_encerrar,
    "intencao_visita": _h_intencao_visita,
}


def registrar_handler(tipo: str, fn: Handler, *, registro: Optional[dict[str, Handler]] = None) -> None:
    """Register `fn` for action `tipo` in THE module registry, or in `registro` when given
    (an isolated copy, e.g. `dict(HANDLERS)`, handed to `aplicar(..., handlers=...)`)."""
    (HANDLERS if registro is None else registro)[tipo] = fn


# ── apply ───────────────────────────────────────────────────────────────────
def _ledger(client: Any) -> Any:
    return client.table(contatos.T_ACOES)


def _atualizar_resultado(client: Any, org_id: Any, lote_hash: str, seq: int, resultado: Optional[dict[str, Any]]) -> None:
    try:
        _ledger(client).update({"resultado": resultado}).eq("org_id", str(org_id)).eq("lote_hash", lote_hash).eq("seq", seq).execute()
    except Exception as exc:
        logger.error("julia: could not store the result of action seq=%s lote=%s (%s)", seq, lote_hash[:12], type(exc).__name__)


async def aplicar(
    client: Any,
    *,
    org_id: UUID | str,
    contato: dict[str, Any],
    result: TurnResult,
    lote_hash: str,
    conversation_id: Optional[str] = None,
    agents_client: Optional[AgentsClient] = None,
    core_client: Any = None,
    connection_id: Optional[UUID | str] = None,
    chat_id: Optional[str] = None,
    handlers: Optional[Mapping[str, Handler]] = None,
) -> list[dict[str, Any]]:
    """`handlers=None` uses THE registry (`HANDLERS`). Apply `result.julia_actions` in `seq` order; returns one summary per action
    `{seq, tipo, estado}` with estado in `aplicada | repetida | sem_handler | falhou`. Never raises."""
    resumo: list[dict[str, Any]] = []
    conversation_id = conversation_id or result.conversation_id
    for acao in result.julia_actions:
        try:
            resumo.append(await _aplicar_uma(
                client, org_id=org_id, contato_id=contato["id"], acao=acao, lote_hash=lote_hash,
                conversation_id=conversation_id, agents_client=agents_client, core_client=core_client,
                connection_id=connection_id, chat_id=chat_id,
                handlers=HANDLERS if handlers is None else handlers,
            ))
        except Exception as exc:
            # The ledger insert itself failed (DB down): the reply is already sent, so report, don't raise.
            logger.error("julia: action %s seq=%s could not be applied (org=%s) (%s)", acao.type, acao.seq, org_id, type(exc).__name__)
            resumo.append({"seq": acao.seq, "tipo": acao.type, "estado": "falhou"})
    return resumo


async def _aplicar_uma(
    client: Any, *, org_id: UUID | str, contato_id: Any, acao: Any, lote_hash: str, conversation_id: Optional[str],
    agents_client: Optional[AgentsClient], core_client: Any,
    connection_id: Optional[UUID | str], chat_id: Optional[str], handlers: Mapping[str, Handler],
) -> dict[str, Any]:
    inserted = _ledger(client).upsert(
        {
            "org_id": str(org_id), "contato_id": str(contato_id), "conversation_id": conversation_id,
            "lote_hash": lote_hash, "seq": acao.seq, "tipo": acao.type, "payload": sanitizar_payload(acao.payload, org_id),
        },
        on_conflict="org_id,lote_hash,seq", ignore_duplicates=True,
    ).execute().data or []
    if not inserted:
        logger.info("julia: action %s seq=%s of lote %s already applied -- skipped", acao.type, acao.seq, lote_hash[:12])
        return {"seq": acao.seq, "tipo": acao.type, "estado": "repetida"}

    handler = handlers.get(acao.type)
    if handler is None:
        logger.warning("julia: no handler for action %r (its wave is not built) org=%s", acao.type, org_id)
        eventos.emitir(client, org_id, "acao_sem_handler", contato_id, {"tipo": acao.type, "seq": acao.seq})
        _atualizar_resultado(client, org_id, lote_hash, acao.seq, {"sem_handler": True})
        return {"seq": acao.seq, "tipo": acao.type, "estado": "sem_handler"}

    # Fresh state per action: an earlier handler of the same batch may have changed it.
    cont = (client.table(contatos.T_CONTATOS).select("*").eq("id", str(contato_id)).limit(1).execute().data or [None])[0]
    if cont is None:
        raise LookupError(f"julia contato {contato_id} vanished mid-batch")
    ctx = AcaoCtx(
        client=client, org_id=org_id, contato=cont, interacao=contatos.interacao_aberta(client, contato_id),
        lote_hash=lote_hash, seq=acao.seq, tipo=acao.type, conversation_id=conversation_id,
        agents_client=agents_client, core_client=core_client,
        connection_id=connection_id, chat_id=chat_id,
    )
    try:
        out = handler(ctx, acao.payload)
        if inspect.isawaitable(out):
            out = await out
    except Exception as exc:
        logger.error("julia: handler for %s seq=%s failed (org=%s) (%s)", acao.type, acao.seq, org_id, type(exc).__name__)
        eventos.emitir(client, org_id, "acao_falhou", contato_id, {"tipo": acao.type, "seq": acao.seq, "erro": type(exc).__name__})
        _atualizar_resultado(client, org_id, lote_hash, acao.seq, {"erro": type(exc).__name__})
        return {"seq": acao.seq, "tipo": acao.type, "estado": "falhou"}
    for hook in tuple(POS_ACAO.get(acao.type, ())):
        try:
            res = hook(ctx, acao.payload, out)
            if inspect.isawaitable(res):
                await res
        except Exception as exc:
            logger.error("julia: pos-acao hook %s for %s failed (org=%s) (%s)", getattr(hook, "__name__", "?"), acao.type, org_id, type(exc).__name__)
    _atualizar_resultado(client, org_id, lote_hash, acao.seq, out or {})
    return {"seq": acao.seq, "tipo": acao.type, "estado": "aplicada"}


__all__ = [
    "AcaoCtx", "HANDLERS", "Handler", "MOTIVOS_ENCERRAR", "OPERACOES", "aplicar", "fechar_interacao",
    "POS_ACAO", "POS_ENCERRAR", "POS_FECHAR", "lote_hash_de", "registrar_handler", "registrar_pos_acao", "registrar_pos_encerrar",
    "registrar_pos_fechar", "sanitizar_payload",
]
