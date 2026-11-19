"""Chat service -- conversations, messages, memories, caps and the SSE stream
(``specs/geracao-contract.md`` sections 2.6, 4.6, 6.2, 9.4).

Everything is private to the caller: a conversation of another user of the same org is a 404, same as
a foreign org (ids are not enumerable). The stream follows the seed ``help_chat`` wire format
(``{"delta"}`` / ``{"truncated"}`` / ``{"done"}`` / ``{"error"}``) plus a leading ``{"meta"}`` frame,
and its continuation rounds; it does NOT mount the help_chat router (that organ never reads tenant
data -- this chat is the opposite).

Persistence rules (6.2): the user message is written BEFORE the model is called and is never lost;
the assistant message is written as ``completa`` on done, ``parcial`` on client disconnect and
``erro`` on a model failure (partial text kept).

ONE unified chat (``estruturas-contract.md`` 6.5): there is no headline/roteiro agent any more. ``agente`` is accepted
on input and ignored; every read answers ``unificado`` (a legacy ``headline|roteiro`` row is presented as unified and
never filtered by it). On ``done`` the assistant text is parsed SERVER-SIDE into propostas (``services/propostas.py``,
the single derivation) and persisted -- message, propostas, Estrutura links and events in ONE transaction -- and
returned in the ``done`` frame.

``NOC-REMEDIATE[chat-stream-lock]`` -- 2026-10-10: "one stream per user" is an in-process guard
(single uvicorn worker today). Behind several workers it needs a shared lock (DB advisory / Redis seam).
``NOC-REMEDIATE[chat-retention]`` -- 2026-10-10: conversations and memories are kept until the user deletes them.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Callable, Mapping, Optional

from fastapi.concurrency import run_in_threadpool

from noctusai_lib.domain.help_chat.router import PEDIDO_CONTINUACAO
from noctusai_lib.domain.help_chat.service import build_conversation_messages
from noctusai_lib.realtime.sse import sse_event
from noctusai_lib.integrations.llm import (
    LLMAPIError,
    LLMBudgetExceeded,
    LLMNotConfigured,
    StreamOutcome,
    chat_completion_stream,
)
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched

from app.config import settings
from app.modules.media_creation.limites_geracao import limite_geracao
from app.modules.media_creation.prompts import chat_unificado
from app.modules.media_creation.services.chat_contexto import (
    ChatContexto,
    ChatError,
    ContextoMontado,
    ReferenciaResolvida,
    eh_uuid,
)
from app.modules.media_creation.services.diretor_criacao import (
    AGENT_KEY,
    VIA_DIRETOR,
    VIA_LEGADO,
    DiretorCriacao,
    DiretorIndisponivel,
    TurnoDiretor,
)
from app.modules.media_creation.services.fluxo_service import FluxoService
from app.modules.media_creation.services.propostas import EstruturaCitavel, codigos_citados
from app.modules.media_creation.services.publicacao_service import PublicacaoService
from app.modules.media_creation.services.publicacoes import extrair_publicacoes, vincular_publicacoes

logger = logging.getLogger(__name__)

CONVERSAS = "cs_chat_conversas"
MENSAGENS = "cs_chat_mensagens"
MEMORIAS = "cs_memorias"
MARCAS = "marcas"
FLUXO_EVENTOS = "cs_fluxo_eventos"

TITULO_PADRAO = "Nova conversa"
MAX_TITULO_AUTO = 60
MAX_MEMORIAS = 50
HISTORICO_MAX_MENSAGENS = 20
HISTORICO_MAX_CHARS = 40_000
MAX_CONTINUACOES = 2
MAX_TOKENS_POR_RODADA = 4096
TEMPERATURA = 0.7
PROVIDER = "anthropic"
JANELA_CAP = timedelta(hours=24)
#: A stream lock older than this is considered leaked (a response that never started its generator).
LOCK_TTL_SECONDS = 600.0

ERRO_IA_NAO_CONFIGURADA = "ia_nao_configurada"
ERRO_ORCAMENTO = "orcamento_ia_excedido"
ERRO_IA_INDISPONIVEL = "ia_indisponivel"
ERRO_STREAM_EM_ANDAMENTO = "stream_em_andamento"
ERRO_LIMITE = "limite_de_mensagens"
ERRO_DIRETOR = "diretor_indisponivel"
ESTRUTURAS = "cs_estruturas"
MAX_CODIGOS_DO_DIRETOR = 40

#: ``(messages, *, model, provider, org_id, outcome) -> AsyncIterator[str]`` -- DI seam; tests inject
#: a fake that fills ``outcome`` (a ``StreamOutcome``) once drained.
ChatStreamFn = Callable[..., AsyncIterator[str]]

CONVERSA_COLS = "id,org_id,marca_id,user_id,agente,titulo,last_message_at"
MENSAGEM_COLS = "id,role,conteudo,referencias,status,truncada,created_at,tipo,proposta_id"

#: The ONE agent value every read answers (legacy ``headline`` / ``roteiro`` rows are presented as unified).
AGENTE_UNIFICADO = "unificado"
#: The fluxo event kinds the citation parser may report (``cs_fluxo_eventos.tipo``); anything else is a parser bug.
EVENTOS_DO_PARSER = frozenset({
    "citacao_rejeitada", "formato_misturado", "placeholder_remanescente", "atribuicao_ausente", "roteiro_invalido",
})
#: ``(texto, codigos_permitidos) -> ResultadoPropostas`` -- DI seam over ``services/propostas.extrair_propostas``.
ExtrairFn = Callable[[str, Mapping[str, Any]], Any]
RESOLUCAO_VAZIA = {"resolvidos": [], "ambiguos": [], "nao_encontrados": []}


def default_stream_fn(
    messages: list[dict], *, model: str, provider: str, org_id: Optional[str], outcome: StreamOutcome
) -> AsyncIterator[str]:
    return chat_completion_stream(
        messages, model=model, provider=provider, org_id=org_id,
        temperature=TEMPERATURA, max_tokens=MAX_TOKENS_POR_RODADA, outcome=outcome,
    )


def get_chat_stream_fn() -> ChatStreamFn:
    """FastAPI dependency -- the model stream. Tests override it with a fake."""
    return default_stream_fn


def extrair_propostas_padrao(texto: str, codigos_permitidos: Mapping[str, Any]) -> Any:
    """The real parser (``services/propostas.py``, EST-4a: a PURE parser/validator, no DB writes)."""
    from app.modules.media_creation.services.propostas import extrair_propostas

    return extrair_propostas(texto, codigos_permitidos)


def get_extrair_propostas() -> ExtrairFn:
    """FastAPI dependency -- the citation parser. Tests override it (a parser of their own, never a patched guard)."""
    return extrair_propostas_padrao


# ── one stream per user ──────────────────────────────────────────────────

_streams: dict[str, float] = {}
_streams_lock = threading.Lock()


def _adquirir_stream(user_id: str) -> bool:
    agora = time.monotonic()
    with _streams_lock:
        desde = _streams.get(user_id)
        if desde is not None and agora - desde < LOCK_TTL_SECONDS:
            return False
        _streams[user_id] = agora
        return True


def liberar_stream(user_id: str) -> None:
    with _streams_lock:
        _streams.pop(user_id, None)


def novo_id() -> str:
    return str(uuid.uuid4())


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_ts(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not isinstance(valor, str):
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def conversa_out(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r.get(k) for k in ("id", "marca_id", "titulo", "last_message_at")}
    out["agente"] = AGENTE_UNIFICADO  # a legacy headline|roteiro row is PRESENTED as unified, never filtered by it
    return out


def mensagem_out(
    r: dict[str, Any], propostas: Optional[list[dict[str, Any]]] = None, fluxo: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    return {
        "id": r["id"], "role": r["role"], "conteudo": r.get("conteudo") or "",
        "referencias": r.get("referencias") or [], "status": r.get("status") or "completa",
        "truncada": bool(r.get("truncada")), "created_at": r.get("created_at"),
        "tipo": r.get("tipo") or "texto", "propostas": propostas or [], "fluxo": fluxo,
    }


def _sistema(montado: ContextoMontado) -> str:
    prompt = chat_unificado.SYSTEM_PROMPT
    return f"{prompt}\n\n{montado.texto}" if montado.texto else prompt


def _agente_do_contexto(conversa: dict[str, Any]) -> str:
    """What ``ChatContexto.montar`` is told. The unified chat IS the headline conversation (its context is the headline
    context: perfil, memorias, mentions, the Estrutura pool); a legacy ``roteiro`` row keeps the context it was written
    with until the context itself stops branching on the agent (EST-4a)."""
    return conversa["agente"] if conversa["agente"] in ("headline", "roteiro") else "headline"


def mapa_citavel(contexto: ContextoMontado) -> Mapping[str, Any]:
    """The ``{codigo: EstruturaCitavel}`` the context put in front of the model (``ContextoMontado.citaveis``, EST-4a):
    what ``propostas.extrair_propostas`` validates the model's citations against."""
    return contexto.citaveis


def codigos_para_meta(contexto: ContextoMontado) -> list[int]:
    """``meta.codigos_permitidos``: the Estrutura ``codigo`` numbers the model was allowed to cite."""
    return list(contexto.codigos_permitidos)


@dataclass
class Envio:
    """Everything the stream generator needs, resolved before the first byte."""

    conversa: dict[str, Any]
    mensagens: list[dict[str, Any]]
    sistema: str
    contexto: ContextoMontado
    mensagem_usuario_id: str
    referencias: list[dict[str, str]]
    stream_fn: ChatStreamFn
    primeira: Optional[str]
    rodada: AsyncIterator[str]
    outcome: StreamOutcome
    modelo: str
    extrair: ExtrairFn = extrair_propostas_padrao
    modo_estrutura: str = "auto"
    resolucao_perfis: Optional[dict[str, Any]] = None
    #: Which engine answers this turn: ``legado`` (the direct-model stream) or ``diretor`` (the agents product's Diretor de
    #: Criação, per-org switch ``chat_diretor_criacao``). Exactly one per turn; a failing Diretor never falls back.
    via: str = VIA_LEGADO


async def _rodada_diretor(diretor: DiretorCriacao, turno: TurnoDiretor, outcome: StreamOutcome) -> AsyncIterator[str]:
    """The Diretor's turn as the one-round stream ``ChatService.eventos`` already consumes: the (non-streaming) agents turn
    runs when iteration starts -- AFTER the ``meta`` and ``status`` frames -- and its whole text is the single delta."""
    resposta = await diretor.responder(turno)
    outcome.truncated = False
    yield resposta.texto


class ChatService:
    def __init__(self, db: Any, org_id: str, user_id: str, *, fluxo: Optional[FluxoService] = None) -> None:
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.contexto = ChatContexto(db, org_id, user_id, settings.chat_contexto_max_chars)
        self.fluxo = fluxo if fluxo is not None else FluxoService(db, org_id, user_id)

    # ── guards ───────────────────────────────────────────────────────────

    def assert_marca(self, marca_id: str) -> None:
        rows = self.db.table(MARCAS).select("id").eq("id", marca_id).eq("org_id", self.org_id).execute().data
        if not rows:
            raise ChatError(404, "Marca não encontrada")

    def get_conversa(self, conversa_id: str) -> dict[str, Any]:
        rows = (
            self.db.table(CONVERSAS).select(CONVERSA_COLS)
            .eq("id", conversa_id).eq("org_id", self.org_id).eq("user_id", self.user_id).execute().data
        )
        if not rows:
            raise ChatError(404, "Conversa não encontrada")
        return rows[0]

    # ── conversations ────────────────────────────────────────────────────

    def list_conversas(self, marca_id: str, limit: int, offset: int) -> dict[str, Any]:
        """Conversations are listed per (user, marca) only: the legacy ``agente`` filter is gone (a legacy row is a unified one)."""
        self.assert_marca(marca_id)
        rows = (
            self.db.table(CONVERSAS).select(CONVERSA_COLS)
            .eq("org_id", self.org_id).eq("user_id", self.user_id)
            .eq("marca_id", marca_id)
            .order("last_message_at", desc=True).range(offset, offset + limit).execute().data
        ) or []
        return {"items": [conversa_out(r) for r in rows[:limit]], "tem_mais": len(rows) > limit}

    def create_conversa(self, marca_id: str, titulo: Optional[str]) -> dict[str, Any]:
        self.assert_marca(marca_id)
        agora = _iso(_agora())
        row = {
            "id": novo_id(), "org_id": self.org_id, "marca_id": marca_id, "user_id": self.user_id,
            "agente": AGENTE_UNIFICADO, "titulo": titulo or TITULO_PADRAO, "last_message_at": agora,
            "created_at": agora, "updated_at": agora,
        }
        self.db.table(CONVERSAS).insert(row).execute()
        return conversa_out(row)

    def rename_conversa(self, conversa_id: str, titulo: str) -> dict[str, Any]:
        self.get_conversa(conversa_id)
        rows = (
            self.db.table(CONVERSAS).update({"titulo": titulo})
            .eq("id", conversa_id).eq("org_id", self.org_id).eq("user_id", self.user_id).execute().data
        )
        return conversa_out(rows[0] if rows else {**self.get_conversa(conversa_id)})

    def delete_conversa(self, conversa_id: str) -> None:
        self.get_conversa(conversa_id)
        self.db.table(MENSAGENS).delete().eq("conversa_id", conversa_id).eq("org_id", self.org_id).execute()
        self.db.table(CONVERSAS).delete().eq("id", conversa_id).eq("org_id", self.org_id).eq(
            "user_id", self.user_id
        ).execute()

    # ── messages ─────────────────────────────────────────────────────────

    def list_mensagens(self, conversa_id: str, antes: Optional[str], limit: int) -> dict[str, Any]:
        self.get_conversa(conversa_id)
        q = (
            self.db.table(MENSAGENS).select(MENSAGEM_COLS)
            .eq("conversa_id", conversa_id).eq("org_id", self.org_id)
        )
        if antes:
            if not eh_uuid(antes):
                raise ChatError(422, "Cursor inválido")
            ref = (
                self.db.table(MENSAGENS).select("created_at")
                .eq("id", antes).eq("conversa_id", conversa_id).eq("org_id", self.org_id).execute().data
            )
            if not ref:
                raise ChatError(404, "Mensagem não encontrada")
            q = q.lt("created_at", ref[0]["created_at"])
        rows = q.order("created_at", desc=True).limit(limit + 1).execute().data or []
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        pagina = list(reversed(rows[:limit]))
        propostas = self.fluxo.propostas_por_mensagem(r["id"] for r in pagina if r["role"] == "assistant")
        items = []
        for r in pagina:
            fluxo = None
            if (r.get("tipo") or "texto") == "roteiro_gerado" and r.get("proposta_id"):
                proposta = self.fluxo.get_proposta(str(r["proposta_id"]))
                fluxo = self.fluxo.compor_fluxo(proposta) if proposta else None
            items.append(mensagem_out(r, propostas.get(str(r["id"])), fluxo))
        return {"items": items, "tem_mais": len(rows) > limit}

    def _historico(self, conversa_id: str) -> list[dict[str, str]]:
        rows = (
            self.db.table(MENSAGENS).select("role,conteudo,created_at")
            .eq("conversa_id", conversa_id).eq("org_id", self.org_id)
            .order("created_at", desc=True).limit(HISTORICO_MAX_MENSAGENS).execute().data
        ) or []
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        usados: list[dict[str, str]] = []
        total = 0
        for r in rows:  # newest first: the oldest are dropped when the char cap bites
            texto = r.get("conteudo") or ""
            if not texto.strip():
                continue
            if total + len(texto) > HISTORICO_MAX_CHARS:
                break
            total += len(texto)
            usados.append({"role": r["role"], "content": texto})
        usados.reverse()
        return usados

    def _gravar_mensagem(self, conversa_id: str, role: str, conteudo: str, **extra: Any) -> dict[str, Any]:
        row = {
            "id": novo_id(), "org_id": self.org_id, "conversa_id": conversa_id, "role": role,
            "conteudo": conteudo, "referencias": extra.pop("referencias", []),
            "status": extra.pop("status", "completa"), "truncada": extra.pop("truncada", False),
            "created_at": _iso(_agora()), **extra,
        }
        self.db.table(MENSAGENS).insert(row).execute()
        return row

    def _tocar_conversa(self, conversa_id: str, titulo: Optional[str] = None) -> None:
        patch: dict[str, Any] = {"last_message_at": _iso(_agora())}
        if titulo:
            patch["titulo"] = titulo
        self.db.table(CONVERSAS).update(patch).eq("id", conversa_id).eq("org_id", self.org_id).eq(
            "user_id", self.user_id
        ).execute()

    # ── caps (9.4) ───────────────────────────────────────────────────────

    def _retry_after(self, criados: list[datetime], limite: int, agora: datetime) -> int:
        """Seconds until the oldest counted message leaves the 24 h window."""
        if not criados:
            return 3600
        criados = sorted(criados)
        liberar = criados[max(len(criados) - limite, 0)] + JANELA_CAP
        return max(int((liberar - agora).total_seconds()), 60)

    def checar_caps(self) -> None:
        agora = _agora()
        desde = _iso(agora - JANELA_CAP)

        def paginas(montar):
            def page(start: int, end: int):
                return montar().order("id").range(start, end).execute().data
            return iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_chat_mensagens")

        # org-wide
        org_msgs = [
            _parse_ts(r["created_at"])
            for r in paginas(lambda: self.db.table(MENSAGENS).select("id,created_at")
                             .eq("org_id", self.org_id).eq("role", "user").gte("created_at", desde))
        ]
        # per user: through the user's conversations active inside the window
        conv_ids = [
            r["id"] for r in iter_paged_rows(
                lambda s, e: self.db.table(CONVERSAS).select("id").eq("org_id", self.org_id)
                .eq("user_id", self.user_id).gte("last_message_at", desde).order("id").range(s, e).execute().data,
                page_size=PAGE_SIZE, label="cs_chat_conversas",
            )
        ]
        user_msgs: list[datetime] = []
        for lote in batched(conv_ids):
            user_msgs += [
                _parse_ts(r["created_at"])
                for r in paginas(lambda lote=lote: self.db.table(MENSAGENS).select("id,created_at")
                                 .eq("org_id", self.org_id).eq("role", "user").gte("created_at", desde)
                                 .in_("conversa_id", lote))
            ]
        user_msgs = [d for d in user_msgs if d]
        org_msgs = [d for d in org_msgs if d]
        limite_usuario = limite_geracao("chat_mensagens_dia_usuario", self.org_id, settings)
        limite_org = limite_geracao("chat_mensagens_dia_org", self.org_id, settings)
        if len(user_msgs) >= limite_usuario:
            raise ChatError(
                429, f"Você atingiu o limite de {limite_usuario} mensagens por dia no chat.",
                code=ERRO_LIMITE,
                headers={"Retry-After": str(self._retry_after(user_msgs, limite_usuario, agora))},
            )
        if len(org_msgs) >= limite_org:
            raise ChatError(
                429, "A sua organização atingiu o limite diário de mensagens no chat.", code=ERRO_LIMITE,
                headers={"Retry-After": str(self._retry_after(org_msgs, limite_org, agora))},
            )

    # ── memories (endpoint 47) ───────────────────────────────────────────

    def list_memorias(self, marca_id: str) -> list[dict[str, Any]]:
        self.assert_marca(marca_id)
        rows = (
            self.db.table(MEMORIAS).select("id,texto,created_at")
            .eq("org_id", self.org_id).eq("user_id", self.user_id).eq("marca_id", marca_id)
            .order("created_at").execute().data
        ) or []
        return [{"id": r["id"], "texto": r["texto"], "created_at": r["created_at"]} for r in rows]

    def create_memoria(self, marca_id: str, texto: str) -> dict[str, Any]:
        self.assert_marca(marca_id)
        existentes = (
            self.db.table(MEMORIAS).select("id")
            .eq("org_id", self.org_id).eq("user_id", self.user_id).eq("marca_id", marca_id).execute().data
        ) or []
        if len(existentes) >= MAX_MEMORIAS:
            raise ChatError(409, f"Limite de {MAX_MEMORIAS} memórias atingido. Apague alguma para salvar outra.")
        row = {
            "id": novo_id(), "org_id": self.org_id, "user_id": self.user_id, "marca_id": marca_id,
            "texto": texto, "created_at": _iso(_agora()),
        }
        self.db.table(MEMORIAS).insert(row).execute()
        return {"id": row["id"], "texto": texto, "created_at": row["created_at"]}

    def delete_memoria(self, memoria_id: str) -> None:
        rows = (
            self.db.table(MEMORIAS).select("id")
            .eq("id", memoria_id).eq("org_id", self.org_id).eq("user_id", self.user_id).execute().data
        )
        if not rows:
            raise ChatError(404, "Memória não encontrada")
        self.db.table(MEMORIAS).delete().eq("id", memoria_id).eq("org_id", self.org_id).eq(
            "user_id", self.user_id
        ).execute()

    # ── context meter (endpoint 48) ──────────────────────────────────────

    def medir_contexto(self, conversa_id: str) -> dict[str, Any]:
        conversa = self.get_conversa(conversa_id)
        montado = self.contexto.montar(conversa, [])
        return {"contexto_chars": montado.chars, "limite": settings.chat_contexto_max_chars}

    # ── send (pre-stream) ────────────────────────────────────────────────

    def _preparar_sync(self, conversa_id: str, conteudo: str, referencias: list[Any]) -> dict[str, Any]:
        """Every refusal that must be a plain HTTP status happens here, BEFORE anything is persisted
        (except the lock, released by the caller): ownership 404s, caps 429, one-stream 409."""
        conversa = self.get_conversa(conversa_id)
        resolvidas = self.contexto.resolver(conversa["marca_id"], referencias)
        self.checar_caps()
        if not _adquirir_stream(self.user_id):
            raise ChatError(409, "Já existe uma resposta sendo gerada. Aguarde ela terminar.",
                            code=ERRO_STREAM_EM_ANDAMENTO)
        try:
            historico = self._historico(conversa_id)
            eh_primeira = not historico and not (
                self.db.table(MENSAGENS).select("id").eq("conversa_id", conversa_id)
                .eq("org_id", self.org_id).limit(1).execute().data
            )
            # the typed text turns on the free-text profile resolution (8.3); the profiles it resolved are stored on the
            # message `referencias` (each carries via="texto") next to the explicit mentions
            montado = self.contexto.montar({**conversa, "agente": _agente_do_contexto(conversa)}, resolvidas, texto=conteudo)
            refs_dict = [r.como_dict() for r in [*resolvidas, *montado.referencias_via_texto]]
            msg = self._gravar_mensagem(conversa_id, "user", conteudo, referencias=refs_dict)
            self._gravar_eventos_do_contexto(conversa, msg["id"], montado.eventos)
            titulo = conteudo[:MAX_TITULO_AUTO].strip() if eh_primeira and conversa["titulo"] == TITULO_PADRAO else None
            self._tocar_conversa(conversa_id, titulo)
        except Exception:
            liberar_stream(self.user_id)
            raise
        return {"conversa": conversa, "historico": historico, "montado": montado,
                "msg_id": msg["id"], "refs": refs_dict}

    def _gravar_eventos_do_contexto(self, conversa: dict[str, Any], mensagem_id: str, eventos: list[dict[str, Any]]) -> None:
        """The name-resolution outcomes (``perfil_resolvido|perfil_ambiguo|perfil_nao_encontrado`` + ``contagem``) of this
        turn, as ``cs_fluxo_eventos`` rows (no content: counts only)."""
        if not eventos:
            return
        self.db.table(FLUXO_EVENTOS).insert([
            {"id": novo_id(), "org_id": self.org_id, "marca_id": conversa["marca_id"], "conversa_id": conversa["id"],
             "mensagem_id": mensagem_id, "ator_id": self.user_id, "tipo": e["tipo"], "contagem": int(e.get("contagem") or 0)}
            for e in eventos
        ]).execute()

    async def preparar_envio(
        self, conversa_id: str, conteudo: str, referencias: list[Any], stream_fn: ChatStreamFn,
        extrair: ExtrairFn = extrair_propostas_padrao, diretor: Optional[DiretorCriacao] = None,
    ) -> Envio:
        """``diretor`` given = this org's turn is answered by the Diretor de Criação (the router decides, from the per-org
        switch, and refuses a missing Diretor BEFORE this runs); ``stream_fn`` is then unused."""
        prep = await run_in_threadpool(self._preparar_sync, conversa_id, conteudo, referencias)
        conversa = prep["conversa"]
        if diretor is not None:
            outcome = StreamOutcome()
            turno = TurnoDiretor(
                org_id=self.org_id, marca_id=str(conversa["marca_id"]), conversa_id=str(conversa["id"]),
                mensagem_id=prep["msg_id"], texto=conteudo,
            )
            return Envio(
                conversa=conversa, mensagens=prep["historico"], sistema="", contexto=prep["montado"],
                mensagem_usuario_id=prep["msg_id"], referencias=prep["refs"], stream_fn=stream_fn, primeira=None,
                rodada=_rodada_diretor(diretor, turno, outcome), outcome=outcome, modelo=AGENT_KEY, extrair=extrair,
                modo_estrutura=prep["montado"].modo_estrutura, via=VIA_DIRETOR,
                resolucao_perfis=prep["montado"].resolucao.como_dict() if prep["montado"].resolucao is not None else None,
            )
        modelo = settings.geracao_llm_model
        sistema = _sistema(prep["montado"])
        mensagens = build_conversation_messages(
            system_prompt=sistema,
            history=prep["historico"] + [{"role": "user", "content": conteudo}],
            provider=PROVIDER,
        )
        outcome = StreamOutcome()
        agen = stream_fn(mensagens, model=modelo, provider=PROVIDER, org_id=self.org_id, outcome=outcome)
        try:
            primeira = await agen.__anext__()
        except StopAsyncIteration:
            primeira = None
        except LLMNotConfigured as exc:
            liberar_stream(self.user_id)
            logger.warning("chat: IA não configurada org=%s", self.org_id)
            raise ChatError(503, "A IA não está configurada (chave da Anthropic ausente).",
                            code=ERRO_IA_NAO_CONFIGURADA) from exc
        except LLMBudgetExceeded as exc:
            liberar_stream(self.user_id)
            logger.warning("chat: orçamento de IA excedido org=%s", self.org_id)
            raise ChatError(503, "O limite de uso de IA da organização foi atingido.", code=ERRO_ORCAMENTO) from exc
        except LLMAPIError as exc:
            liberar_stream(self.user_id)
            logger.error("chat: provedor de IA falhou org=%s", self.org_id)
            raise ChatError(502, "O provedor de IA não respondeu. Tente novamente em instantes.",
                            code=ERRO_IA_INDISPONIVEL) from exc
        except BaseException:
            liberar_stream(self.user_id)
            raise
        return Envio(
            conversa=conversa, mensagens=prep["historico"], sistema=sistema, contexto=prep["montado"],
            mensagem_usuario_id=prep["msg_id"], referencias=prep["refs"], stream_fn=stream_fn,
            primeira=primeira, rodada=agen, outcome=outcome, modelo=modelo, extrair=extrair,
            modo_estrutura=prep["montado"].modo_estrutura,
            resolucao_perfis=prep["montado"].resolucao.como_dict() if prep["montado"].resolucao is not None else None,
        )

    # ── the stream ───────────────────────────────────────────────────────

    def _salvar_resposta(self, envio: Envio, texto: str, status: str, truncada: bool) -> Optional[str]:
        """Sync on purpose: it also runs from ``finally`` on a client disconnect, where awaiting is unsafe."""
        try:
            row = self._gravar_mensagem(
                envio.conversa["id"], "assistant", texto, status=status, truncada=truncada,
                modelo=envio.modelo, contexto_chars=envio.contexto.chars,
            )
            self._tocar_conversa(envio.conversa["id"])
            return row["id"]
        except Exception:
            logger.exception("chat: falha ao gravar a resposta (status=%s) conversa=%s", status, envio.conversa["id"])
            return None

    def _finalizar_resposta(self, envio: Envio, texto: str, truncada: bool) -> tuple[Optional[str], list[dict[str, Any]]]:
        """Save the completed answer. With Estrutura citations to validate: parse (server-side, single derivation) and write
        message + propostas + Estrutura links + events in ONE transaction (``cs_chat_resposta_gravar``). Returns
        ``(mensagem_id, Proposta[])``. A text with no parsable headline is saved the plain way, ``propostas: []``."""
        mapa = mapa_citavel(envio.contexto)
        if envio.via == VIA_DIRETOR:
            # the Director's codes come from its tools (the platform-wide library), not from this context's pool
            mapa = {**self._citaveis_por_codigo(texto), **mapa}
        try:
            resultado = envio.extrair(texto, mapa)
        except Exception:
            # a parser bug must never cost the user the answer: keep the text, lose (loudly) its propostas
            logger.exception("chat: o parser de propostas falhou conversa=%s", envio.conversa["id"])
            return self._salvar_resposta(envio, texto, "completa", truncada), []
        propostas = list(getattr(resultado, "propostas", ()) or ())
        eventos = self._eventos_do_parser(getattr(resultado, "eventos", ()) or ())
        if not propostas and not eventos:
            return self._salvar_resposta(envio, texto, "completa", truncada), []
        payload = {
            "org_id": self.org_id, "conversa_id": envio.conversa["id"], "user_id": self.user_id, "conteudo": texto,
            "truncada": truncada, "modelo": envio.modelo, "contexto_chars": envio.contexto.chars,
            "propostas": [
                {
                    # contract 16.2/16.5: a roteiro proposta carries its title, formato (the principal Estrutura's)
                    # and the WHOLE script as texto; a headline carries neither (the DB CHECK pins both shapes)
                    "ordem": p.ordem, "tipo": p.tipo, "texto": p.headline, "titulo": p.titulo, "formato": p.formato,
                    "gatilho_tag": p.gatilho, "estrutura_ids": list(dict.fromkeys(str(i) for i in p.estrutura_ids))[:3],
                }
                for p in propostas
            ],
            "eventos": eventos,
        }
        try:
            res = self.db.rpc("cs_chat_resposta_gravar", {"p": payload}).execute()
            data = res.data[0] if isinstance(res.data, list) else res.data
            mensagem_id = str(data["mensagem_id"])
            self._tocar_conversa(envio.conversa["id"])
            ids = [str(p["id"]) for p in sorted(data.get("propostas") or [], key=lambda x: x["ordem"])]
            if envio.via == VIA_DIRETOR:
                self._gravar_publicacoes(envio.conversa, mensagem_id, texto, propostas, data.get("propostas") or [])
            rows = [self.fluxo.get_proposta(i) for i in ids]
            return mensagem_id, self.fluxo.apresentar_propostas([r for r in rows if r])
        except Exception:
            # the user keeps the answer: save the text the plain way and say loudly that its propostas were lost
            logger.exception("chat: falha ao gravar a resposta com propostas conversa=%s", envio.conversa["id"])
            return self._salvar_resposta(envio, texto, "completa", truncada), []

    def _citaveis_por_codigo(self, texto: str) -> dict[str, EstruturaCitavel]:
        """``{codigo: EstruturaCitavel}`` for every ACTIVE library Estrutura the reply cites (at most
        ``MAX_CODIGOS_DO_DIRETOR`` distinct codes; the rest stay unknown, so the parser rejects them, counted)."""
        codigos = [int(c) for c in codigos_citados(texto) if c.isdigit()][:MAX_CODIGOS_DO_DIRETOR]
        out: dict[str, EstruturaCitavel] = {}
        for lote in batched(codigos):
            rows = (
                self.db.table(ESTRUTURAS).select("id,codigo,formato").in_("codigo", lote).eq("status", "ativa").execute().data or []
            )
            for r in rows:
                out[str(r["codigo"])] = EstruturaCitavel(uuid.UUID(str(r["id"])), str(r["codigo"]), r.get("formato") or "")
        return out

    def _gravar_publicacoes(
        self, conversa: dict[str, Any], mensagem_id: str, texto: str, propostas: list[Any], salvas: list[dict[str, Any]],
    ) -> None:
        """The Publicação blocks of a Director reply, bound to the saved options. The answer is already saved: a failure here is
        logged loudly and costs the blocks (the card's caption then comes from the finalizer), never the answer."""
        try:
            lidas = extrair_publicacoes(texto)
            PublicacaoService(self.db, self.org_id, self.user_id).gravar(
                conversa, mensagem_id, salvas, vincular_publicacoes(propostas, lidas), lidas.invalidas,
            )
        except Exception:
            logger.exception("chat: falha ao gravar as publicações conversa=%s", conversa["id"])

    @staticmethod
    def _eventos_do_parser(eventos: Any) -> list[dict[str, Any]]:
        out = []
        for e in eventos:
            if e.get("tipo") not in EVENTOS_DO_PARSER:
                logger.error("chat: o parser de propostas devolveu um evento desconhecido: %r", e.get("tipo"))
                continue
            out.append({"tipo": e["tipo"], "contagem": int(e.get("contagem") or 0)})
        return out

    async def eventos(self, envio: Envio, conteudo: str) -> AsyncIterator[str]:
        """SSE frames: ``meta`` -> ``delta``... -> [``truncated``] -> ``done`` | ``error``."""
        conversa = envio.conversa
        org_id = self.org_id
        partes: list[str] = []
        outcome = envio.outcome
        salvo = False
        continuacoes = 0
        inicio = time.monotonic()

        async def falha(codigo: str, mensagem: str) -> str:
            nonlocal salvo
            if not salvo:
                salvo = True
                await run_in_threadpool(self._salvar_resposta, envio, "".join(partes), "erro", bool(outcome.truncated))
            return sse_event({"error": {"code": codigo, "message": mensagem}})

        try:
            yield sse_event({"meta": {
                "mensagem_usuario_id": envio.mensagem_usuario_id,
                "contexto_chars": envio.contexto.chars,
                "codigos_permitidos": codigos_para_meta(envio.contexto),
                "modo_estrutura": envio.modo_estrutura,
                "resolucao_perfis": envio.resolucao_perfis or RESOLUCAO_VAZIA,
                # the legacy frame stays byte-for-byte what it was (a pinned wire shape): only a Director turn names its engine
                **({"via": envio.via} if envio.via == VIA_DIRETOR else {}),
            }})
            if envio.via == VIA_DIRETOR:
                # the agents turn does not stream yet (contract 4): tell the screen the Director is working
                yield sse_event({"status": {"codigo": "diretor_trabalhando", "mensagem": "O Diretor de Criação está preparando as opções..."}})
            if envio.primeira is not None:
                partes.append(envio.primeira)
                yield sse_event({"delta": envio.primeira})
            rodada = envio.rodada
            while True:
                async for chunk in rodada:
                    partes.append(chunk)
                    yield sse_event({"delta": chunk})
                texto = "".join(partes)
                if not outcome.truncated or continuacoes >= MAX_CONTINUACOES or not texto.strip():
                    break
                continuacoes += 1
                outcome = StreamOutcome()
                rodada = envio.stream_fn(
                    build_conversation_messages(
                        system_prompt=envio.sistema,
                        history=envio.mensagens + [
                            {"role": "user", "content": conteudo},
                            {"role": "assistant", "content": texto},
                            {"role": "user", "content": PEDIDO_CONTINUACAO},
                        ],
                        provider=PROVIDER,
                    ),
                    model=envio.modelo, provider=PROVIDER, org_id=org_id, outcome=outcome,
                )
            truncada = bool(outcome.truncated)
            salvo = True
            mensagem_id, propostas = await run_in_threadpool(self._finalizar_resposta, envio, "".join(partes), truncada)
            if truncada:
                yield sse_event({"truncated": True})
            yield sse_event({"done": {"mensagem_id": mensagem_id, "propostas": propostas}})
            logger.info(
                "chat: stream ok org=%s conversa=%s chars=%d continuacoes=%d truncated=%s latency_ms=%d",
                org_id, conversa["id"], len("".join(partes)), continuacoes, truncada,
                int((time.monotonic() - inicio) * 1000),
            )
        except DiretorIndisponivel as exc:
            logger.warning("chat: diretor indisponível org=%s codigo=%s", org_id, exc.codigo)
            yield await falha(ERRO_DIRETOR, "O Diretor de Criação não respondeu. Tente novamente em instantes.")
        except LLMNotConfigured:
            logger.warning("chat: IA não configurada mid-stream org=%s", org_id)
            yield await falha(ERRO_IA_NAO_CONFIGURADA, "A IA não está configurada (chave da Anthropic ausente).")
        except LLMBudgetExceeded:
            logger.warning("chat: orçamento de IA excedido mid-stream org=%s", org_id)
            yield await falha(ERRO_ORCAMENTO, "O limite de uso de IA da organização foi atingido.")
        except LLMAPIError:
            logger.error("chat: provedor de IA falhou mid-stream org=%s", org_id)
            yield await falha(ERRO_IA_INDISPONIVEL, "O provedor de IA não respondeu. Tente novamente em instantes.")
        except Exception:
            logger.exception("chat: erro inesperado no streaming org=%s", org_id)
            yield await falha(ERRO_IA_INDISPONIVEL, "Ocorreu um erro inesperado. Tente novamente.")
        finally:
            if not salvo:  # client disconnected (GeneratorExit / cancel): keep what was streamed
                salvo = True
                self._salvar_resposta(envio, "".join(partes), "parcial", bool(outcome.truncated))
            liberar_stream(self.user_id)


__all__ = [
    "AGENTE_UNIFICADO", "ChatError", "ChatService", "ChatStreamFn", "ERRO_STREAM_EM_ANDAMENTO", "Envio", "ExtrairFn",
    "TITULO_PADRAO", "conversa_out", "extrair_propostas_padrao", "get_chat_stream_fn", "get_extrair_propostas",
    "liberar_stream", "mensagem_out",
]
