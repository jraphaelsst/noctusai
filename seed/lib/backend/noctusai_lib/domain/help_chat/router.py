"""`create_help_chat_router(...)` — the help-chat organ's HTTP surface.

A factory (same shape as `noctusai_lib.domain.card_hub.card_hub_routers`)
because the seed cannot know the product's auth dependency or how to pull
an org id out of whatever that dependency returns. Both arrive as
parameters, so a product keeps its own DI seams and its tests keep
overriding them exactly as they do for every other seed-mounted router.

Mounts two routes:

    POST {prefix}/chat   (default prefix "/api/ajuda")
        body: {"messages": [{"role": "user"|"assistant", "content": str}, ...],
               "pagina_atual": str | None, "conversa_id": uuid | None}
        auth: `auth_dependency` (401 on missing/invalid auth)
        response: `text/event-stream` — SSE frames
            data: {"delta": "..."}          (one per streamed chunk)
            data: {"truncated": true}        (reply still cut off after every
                                              continuation round; precedes done)
            data: {"encerrado": true}        (the model judged the attendance
                                              concluded; ONLY on a clean
                                              completion, never alongside an
                                              `error`; precedes done)
            data: {"done": true}             (terminal, success)
            data: {"error": {"code", "message"}}   (terminal, mid-stream failure)

    POST {prefix}/avaliacao   -> 204
        body: {"conversa_id": uuid, "nota": 1..5, "comentario": str<=1000 | None,
               "motivo": "concluido" | "inatividade"}
        auth: `auth_dependency`; 404 `conversa_nao_encontrada` when the id is not
        the caller's own conversation. Upsert: the last rating wins.

Conversations are STORED (full text, via the injected `HelpChatStore`; read
only by the platform team — see `store.py`). A store failure never breaks the
answer: it is logged at ERROR with org/conversa ids and the stream goes on.

Two distinct failure surfaces, because SSE cannot change its HTTP status
once the first byte is sent:

  - A failure BEFORE the first chunk (bad API key, budget exhausted, the
    provider refusing at connect time) is caught before the
    `StreamingResponse` is even constructed, so it answers with a REAL
    HTTP status: 503 `ia_nao_configurada`, 429 `orcamento_ia_excedido`,
    502 `ia_indisponivel`. This is done by "priming" the async generator —
    pulling its first chunk inside the route handler, before wrapping it in
    a `StreamingResponse` — since `chat_completion_stream`'s docstring says
    it raises "at stream open", i.e. on the first `__anext__()`.
  - A failure AFTER streaming has started (the one shape that cannot become
    an HTTP status any more) is emitted as an in-band SSE `error` event —
    the frontend organ treats any `error` event as terminal.

Never LOGS message content — only ids/sizes/latency/usage (the text lives in
the store, not in log lines).
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Callable, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse

from noctusai_lib.integrations.llm import (
    LLMAPIError,
    LLMBudgetExceeded,
    LLMNotConfigured,
    StreamOutcome,
    chat_completion_stream,
)

from .schemas import HelpChatAvaliacaoRequest, HelpChatRequest
from .service import (
    ERROR_IA_INDISPONIVEL,
    ERROR_IA_NAO_CONFIGURADA,
    ERROR_ORCAMENTO_IA_EXCEDIDO,
    HelpChatRateLimiter,
    KnowledgePath,
    MarcadorFilter,
    build_conversation_messages,
    build_system_prompt,
    load_knowledge,
    rate_limit_error_body,
    sse_event,
)
from .store import HelpChatStore

logger = logging.getLogger(__name__)

#: `(messages, *, model, provider, org_id, outcome) -> AsyncIterator[str]` —
#: what the router calls to get streamed text deltas; it must fill `outcome`
#: (a `StreamOutcome`) once drained. Defaults to the seed's
#: `chat_completion_stream`; tests inject a `FakeProvider`-backed callable.
HelpChatStreamFn = Callable[..., AsyncIterator[str]]

#: Output cap PER ROUND. A how-to answer for a whole product flow routinely
#: exceeds the old 1200 (measured live 2026-10-01: an orçamento walkthrough cut
#: off mid-section). Long answers that still exceed it are continued
#: (`max_continuations`), not cut.
MAX_TOKENS_POR_RODADA = 4096

#: The follow-up turn that asks the model to resume a reply it was cut off in.
#: Never shown to the user and never persisted — it exists for one request.
PEDIDO_CONTINUACAO = (
    "Sua resposta anterior foi interrompida pelo limite de tamanho. Continue "
    "exatamente do ponto onde parou — sem repetir nada, sem introdução e sem "
    "comentar a interrupção."
)


def _default_stream_fn(
    messages: list[dict],
    *,
    model: str,
    provider: str,
    org_id: Optional[str],
    outcome: StreamOutcome,
) -> AsyncIterator[str]:
    return chat_completion_stream(
        messages,
        model=model,
        provider=provider,
        org_id=org_id,
        temperature=0.4,
        max_tokens=MAX_TOKENS_POR_RODADA,
        outcome=outcome,
    )


def _falha(status: int, code: str, mensagem: str) -> HTTPException:
    """Same error envelope as `products/igig/backend/app/routers/
    assistente_router.py` — `{"detail": ..., "code": ...}` — the reference
    consumer pattern this organ formalizes."""
    return HTTPException(status_code=status, detail={"detail": mensagem, "code": code})


def create_help_chat_router(
    *,
    product_name: str,
    product_slug: str,
    knowledge_path: KnowledgePath,
    store: HelpChatStore,
    auth_dependency: Callable[..., Any],
    org_id_from_auth: Callable[[Any], str],
    user_id_from_auth: Optional[Callable[[Any], str]] = None,
    model: str = "claude-haiku-4-5",
    provider: str = "anthropic",
    max_turns: int = 20,
    max_chars_per_message: int = 4000,
    max_continuations: int = 2,
    rate_limit: int = 20,
    prefix: str = "/api/ajuda",
    tags: Optional[list[str]] = None,
    stream_fn: HelpChatStreamFn = _default_stream_fn,
    rate_limiter: Optional[HelpChatRateLimiter] = None,
) -> APIRouter:
    """Build the help-chat router. Mount it like any other product router:

        from noctusai_lib.domain.help_chat import create_help_chat_router

        app.include_router(create_help_chat_router(
            product_name="IgIg",
            knowledge_path=Path(__file__).parent / "help_chat_knowledge.md",
            auth_dependency=get_current_user_org,
            org_id_from_auth=lambda auth: str(coerce_org_uuid(auth[2])),
        ))

    Args:
        product_slug: Stored in `help_chat_conversas.produto` (the organ's
            tables are product-agnostic) - e.g. "igig".
        store: Conversation storage seam (`make_help_chat_store(client_fn=...)`
            in production, `FakeHelpChatStore()` in tests). Required: a help
            chat that silently stores nothing would break the platform
            team's ability to review it.
        product_name: Shown to the model in the behavioural preamble
            ("Você é o assistente especialista do {product_name}").
        knowledge_path: A `Path` to a markdown file, or a zero-arg callable
            returning the knowledge text. Loaded ONCE, right here, at
            router-construction time (i.e. at product startup, since
            products build their routers at import/startup time) —
            `HelpChatKnowledgeMissing` propagates and fails app startup
            loudly if the file is missing or empty. No silent empty
            knowledge.
        auth_dependency: The product's FastAPI auth dependency — same
            seam as `card_hub_routers`. Whatever it returns is passed to
            `org_id_from_auth` (and `user_id_from_auth`).
        org_id_from_auth: `(auth_value) -> org_id str`.
        user_id_from_auth: `(auth_value) -> user_id str`, used to key the
            per-user rate limit. Defaults to `org_id_from_auth` (per-org
            limiting) when omitted — still a real limit, just coarser.
        model / provider: Passed to `stream_fn`. Default model is Haiku —
            cheap/fast, conversation-optimized; a product with a more
            demanding assistant can override.
        max_turns: Maximum number of messages accepted in one request body
            (422 above this — the client is expected to trim its own
            history before sending).
        max_chars_per_message: Per-message content length cap (422 above
            this).
        max_continuations: When the provider reports the reply was cut off
            at the per-round token cap, the router asks the model to
            continue (up to this many extra rounds) and streams the rest as
            ordinary `delta` frames — the client sees one unbroken answer.
            Still cut off after the last round ⇒ a `{"truncated": true}`
            frame before `done`, never a silent "complete" (`0` disables
            continuation; truncation is then reported immediately).
        rate_limit: Requests per minute per user (429 above this, pt-BR
            message, `code="limite_de_mensagens"`).
        prefix: Router prefix. Default `/api/ajuda` mounts
            `POST /api/ajuda/chat`.
        stream_fn / rate_limiter: Test seams — override with a
            `FakeProvider`-backed callable / a limiter with a tiny budget.
    """
    knowledge = load_knowledge(knowledge_path)
    system_prompt = build_system_prompt(product_name=product_name, knowledge=knowledge)
    limiter = rate_limiter or HelpChatRateLimiter(max_requests=rate_limit, window_seconds=60.0)
    resolve_user_key = user_id_from_auth or org_id_from_auth

    async def guardar(operacao: Callable[[], Any], descricao: str, org_id: str, conversa_id: str) -> bool:
        """Run a store call off the event loop. NEVER raises: a store outage
        must not break the user's answer, but it is logged at ERROR (ids and
        exception class only - never message text)."""
        try:
            await run_in_threadpool(operacao)
            return True
        except Exception as exc:
            logger.error(
                "help_chat: falha ao armazenar %s org=%s conversa=%s (%s)",
                descricao, org_id, conversa_id, type(exc).__name__,
            )
            return False

    router = APIRouter(prefix=prefix, tags=tags or ["help_chat"])

    @router.post("/chat")
    async def help_chat(
        payload: HelpChatRequest,
        auth: Any = Depends(auth_dependency),
    ) -> StreamingResponse:
        org_id = org_id_from_auth(auth)
        user_key = resolve_user_key(auth)

        if not limiter.allow(user_key):
            raise HTTPException(status_code=429, detail=rate_limit_error_body())

        if not payload.messages:
            raise HTTPException(
                status_code=422,
                detail={"detail": "A conversa precisa ter pelo menos uma mensagem.", "code": "mensagens_vazias"},
            )
        if len(payload.messages) > max_turns:
            raise HTTPException(
                status_code=422,
                detail={
                    "detail": f"Esta conversa já tem mensagens demais (máximo {max_turns}). Inicie uma nova conversa.",
                    "code": "limite_de_turnos",
                },
            )
        if payload.messages[-1].role != "user":
            raise HTTPException(
                status_code=422,
                detail={"detail": "A última mensagem precisa ser do usuário.", "code": "ultima_mensagem_invalida"},
            )
        for msg in payload.messages:
            if len(msg.content) > max_chars_per_message:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "detail": f"Mensagem muito longa (máximo {max_chars_per_message} caracteres).",
                        "code": "mensagem_muito_longa",
                    },
                )

        conversa_id = str(payload.conversa_id or uuid4())
        guardando = await guardar(
            lambda: store.registrar_turno_usuario(
                conversa_id=conversa_id,
                produto=product_slug,
                org_id=org_id,
                user_id=user_id_from_auth(auth) if user_id_from_auth else None,
                conteudo=payload.messages[-1].content,
                pagina_atual=payload.pagina_atual,
            ),
            "turno do usuário", org_id, conversa_id,
        )

        history = [{"role": m.role, "content": m.content} for m in payload.messages]
        messages = build_conversation_messages(
            system_prompt=system_prompt, history=history, provider=provider
        )

        started = time.monotonic()
        outcome = StreamOutcome()
        agen = stream_fn(messages, model=model, provider=provider, org_id=org_id, outcome=outcome)
        try:
            first_chunk = await agen.__anext__()
        except StopAsyncIteration:
            first_chunk = None
        except LLMNotConfigured as exc:
            logger.warning("help_chat: IA não configurada org=%s", org_id)
            raise _falha(503, ERROR_IA_NAO_CONFIGURADA,
                         "A IA não está configurada (chave da Anthropic ausente).") from exc
        except LLMBudgetExceeded as exc:
            logger.warning("help_chat: orçamento de IA excedido org=%s", org_id)
            raise _falha(429, ERROR_ORCAMENTO_IA_EXCEDIDO,
                         "O limite de uso de IA da organização foi atingido.") from exc
        except LLMAPIError as exc:
            logger.error("help_chat: provedor de IA falhou org=%s", org_id)
            raise _falha(502, ERROR_IA_INDISPONIVEL,
                         "O provedor de IA não respondeu. Tente novamente em instantes.") from exc

        async def event_stream() -> AsyncIterator[str]:
            nonlocal outcome
            chunk_count = 0
            # The raw reply so far - held in memory for this request only (to
            # replay it to the model on a continuation round). `filtro` holds
            # the marker-free text that is streamed and stored.
            bruto: list[str] = []
            filtro = MarcadorFilter()
            continuacoes = 0
            salvo = False

            def salvar(parcial: bool) -> None:
                """Persist the reply (sync; also used from `finally`)."""
                nonlocal salvo
                if not guardando or salvo:
                    return
                salvo = True
                texto = filtro.texto_final()
                if not texto:
                    return
                try:
                    store.registrar_resposta(
                        conversa_id=conversa_id, conteudo=texto, modelo=model,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        truncated=outcome.truncated, parcial=parcial,
                    )
                except Exception as exc:
                    logger.error(
                        "help_chat: falha ao armazenar resposta org=%s conversa=%s (%s)",
                        org_id, conversa_id, type(exc).__name__,
                    )

            async def salvar_parcial() -> None:
                filtro.flush()
                await run_in_threadpool(salvar, True)

            try:
                if first_chunk is not None:
                    chunk_count += 1
                    bruto.append(first_chunk)
                    saida = filtro.feed(first_chunk)
                    if saida:
                        yield sse_event({"delta": saida})
                rodada = agen
                while True:
                    async for chunk in rodada:
                        chunk_count += 1
                        bruto.append(chunk)
                        saida = filtro.feed(chunk)
                        if saida:
                            yield sse_event({"delta": saida})
                    texto = "".join(bruto)
                    if not outcome.truncated or continuacoes >= max_continuations or not texto.strip():
                        break
                    continuacoes += 1
                    continuacao = build_conversation_messages(
                        system_prompt=system_prompt,
                        history=history + [
                            {"role": "assistant", "content": texto},
                            {"role": "user", "content": PEDIDO_CONTINUACAO},
                        ],
                        provider=provider,
                    )
                    outcome = StreamOutcome()
                    rodada = stream_fn(
                        continuacao, model=model, provider=provider, org_id=org_id, outcome=outcome
                    )
                resto = filtro.flush()
                if resto:
                    yield sse_event({"delta": resto})
                await run_in_threadpool(salvar, False)
                if outcome.truncated:
                    yield sse_event({"truncated": True})
                if filtro.encontrado:
                    yield sse_event({"encerrado": True})
                yield sse_event({"done": True})
                logger.info(
                    "help_chat: stream ok org=%s conversa=%s chunks=%d chars=%d continuations=%d "
                    "truncated=%s encerrado=%s latency_ms=%d",
                    org_id, conversa_id, chunk_count, len(filtro.texto_final()), continuacoes,
                    outcome.truncated, filtro.encontrado, int((time.monotonic() - started) * 1000),
                )
            except LLMNotConfigured:
                logger.warning("help_chat: IA não configurada mid-stream org=%s", org_id)
                await salvar_parcial()
                yield sse_event({"error": {"code": ERROR_IA_NAO_CONFIGURADA,
                                            "message": "A IA não está configurada (chave da Anthropic ausente)."}})
            except LLMBudgetExceeded:
                logger.warning("help_chat: orçamento de IA excedido mid-stream org=%s", org_id)
                await salvar_parcial()
                yield sse_event({"error": {"code": ERROR_ORCAMENTO_IA_EXCEDIDO,
                                            "message": "O limite de uso de IA da organização foi atingido."}})
            except LLMAPIError:
                logger.error("help_chat: provedor de IA falhou mid-stream org=%s", org_id)
                await salvar_parcial()
                yield sse_event({"error": {"code": ERROR_IA_INDISPONIVEL,
                                            "message": "O provedor de IA não respondeu. Tente novamente em instantes."}})
            except Exception:
                # No silent errors: log loudly, still answer the client with
                # a typed SSE error frame instead of an opaque broken stream.
                logger.exception("help_chat: erro inesperado no streaming org=%s", org_id)
                await salvar_parcial()
                yield sse_event({"error": {"code": ERROR_IA_INDISPONIVEL,
                                            "message": "Ocorreu um erro inesperado. Tente novamente."}})
            finally:
                # Client disconnected (GeneratorExit/cancel) before any of the
                # paths above stored the reply: keep what was streamed.
                if not salvo:
                    filtro.flush()
                    salvar(True)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/avaliacao", status_code=204)
    async def avaliar_atendimento(
        payload: HelpChatAvaliacaoRequest,
        auth: Any = Depends(auth_dependency),
    ) -> Response:
        org_id = org_id_from_auth(auth)
        conversa_id = str(payload.conversa_id)
        user_id = user_id_from_auth(auth) if user_id_from_auth else None
        try:
            ok = await run_in_threadpool(
                lambda: store.avaliar(
                    conversa_id=conversa_id, org_id=org_id, user_id=user_id,
                    nota=payload.nota, comentario=payload.comentario, motivo=payload.motivo,
                )
            )
        except Exception as exc:
            logger.error(
                "help_chat: falha ao armazenar avaliação org=%s conversa=%s (%s)",
                org_id, conversa_id, type(exc).__name__,
            )
            raise _falha(503, "avaliacao_indisponivel",
                         "Não foi possível registrar sua avaliação agora. Tente novamente.") from exc
        if not ok:
            raise _falha(404, "conversa_nao_encontrada", "Conversa não encontrada.")
        return Response(status_code=204)

    return router


__all__ = ["HelpChatStreamFn", "create_help_chat_router"]
