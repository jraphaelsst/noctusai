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
from typing import Any, AsyncIterator, Callable, Optional

from fastapi.concurrency import run_in_threadpool

from noctusai_lib.domain.help_chat.router import PEDIDO_CONTINUACAO
from noctusai_lib.domain.help_chat.service import build_conversation_messages, sse_event
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
from app.modules.media_creation.prompts import chat_headline, chat_roteiro
from app.modules.media_creation.services.chat_contexto import (
    ChatContexto,
    ChatError,
    ContextoMontado,
    ReferenciaResolvida,
    eh_uuid,
)

logger = logging.getLogger(__name__)

CONVERSAS = "cs_chat_conversas"
MENSAGENS = "cs_chat_mensagens"
MEMORIAS = "cs_memorias"
MARCAS = "marcas"

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

#: ``(messages, *, model, provider, org_id, outcome) -> AsyncIterator[str]`` -- DI seam; tests inject
#: a fake that fills ``outcome`` (a ``StreamOutcome``) once drained.
ChatStreamFn = Callable[..., AsyncIterator[str]]

CONVERSA_COLS = "id,org_id,marca_id,user_id,agente,titulo,last_message_at"
MENSAGEM_COLS = "id,role,conteudo,referencias,status,truncada,created_at"


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
    return {k: r.get(k) for k in ("id", "marca_id", "agente", "titulo", "last_message_at")}


def mensagem_out(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"], "role": r["role"], "conteudo": r.get("conteudo") or "",
        "referencias": r.get("referencias") or [], "status": r.get("status") or "completa",
        "truncada": bool(r.get("truncada")), "created_at": r.get("created_at"),
    }


def _sistema(agente: str, montado: ContextoMontado) -> str:
    prompt = chat_headline.SYSTEM_PROMPT if agente == "headline" else chat_roteiro.SYSTEM_PROMPT
    return f"{prompt}\n\n{montado.texto}" if montado.texto else prompt


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


class ChatService:
    def __init__(self, db: Any, org_id: str, user_id: str) -> None:
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.contexto = ChatContexto(db, org_id, user_id, settings.chat_contexto_max_chars)

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

    def list_conversas(self, marca_id: str, agente: str, limit: int, offset: int) -> dict[str, Any]:
        self.assert_marca(marca_id)
        rows = (
            self.db.table(CONVERSAS).select(CONVERSA_COLS)
            .eq("org_id", self.org_id).eq("user_id", self.user_id)
            .eq("marca_id", marca_id).eq("agente", agente)
            .order("last_message_at", desc=True).range(offset, offset + limit).execute().data
        ) or []
        return {"items": [conversa_out(r) for r in rows[:limit]], "tem_mais": len(rows) > limit}

    def create_conversa(self, marca_id: str, agente: str, titulo: Optional[str]) -> dict[str, Any]:
        self.assert_marca(marca_id)
        agora = _iso(_agora())
        row = {
            "id": novo_id(), "org_id": self.org_id, "marca_id": marca_id, "user_id": self.user_id,
            "agente": agente, "titulo": titulo or TITULO_PADRAO, "last_message_at": agora,
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
        return {"items": [mensagem_out(r) for r in pagina], "tem_mais": len(rows) > limit}

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
        if len(user_msgs) >= settings.chat_mensagens_dia_usuario:
            raise ChatError(
                429, f"Você atingiu o limite de {settings.chat_mensagens_dia_usuario} mensagens por dia no chat.",
                code=ERRO_LIMITE,
                headers={"Retry-After": str(self._retry_after(user_msgs, settings.chat_mensagens_dia_usuario, agora))},
            )
        if len(org_msgs) >= settings.chat_mensagens_dia_org:
            raise ChatError(
                429, "A sua organização atingiu o limite diário de mensagens no chat.", code=ERRO_LIMITE,
                headers={"Retry-After": str(self._retry_after(org_msgs, settings.chat_mensagens_dia_org, agora))},
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
            montado = self.contexto.montar(conversa, resolvidas)
            refs_dict = [r.como_dict() for r in resolvidas]
            msg = self._gravar_mensagem(conversa_id, "user", conteudo, referencias=refs_dict)
            titulo = conteudo[:MAX_TITULO_AUTO].strip() if eh_primeira and conversa["titulo"] == TITULO_PADRAO else None
            self._tocar_conversa(conversa_id, titulo)
        except Exception:
            liberar_stream(self.user_id)
            raise
        return {"conversa": conversa, "historico": historico, "montado": montado,
                "msg_id": msg["id"], "refs": refs_dict}

    async def preparar_envio(
        self, conversa_id: str, conteudo: str, referencias: list[Any], stream_fn: ChatStreamFn
    ) -> Envio:
        prep = await run_in_threadpool(self._preparar_sync, conversa_id, conteudo, referencias)
        conversa = prep["conversa"]
        modelo = settings.geracao_llm_model
        sistema = _sistema(conversa["agente"], prep["montado"])
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
            primeira=primeira, rodada=agen, outcome=outcome, modelo=modelo,
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
                "codigos_permitidos": envio.contexto.codigos_permitidos,
            }})
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
            mensagem_id = await run_in_threadpool(self._salvar_resposta, envio, "".join(partes), "completa", truncada)
            if truncada:
                yield sse_event({"truncated": True})
            yield sse_event({"done": {"mensagem_id": mensagem_id}})
            logger.info(
                "chat: stream ok org=%s conversa=%s chars=%d continuacoes=%d truncated=%s latency_ms=%d",
                org_id, conversa["id"], len("".join(partes)), continuacoes, truncada,
                int((time.monotonic() - inicio) * 1000),
            )
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
    "ChatError", "ChatService", "ChatStreamFn", "ERRO_STREAM_EM_ANDAMENTO", "Envio", "TITULO_PADRAO",
    "conversa_out", "get_chat_stream_fn", "liberar_stream", "mensagem_out",
]
