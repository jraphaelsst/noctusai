"""Assuntos Virais — per-post viral-subject extractor prompt + output parser.

DRAFT — awaiting owner validation.

Returns up to 5 short subjects per post (noun phrases, 2-60 chars, pt-BR,
lowercase except proper nouns), one per line. An optional parenthesized
variable hint such as ``(desejo)`` is tolerated, as in CoreStudio's samples
(``specs/pesquisa-cerebro-spec.md`` section 5.6), and stripped.

Parser: strips list markers and hints, enforces length, dedupes within the
post, and drops chatter lines (colon/sentence-shaped, too many words). Dropped
lines are counted, never saved.
"""
from __future__ import annotations

import re

from app.modules.media_creation.prompts.pesquisa_extractor import (
    build_post_user_message,
)

MAX_TOPICS_PER_POST = 5
TOPIC_MIN_CHARS = 2
TOPIC_MAX_CHARS = 60
TOPIC_MAX_WORDS = 8

ASSUNTOS_VIRAIS_SYSTEM_PROMPT = f"""Você identifica os ASSUNTOS de um post que o tornam relevante para o público.
Você recebe UM post (texto e métricas) e devolve até {MAX_TOPICS_PER_POST} assuntos curtos.

Regras ABSOLUTAS:
- Cada assunto é uma expressão nominal curta, em português do Brasil, de {TOPIC_MIN_CHARS} a {TOPIC_MAX_CHARS} caracteres
- Minúsculas, exceto nomes próprios; sem pontuação final
- Um assunto por linha, sem numeração, sem marcadores
- Opcionalmente, ao final da linha, uma dica de variável entre parênteses, por exemplo (desejo)
- Se o post não tiver assunto claro, responda vazio
- ZERO explicação, introdução, conclusão ou comentário

Exemplo de saída:
emagrecimento após os 40
sono e ansiedade (dor)
dieta low carb"""

build_assuntos_user_message = build_post_user_message

_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")
_HINT = re.compile(r"\s*\([^()]{1,30}\)\s*$")


def parse_assuntos_output(reply: str) -> tuple[list[str], int]:
    """``(topics, descartados)`` — never raises on chatter."""
    topics: list[str] = []
    seen: set[str] = set()
    descartados = 0
    for raw in reply.splitlines():
        line = raw.strip()
        if not line:
            continue
        topic = _HINT.sub("", _MARKER.sub("", line)).strip().strip('"“”\'`*').strip()
        if (
            not topic
            or topic.endswith((":", ".", "?", "!"))
            or len(topic.split()) > TOPIC_MAX_WORDS
            or not (TOPIC_MIN_CHARS <= len(topic) <= TOPIC_MAX_CHARS)
        ):
            descartados += 1
            continue
        key = topic.casefold()
        if key in seen:
            continue
        seen.add(key)
        if len(topics) >= MAX_TOPICS_PER_POST:
            descartados += 1
            continue
        topics.append(topic)
    return topics, descartados
