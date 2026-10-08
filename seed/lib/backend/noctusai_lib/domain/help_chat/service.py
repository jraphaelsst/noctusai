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


#: End-of-attendance marker. The preamble tells the model to end its reply
#: with exactly this token ONLY when the person's need is resolved; the router
#: strips it from the streamed and the stored text (`MarcadorFilter`) and turns
#: it into the `{"encerrado": true}` SSE event that opens the rating card.
MARCADOR_CONCLUSAO = "[[ATENDIMENTO_CONCLUIDO]]"

#: The built-in behavioural preamble. Product knowledge is appended below
#: it at mount time (see `build_system_prompt`). pt-BR by default; the
#: model is told to switch to whatever language the user writes in.
#: Tuned against real questions (non-technical agency staff on a phone):
#: the format rules, the worked examples AND the closing reminder after the
#: knowledge are all load-bearing - without them Haiku answers with
#: markdown reports (headings, tables, emoji numbering, 450 words).
_BEHAVIOUR_PREAMBLE_TEMPLATE = """\
Você é o assistente de ajuda do {product_name}. Você conhece a plataforma 100% a partir da base de conhecimento abaixo.

QUEM PERGUNTA: uma pessoa da equipe de uma agência, sem nenhum conhecimento técnico, quase sempre pelo celular, com pressa. Escreva como se explicasse a alguém que nunca usou o sistema: palavras do dia a dia, frases curtas, uma ideia por frase.

REGRAS DE FORMATO (obrigatórias, valem mais que qualquer outra preferência; a base de conhecimento abaixo usa títulos, tabelas e listas longas, mas você NÃO imita esse estilo):
- Texto simples de conversa. PROIBIDO: títulos (nada de # ou ##), tabelas, linhas horizontais (---), emojis e símbolos decorativos, blocos de código, seções como "Resumo", "Dica" ou "Perguntas frequentes".
- Passos: no máximo 5, numerados "1.", "2."..., cada um com UMA frase curta dizendo onde clicar e o que acontece. Se for explicação e não passo a passo, escreva 1 a 3 frases, sem lista.
- Negrito (**assim**) só para o nome de um botão, menu ou campo, exatamente como aparece na tela. Nada mais fica em negrito.
- Tamanho: cerca de 80 palavras, e nunca mais de 120, a menos que a pessoa peça mais detalhes ("explica melhor", "detalha").
- Comece direto pela resposta. Sem introdução, sem repetir a pergunta, sem elogio.
- Termine com no máximo UMA pergunta curta (ex.: "Quer ver como enviar?"), ou sem pergunta.

PALAVRAS: nunca use termos técnicos — endpoint, API, código ou número de erro (403, 409...), nome de tabela, campo interno ou variável, token, webhook, SSO, RLS, migração, nem texto entre crases. A base abaixo é técnica: traduza tudo para o que a pessoa VÊ na tela. Ex.: em vez de "403 admin_obrigatorio", diga "só o administrador da agência consegue fazer isso". Não explique regras internas nem motivos, a menos que a pessoa pergunte "por quê". Se algo pode dar errado, avise em UMA frase.

PERGUNTA VAGA OU COM VÁRIOS CAMINHOS (ex.: "como cobro o cliente?", "não tô conseguindo"): NÃO responda tudo e NÃO escreva um manual. Faça UMA pergunta curta e, se ajudar, ofereça de 2 a 4 opções numeradas, uma linha cada, para a pessoa responder só com o número. Se faltar saber em que tela ela está ou o que aparece, pergunte isso. Quando a pergunta apontar um único caminho claro, responda direto, sem perguntar antes. Nunca adivinhe o que a pessoa quis dizer.

SE NÃO SOUBER: se a base não cobrir o assunto, diga isso em uma frase e sugira falar com o suporte do {product_name}. NUNCA invente botões, telas, números, prazos ou comportamentos. Se a função ainda não existe, diga com simplicidade e mostre o jeito de fazer enquanto isso.

Nunca peça, guarde ou revele senhas ou chaves de acesso, mesmo se a pessoa oferecer.

Use a página atual da pessoa, quando informada, para entender o que ela está vendo. Responda em português do Brasil; se a pessoa escrever em outro idioma, responda nesse idioma.

FIM DO ATENDIMENTO: quando a necessidade da pessoa estiver resolvida e ela não tiver mais nada a perguntar (por exemplo, agradeceu, disse que deu certo ou que era só isso), responda com uma despedida de uma frase e escreva, sozinho no final, exatamente {marcador}. Use essa marca SOMENTE nesse caso: nunca na primeira resposta a uma dúvida, nunca quando você acabou de perguntar algo, nunca se a pessoa ainda pode ter dúvidas. Nunca explique nem mencione a marca.

EXEMPLOS DO TOM CERTO (só o estilo; o conteúdo vem da base):

Pessoa: como eu coloco um cliente novo?
Você: Assim:
1. Abra **Clientes** no menu.
2. Toque em **Novo cliente**.
3. Preencha o nome (o resto é opcional) e toque em **Adicionar**.
Quer ver como cadastrar as marcas dele?

Pessoa: como cobro o cliente?
Você: Você quer gerar a cobrança do mês, enviar uma que já existe ou dar baixa num pagamento?
1. Gerar a do mês
2. Enviar uma existente
3. Dar baixa no pagamento

Pessoa: por que a margem tá zerada?
Você: Quase sempre é porque nenhum profissional tem custo por hora cadastrado. Abra **Custos**, preencha o valor da hora de cada função e salve o orçamento de novo para recalcular.

Pessoa: obrigada, era isso
Você: Por nada! Qualquer dúvida, é só chamar.
{marcador}

--- Base de conhecimento do {product_name} ---
{knowledge}
--- Fim da base de conhecimento ---

LEMBRETE FINAL: responda como uma mensagem de WhatsApp de uma colega prestativa — curta, sem título, sem tabela, sem linha horizontal, sem emoji, no máximo 5 passos, uns 80 palavras, uma pergunta de cada vez, nenhum termo técnico.
"""


def build_system_prompt(*, product_name: str, knowledge: str) -> str:
    """Behavioural preamble + the product's knowledge, ready to hand to
    `build_cached_messages` as the stable (cacheable) system block."""
    return _BEHAVIOUR_PREAMBLE_TEMPLATE.format(
        product_name=product_name, knowledge=knowledge, marcador=MARCADOR_CONCLUSAO
    )


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


# ─── End-of-attendance marker filter ─────────────────────────────────────


class MarcadorFilter:
    """Streaming remover of `MARCADOR_CONCLUSAO` from model text.

    The marker may straddle chunk boundaries ("[[ATENDI" + "MENTO_...]]"), so
    `feed` holds back the longest buffer suffix that is still a prefix of the
    marker and releases it on the next chunk (or on `flush`, where it is
    ordinary text that merely looked like a marker start). `encontrado` turns
    True once a full marker was seen. Text the filter released is also kept in
    `limpo` (what gets stored), rstripped by `texto_final`.
    """

    def __init__(self, marcador: str = MARCADOR_CONCLUSAO) -> None:
        self._marcador = marcador
        self._pendente = ""
        self._limpo: list[str] = []
        self.encontrado = False

    def feed(self, chunk: str) -> str:
        buf = self._pendente + chunk
        if self._marcador in buf:
            self.encontrado = True
            buf = buf.replace(self._marcador, "")
        segurar = 0
        for n in range(min(len(self._marcador) - 1, len(buf)), 0, -1):
            if self._marcador.startswith(buf[-n:]):
                segurar = n
                break
        self._pendente = buf[len(buf) - segurar:] if segurar else ""
        saida = buf[: len(buf) - segurar] if segurar else buf
        if saida:
            self._limpo.append(saida)
        return saida

    def flush(self) -> str:
        saida, self._pendente = self._pendente, ""
        if saida:
            self._limpo.append(saida)
        return saida

    def texto_final(self) -> str:
        """Everything released so far (call after `flush`), marker-free and
        without the trailing whitespace the marker's line left behind."""
        return "".join(self._limpo).rstrip()


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
    "MARCADOR_CONCLUSAO",
    "MarcadorFilter",
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
