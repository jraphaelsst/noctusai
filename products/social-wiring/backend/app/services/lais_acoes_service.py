"""Apply the actions agents returned in a turn (contract A4 / 2.2).

agents never writes SW tables: the model's "action tools" only RECORD intent and the turn
response carries it back; SW applies it HERE, after the reply was sent, idempotently:

  for each action in `seq` order
    1. insert into `lais_acoes_aplicadas` ON CONFLICT (org_id, lote_hash, seq) DO NOTHING
       -> nothing inserted means "this batch already applied it" -> skip (replay-safe);
    2. dispatch to the HANDLER REGISTRY by `tipo`;
    3. an UNKNOWN handler (its wave is not built yet) -> event `acao_sem_handler` + log;
       a handler that raises -> event `acao_falhou` + log. NEVER an exception that
       propagates: applying actions runs after the reply and must not undo or hide it.

Handler registry (waves append ONE line each, nobody edits `aplicar`):

    HANDLERS: dict[str, Handler]
    Handler = Callable[[AcaoCtx, dict], dict | None | Awaitable[dict | None]]

  here    salvar_slots · definir_operacao · encerrar
  wave 3  qualificar_lead      wave 5  pedido_visita      wave 8  captacao

`handler(ctx, payload)` gets the RAW payload (so a wave-5 handler can read the CPF); the ledger
stores a sanitised copy (CPF -> hash + last 3 digits, contract 17). The returned dict (or None)
is stored as `resultado`. `registrar_handler(tipo, fn)` binds one at runtime (tests / late binding).

Closing an episode (`fechar_interacao`) asks agents for the summary (`AgentsClient.resumo`, A5)
and stores it on the `lais_interacoes` row; a failed `/resumo` still closes the episode (event
`resumo_falhou`) -- the summary is enrichment, the close is the state change.
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

from app.clients.agents import AgentsClient, AgentsClientError, ResumoRequest, TurnResult
from app.services import lais_contatos_service as contatos
from app.services import lais_eventos_service as eventos
from app.services import lais_notificacoes_service as notificacoes
from app.services import lais_slots_sensiveis as sensiveis

logger = logging.getLogger(__name__)

SLOT_VALOR_MAX = 500
_SLOT_CHAVE_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,100}@[^@\s]{1,100}\.[^@\s]{2,30}$")
OPERACOES = frozenset({"compra", "aluguel", "administracao", "atualizacao"})
MOTIVOS_ENCERRAR = frozenset({"lead_encerrou", "sem_interesse", "invalido", "outro"})


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
    perguntas: Sequence[dict[str, Any]] = field(default_factory=tuple)
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
    perguntas: Sequence[dict[str, Any]] = (),
    agora: Optional[datetime] = None,
) -> dict[str, Any]:
    """Close an open episode: ask agents for `/resumo` (when there is a conversation to summarise
    and a client), then stamp `encerrada_at` + summary/slots/intencoes/desfecho/custo."""
    if interacao.get("encerrada_at"):
        return interacao
    agora = agora or datetime.now(timezone.utc)
    patch: dict[str, Any] = {"encerrada_at": agora.isoformat()}
    if agents_client is None or not conversation_id:
        logger.info("lais: closing interacao=%s without a summary (no agents client / conversation)", interacao["id"])
    else:
        try:
            res = await agents_client.resumo(
                conversation_id, ResumoRequest(perguntas=tuple(perguntas), desde=_dt(interacao.get("iniciada_at")))
            )
        except AgentsClientError as exc:
            logger.error("lais: /resumo failed (%s) interacao=%s -- closing without a summary", type(exc).__name__, interacao["id"])
            eventos.emitir(client, org_id, "resumo_falhou", contato["id"],
                           {"interacao_id": str(interacao["id"]), "erro": type(exc).__name__, "codigo": exc.code})
        else:
            patch.update(
                resumo=res.resumo, slots=res.slots, intencoes=list(res.intencoes), desfecho=res.desfecho,
                custo_usd=res.custo_usd,
            )
            if res.operacao:
                patch["operacao"] = res.operacao
    # `encerrada_at IS NULL` in the WHERE: a concurrent close wins, ours is a no-op.
    client.table(contatos.T_INTERACOES).update(patch).eq("id", str(interacao["id"])).is_("encerrada_at", "null").execute()
    if patch.get("intencoes"):
        notificacoes.avisar_cobranca(client, org_id, contato, interacao, patch["intencoes"])
    return {**interacao, **patch}


# ── built-in handlers ───────────────────────────────────────────────────────
def _h_salvar_slots(ctx: AcaoCtx, payload: dict[str, Any]) -> HandlerResult:
    slots_in = payload.get("slots")
    if not isinstance(slots_in, dict):
        return {"salvos": [], "ignorados": [], "erro": "slots_invalido"}
    permitidas = {str(p.get("chave")) for p in ctx.perguntas if p.get("chave")} | {"nome", "email"}
    slots = dict(ctx.contato.get("slots") or {})
    coluna: dict[str, Any] = {}
    salvos: list[str] = []
    ignorados: list[str] = []
    for chave, valor in slots_in.items():
        chave = str(chave)
        if not _SLOT_CHAVE_RE.match(chave) or chave not in permitidas or not isinstance(valor, (str, int, float)) or isinstance(valor, bool):
            ignorados.append(chave[:64])
            continue
        texto = str(valor).strip()[:SLOT_VALOR_MAX]
        if not texto:
            ignorados.append(chave)
            continue
        if chave == "nome":
            coluna["nome"] = texto[:200]
        elif chave == "email":
            if _EMAIL_RE.match(texto):
                coluna["email"] = texto.lower()
            else:
                ignorados.append(chave)
                continue
        else:
            slots[chave] = texto
        salvos.append(chave)
    if slots != (ctx.contato.get("slots") or {}):
        coluna["slots"] = slots
    if coluna:
        contatos.atualizar_contato(ctx.client, ctx.contato["id"], coluna)
        if ctx.interacao is not None and "slots" in coluna:
            ctx.client.table(contatos.T_INTERACOES).update({"slots": coluna["slots"]}).eq("id", str(ctx.interacao["id"])).execute()
    return {"salvos": salvos, "ignorados": ignorados}


def _h_definir_operacao(ctx: AcaoCtx, payload: dict[str, Any]) -> HandlerResult:
    operacao = payload.get("operacao")
    if operacao not in OPERACOES:
        return {"erro": "operacao_invalida"}
    contatos.atualizar_contato(ctx.client, ctx.contato["id"], {"operacao": operacao})
    if ctx.interacao is not None:
        ctx.client.table(contatos.T_INTERACOES).update({"operacao": operacao}).eq("id", str(ctx.interacao["id"])).execute()
    return {"operacao": operacao}


async def _h_encerrar(ctx: AcaoCtx, payload: dict[str, Any]) -> HandlerResult:
    motivo = payload.get("motivo") if payload.get("motivo") in MOTIVOS_ENCERRAR else "outro"
    agora = datetime.now(timezone.utc)
    # gen + 1 first: every job queued for this contato is now stale (contract 0.2).
    contatos.bump_gen(ctx.client, ctx.contato["id"], encerrado_at=agora.isoformat())
    fechada = None
    if ctx.interacao is not None:
        fechada = await fechar_interacao(
            ctx.client, org_id=ctx.org_id, contato=ctx.contato, interacao=ctx.interacao,
            agents_client=ctx.agents_client, conversation_id=ctx.conversation_id, perguntas=ctx.perguntas, agora=agora,
        )
    for hook in tuple(POS_ENCERRAR):
        try:
            hook(ctx, motivo)
        except Exception:
            # a policy hook (wave 3: WhatsApp invalido -> send to the SW) must never undo the close
            logger.exception("lais: pos-encerrar hook %s failed (org=%s)", getattr(hook, "__name__", "?"), ctx.org_id)
    return {"motivo": motivo, "interacao_id": str(ctx.interacao["id"]) if ctx.interacao else None,
            "desfecho": (fechada or {}).get("desfecho")}


#: Hooks run after an `encerrar` closed the episode: `hook(ctx, motivo)`. Wave 3 binds the
#: "WhatsApp invalido" policy here (`registrar_pos_encerrar`); the list is the registry, nobody edits `_h_encerrar`.
POS_ENCERRAR: list[Callable[[AcaoCtx, str], Any]] = []


def registrar_pos_encerrar(fn: Callable[[AcaoCtx, str], Any]) -> None:
    """Idempotent: binding the same function twice keeps one entry."""
    if fn not in POS_ENCERRAR:
        POS_ENCERRAR.append(fn)


#: THE registry. Waves append `"<tipo>": <fn>` (or call `registrar_handler`).
HANDLERS: dict[str, Handler] = {
    "salvar_slots": _h_salvar_slots,
    "definir_operacao": _h_definir_operacao,
    "encerrar": _h_encerrar,
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
    except Exception:
        logger.exception("lais: could not store the result of action seq=%s lote=%s", seq, lote_hash[:12])


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
    perguntas: Sequence[dict[str, Any]] = (),
    connection_id: Optional[UUID | str] = None,
    chat_id: Optional[str] = None,
    handlers: Optional[Mapping[str, Handler]] = None,
) -> list[dict[str, Any]]:
    """`handlers=None` uses THE registry (`HANDLERS`). Apply `result.lais_actions` in `seq` order; returns one summary per action
    `{seq, tipo, estado}` with estado in `aplicada | repetida | sem_handler | falhou`. Never raises."""
    resumo: list[dict[str, Any]] = []
    conversation_id = conversation_id or result.conversation_id
    for acao in result.lais_actions:
        try:
            resumo.append(await _aplicar_uma(
                client, org_id=org_id, contato_id=contato["id"], acao=acao, lote_hash=lote_hash,
                conversation_id=conversation_id, agents_client=agents_client, core_client=core_client,
                perguntas=perguntas, connection_id=connection_id, chat_id=chat_id,
                handlers=HANDLERS if handlers is None else handlers,
            ))
        except Exception:
            # The ledger insert itself failed (DB down): the reply is already sent, so report, don't raise.
            logger.exception("lais: action %s seq=%s could not be applied (org=%s)", acao.type, acao.seq, org_id)
            resumo.append({"seq": acao.seq, "tipo": acao.type, "estado": "falhou"})
    return resumo


async def _aplicar_uma(
    client: Any, *, org_id: UUID | str, contato_id: Any, acao: Any, lote_hash: str, conversation_id: Optional[str],
    agents_client: Optional[AgentsClient], core_client: Any, perguntas: Sequence[dict[str, Any]],
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
        logger.info("lais: action %s seq=%s of lote %s already applied -- skipped", acao.type, acao.seq, lote_hash[:12])
        return {"seq": acao.seq, "tipo": acao.type, "estado": "repetida"}

    handler = handlers.get(acao.type)
    if handler is None:
        logger.warning("lais: no handler for action %r (its wave is not built) org=%s", acao.type, org_id)
        eventos.emitir(client, org_id, "acao_sem_handler", contato_id, {"tipo": acao.type, "seq": acao.seq})
        _atualizar_resultado(client, org_id, lote_hash, acao.seq, {"sem_handler": True})
        return {"seq": acao.seq, "tipo": acao.type, "estado": "sem_handler"}

    # Fresh state per action: an earlier handler of the same batch may have changed it.
    cont = (client.table(contatos.T_CONTATOS).select("*").eq("id", str(contato_id)).limit(1).execute().data or [None])[0]
    if cont is None:
        raise LookupError(f"lais contato {contato_id} vanished mid-batch")
    ctx = AcaoCtx(
        client=client, org_id=org_id, contato=cont, interacao=contatos.interacao_aberta(client, contato_id),
        lote_hash=lote_hash, seq=acao.seq, tipo=acao.type, conversation_id=conversation_id,
        agents_client=agents_client, core_client=core_client, perguntas=perguntas,
        connection_id=connection_id, chat_id=chat_id,
    )
    try:
        out = handler(ctx, acao.payload)
        if inspect.isawaitable(out):
            out = await out
    except Exception as exc:
        logger.exception("lais: handler for %s seq=%s failed (org=%s)", acao.type, acao.seq, org_id)
        eventos.emitir(client, org_id, "acao_falhou", contato_id, {"tipo": acao.type, "seq": acao.seq, "erro": type(exc).__name__})
        _atualizar_resultado(client, org_id, lote_hash, acao.seq, {"erro": type(exc).__name__})
        return {"seq": acao.seq, "tipo": acao.type, "estado": "falhou"}
    _atualizar_resultado(client, org_id, lote_hash, acao.seq, out or {})
    return {"seq": acao.seq, "tipo": acao.type, "estado": "aplicada"}


__all__ = [
    "AcaoCtx", "HANDLERS", "Handler", "MOTIVOS_ENCERRAR", "OPERACOES", "aplicar", "fechar_interacao",
    "POS_ENCERRAR", "lote_hash_de", "registrar_handler", "registrar_pos_encerrar", "sanitizar_payload",
]
