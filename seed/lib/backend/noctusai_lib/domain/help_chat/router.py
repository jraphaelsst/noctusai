"""`create_help_chat_router(...)` — the help-chat organ's HTTP surface.

A factory (same shape as `noctusai_lib.domain.card_hub.card_hub_routers`)
because the seed cannot know the product's auth dependency or how to pull
an org id out of whatever that dependency returns. Both arrive as
parameters, so a product keeps its own DI seams and its tests keep
overriding them exactly as they do for every other seed-mounted router.

Mounts a single route:

    POST {prefix}/chat   (default prefix "/api/ajuda")
        body: {"messages": [{"role": "user"|"assistant", "content": str}, ...],
               "pagina_atual": str | None}
        auth: `auth_dependency` (401 on missing/invalid auth)
        response: `text/event-stream` — SSE frames
            data: {"delta": "..."}          (one per streamed chunk)
            data: {"done": true}             (terminal, success)
            data: {"error": {"code", "message"}}   (terminal, mid-stream failure)

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

Never logs message content — only sizes/latency/usage (LGPD: this route
must not persist or leak what a signed-in user asked their product's AI).
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from noctusai_lib.integrations.llm import (
    LLMAPIError,
    LLMBudgetExceeded,
    LLMNotConfigured,
    chat_completion_stream,
)

from .schemas import HelpChatRequest
from .service import (
    ERROR_IA_INDISPONIVEL,
    ERROR_IA_NAO_CONFIGURADA,
    ERROR_ORCAMENTO_IA_EXCEDIDO,
    HelpChatRateLimiter,
    KnowledgePath,
    build_conversation_messages,
    build_system_prompt,
    load_knowledge,
    rate_limit_error_body,
    sse_event,
)

logger = logging.getLogger(__name__)

#: `(messages, *, model, provider, org_id) -> AsyncIterator[str]` — what the
#: router calls to get streamed text deltas. Defaults to the seed's
#: `chat_completion_stream`; tests inject a `FakeProvider`-backed callable.
HelpChatStreamFn = Callable[..., AsyncIterator[str]]


def _default_stream_fn(
    messages: list[dict], *, model: str, provider: str, org_id: Optional[str]
) -> AsyncIterator[str]:
    return chat_completion_stream(
        messages,
        model=model,
        provider=provider,
        org_id=org_id,
        temperature=0.4,
        max_tokens=1200,
    )


def _falha(status: int, code: str, mensagem: str) -> HTTPException:
    """Same error envelope as `products/igig/backend/app/routers/
    assistente_router.py` — `{"detail": ..., "code": ...}` — the reference
    consumer pattern this organ formalizes."""
    return HTTPException(status_code=status, detail={"detail": mensagem, "code": code})


def create_help_chat_router(
    *,
    product_name: str,
    knowledge_path: KnowledgePath,
    auth_dependency: Callable[..., Any],
    org_id_from_auth: Callable[[Any], str],
    user_id_from_auth: Optional[Callable[[Any], str]] = None,
    model: str = "claude-haiku-4-5",
    provider: str = "anthropic",
    max_turns: int = 20,
    max_chars_per_message: int = 4000,
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

        history = [{"role": m.role, "content": m.content} for m in payload.messages]
        messages = build_conversation_messages(
            system_prompt=system_prompt, history=history, provider=provider
        )

        started = time.monotonic()
        agen = stream_fn(messages, model=model, provider=provider, org_id=org_id)
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
            chunk_count = 0
            char_count = 0
            try:
                if first_chunk is not None:
                    chunk_count += 1
                    char_count += len(first_chunk)
                    yield sse_event({"delta": first_chunk})
                async for chunk in agen:
                    chunk_count += 1
                    char_count += len(chunk)
                    yield sse_event({"delta": chunk})
                yield sse_event({"done": True})
                logger.info(
                    "help_chat: stream ok org=%s chunks=%d chars=%d latency_ms=%d",
                    org_id, chunk_count, char_count, int((time.monotonic() - started) * 1000),
                )
            except LLMNotConfigured:
                logger.warning("help_chat: IA não configurada mid-stream org=%s", org_id)
                yield sse_event({"error": {"code": ERROR_IA_NAO_CONFIGURADA,
                                            "message": "A IA não está configurada (chave da Anthropic ausente)."}})
            except LLMBudgetExceeded:
                logger.warning("help_chat: orçamento de IA excedido mid-stream org=%s", org_id)
                yield sse_event({"error": {"code": ERROR_ORCAMENTO_IA_EXCEDIDO,
                                            "message": "O limite de uso de IA da organização foi atingido."}})
            except LLMAPIError:
                logger.error("help_chat: provedor de IA falhou mid-stream org=%s", org_id)
                yield sse_event({"error": {"code": ERROR_IA_INDISPONIVEL,
                                            "message": "O provedor de IA não respondeu. Tente novamente em instantes."}})
            except Exception:
                # No silent errors: log loudly, still answer the client with
                # a typed SSE error frame instead of an opaque broken stream.
                logger.exception("help_chat: erro inesperado no streaming org=%s", org_id)
                yield sse_event({"error": {"code": ERROR_IA_INDISPONIVEL,
                                            "message": "Ocorreu um erro inesperado. Tente novamente."}})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return router


__all__ = ["HelpChatStreamFn", "create_help_chat_router"]
