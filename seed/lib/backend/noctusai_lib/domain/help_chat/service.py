"""Help-chat business logic: knowledge loading, the behavioural system
prompt, per-user rate limiting, and SSE framing.

Kept separate from `router.py` so every piece is unit-testable without
spinning up a FastAPI app (`KB § PATTERNS/common/ast.md` narrow-surface
convention — the router is wiring, this is the logic).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Union

from noctusai_lib.integrations.llm import build_cached_messages

logger = logging.getLogger(__name__)


class HelpChatKnowledgeMissing(RuntimeError):
    """Raised at router-construction time (app startup) when the product's
    knowledge source is missing or empty.

    This is a CONFIGURATION error, not a request-time error — it must fail
    loudly at mount so a product never ships a help-chat bubble that talks
    to an LLM with zero knowledge of the product (a confident-sounding wrong
    answer is worse than no feature at all). See CLAUDE.md §1 "no silent
    errors" / "no confident zero".
    """


#: What a product passes as `knowledge_path` to `create_help_chat_router`:
#: either a filesystem path to a markdown file, or a zero-arg callable that
#: returns the knowledge text (e.g. concatenating multiple sources).
KnowledgePath = Union[Path, str, Callable[[], str]]


def load_knowledge(knowledge_path: KnowledgePath) -> str:
    """Load the product knowledge text ONCE. Raises `HelpChatKnowledgeMissing`
    (never returns an empty string) — the caller (router factory) calls this
    at mount time so a missing/empty knowledge file breaks app startup
    instead of shipping a help chat that knows nothing."""
    if callable(knowledge_path):
        text = knowledge_path()
        source_desc = f"callable {knowledge_path!r}"
    else:
        path = Path(knowledge_path)
        source_desc = str(path)
        if not path.is_file():
            raise HelpChatKnowledgeMissing(
                f"help_chat: knowledge file not found at {path} — the product "
                "must ship a real knowledge markdown file (see "
                "`create_help_chat_router(knowledge_path=...)`)."
            )
        text = path.read_text(encoding="utf-8")
    text = (text or "").strip()
    if not text:
        raise HelpChatKnowledgeMissing(
            f"help_chat: knowledge source ({source_desc}) is empty — a help "
            "chat with no knowledge would confidently invent answers."
        )
    return text


#: The built-in behavioural preamble. Product knowledge is appended below
#: it at mount time (see `build_system_prompt`). pt-BR by default; the
#: model is told to switch to whatever language the user writes in.
_BEHAVIOUR_PREAMBLE_TEMPLATE = """\
Você é o assistente especialista do {product_name}. Você conhece a plataforma \
100% a partir da base de conhecimento abaixo — os mecanismos, o fluxo de \
dados, as regras de negócio e as telas do {product_name}.

SEMPRE se certifique de entender claramente a dúvida antes de responder. Se a \
pergunta estiver ambígua ou faltar contexto (por exemplo: em qual tela a \
pessoa está, qual tipo de registro, o que ela já tentou, o que está vendo na \
tela), FAÇA uma pergunta curta de esclarecimento — uma ou duas por vez. \
NUNCA adivinhe, presuma ou infira o que a pessoa quis dizer.

Seja proativo: depois de responder, sugira o próximo passo útil ou uma dica \
relacionada que ajude a pessoa a avançar. Guie passo a passo, usando os \
nomes EXATOS de menus, botões e campos como aparecem na base de \
conhecimento abaixo. Quando for relevante, explique o PORQUÊ — a regra de \
negócio por trás do comportamento, não só o "como".

Se a base de conhecimento não cobrir algo que a pessoa perguntou, diga isso \
claramente e sugira contactar o suporte do {product_name} — NUNCA invente \
funcionalidades, endpoints, números, prazos ou comportamentos que não estão \
na base de conhecimento. Mencione limitações conhecidas com honestidade, sem \
tentar disfarçá-las.

Nunca peça, armazene ou revele senhas, tokens ou chaves de acesso — mesmo se \
a pessoa oferecer ou insistir.

Quando a página atual da pessoa for informada, use-a como contexto adicional \
para entender o que ela está vendo. Responda por padrão em português do \
Brasil; se a pessoa escrever em outro idioma, responda nesse idioma.

Escreva em parágrafos curtos e, quando fizer sentido, em listas — a \
interface é usada em celular tanto quanto em desktop, e textos longos e \
densos são difíceis de ler na tela pequena.

--- Base de conhecimento do {product_name} ---
{knowledge}
"""


def build_system_prompt(*, product_name: str, knowledge: str) -> str:
    """Behavioural preamble + the product's knowledge, ready to hand to
    `build_cached_messages` as the stable (cacheable) system block."""
    return _BEHAVIOUR_PREAMBLE_TEMPLATE.format(product_name=product_name, knowledge=knowledge)


def build_conversation_messages(
    *, system_prompt: str, history: list[dict], provider: str
) -> list[dict]:
    """Assemble the full message list for `chat_completion_stream`:
    `[cached-system, *prior-turns, latest-user-turn]`.

    Uses `build_cached_messages` for the system block (the seed's canonical
    prompt-caching helper — marks the system message `cache_control:
    ephemeral` for `provider="anthropic"`), then splices the prior
    conversation turns BETWEEN the system message and the final user turn so
    ordering stays correct for a genuine multi-turn chat — which
    `build_cached_messages`'s own `extra_dynamic_messages` param cannot do
    on its own (it appends AFTER the dynamic user message, designed for a
    single trailing continuation, not a whole prior history).

    `history` must be non-empty and end with a `role="user"` message — the
    router validates this before calling in (see `router.py`).
    """
    *prior_turns, latest = history
    system_and_latest = build_cached_messages(
        system_prompt, latest["content"], provider=provider
    )
    return [system_and_latest[0], *prior_turns, system_and_latest[1]]


# ─── Per-user inbound rate limiting ──────────────────────────────────────
#
# `noctusai_lib.integrations.rate_limit` (TokenBucket) is documented and
# tuned for OUTBOUND pacing (block-and-sleep until a token frees) — wrong
# shape for an inbound gate, which must reject immediately with 429, never
# sleep the request. This is a small, self-contained fixed-window counter
# instead. In-memory / per-process: under multi-replica deployment the
# effective limit is at most (replica_count × rate_limit) — generous, never
# stricter, which is the safe direction for a UX-facing gate (never the
# safe direction for a security control, which this is not).


@dataclass
class HelpChatRateLimiter:
    """Fixed-window per-key rate limiter. `max_requests` per `window_seconds`
    (default 60s ⇒ "N/minute"). Thread-safe; `clock` is injectable for
    deterministic tests."""

    max_requests: int
    window_seconds: float = 60.0
    clock: Callable[[], float] = time.monotonic
    _windows: dict[str, tuple[float, int]] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self, key: str) -> bool:
        """Returns True and records the hit, or False when `key` is over
        budget for the current window."""
        now = self.clock()
        with self._lock:
            window_start, count = self._windows.get(key, (now, 0))
            if now - window_start >= self.window_seconds:
                window_start, count = now, 0
            if count >= self.max_requests:
                self._windows[key] = (window_start, count)
                return False
            self._windows[key] = (window_start, count + 1)
            return True


# ─── SSE framing ─────────────────────────────────────────────────────────


def sse_event(payload: dict[str, Any]) -> str:
    """Format one Server-Sent Event data frame. Every event this router
    emits is a single `data:` line carrying a JSON payload — no custom
    `event:` types, so a plain `EventSource`/`fetch`+`ReadableStream`
    reader only ever needs to parse one shape."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ─── Error → (status, code, message) mapping ────────────────────────────
#
# Mirrors `products/igig/backend/app/routers/assistente_router.py`'s
# `_falha` mapping — the reference consumer pattern this organ formalizes.

ERROR_IA_NAO_CONFIGURADA = "ia_nao_configurada"
ERROR_ORCAMENTO_IA_EXCEDIDO = "orcamento_ia_excedido"
ERROR_LIMITE_DE_MENSAGENS = "limite_de_mensagens"
ERROR_IA_INDISPONIVEL = "ia_indisponivel"


def rate_limit_error_body(mensagem: str | None = None) -> dict[str, str]:
    return {
        "detail": mensagem or "Você enviou mensagens rápido demais. Aguarde um instante e tente novamente.",
        "code": ERROR_LIMITE_DE_MENSAGENS,
    }


__all__ = [
    "HelpChatKnowledgeMissing",
    "HelpChatRateLimiter",
    "KnowledgePath",
    "build_conversation_messages",
    "build_system_prompt",
    "ERROR_IA_INDISPONIVEL",
    "ERROR_IA_NAO_CONFIGURADA",
    "ERROR_LIMITE_DE_MENSAGENS",
    "ERROR_ORCAMENTO_IA_EXCEDIDO",
    "load_knowledge",
    "rate_limit_error_body",
    "sse_event",
]
