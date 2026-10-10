"""Extrair Pesquisa — per-post research-item extractor prompt + output parser.

DRAFT — awaiting owner validation.

An extraction is an LLM reading ONE post (text + metrics) and proposing
research items per variable. Same ``{{SLUG}}`` / ``[conteúdo]`` pair output as
the classifier, with one extra hard rule: every item is a LITERAL span of the
post text (CoreStudio's extractor is literal in 641 of 643 cases,
``specs/mechanisms.md`` section 4). The variables table is the classifier's own
rendering of ``pesquisa_variables.CLASSIFIABLE`` (reused, never duplicated).

Parser contract (pesquisa-wave2-contract.md section 3.2): classifiable slugs
only; content 1..500 chars; content must be a substring of the post text after
normalization (casefold, collapsed whitespace, edge punctuation stripped);
everything else — unknown slug, non-literal span, over-long span, chatter,
pairs past the cap — is discarded and COUNTED, never saved.
"""
from __future__ import annotations

import re
from typing import Any

from app.modules.media_creation.pesquisa_variables import CLASSIFIABLE_SLUGS
from app.modules.media_creation.prompts.pesquisa_classifier import VARIABLES_TABLE

MAX_PAIRS_PER_POST = 15
CONTENT_MAX_CHARS = 500

PESQUISA_EXTRACTOR_SYSTEM_PROMPT = f"""Você é um extrator de pesquisa de avatar para copywriting.
Você recebe UM post (texto e métricas) e extrai dele itens de pesquisa do avatar, classificados por variável.

Variáveis disponíveis:
Variável | O que é
{VARIABLES_TABLE}

Regras ABSOLUTAS:
- Extraia SOMENTE trechos LITERAIS do texto do post: copie as palavras exatamente como estão escritas, sem reescrever, resumir, traduzir ou corrigir
- Cada trecho é curto (uma frase ou expressão, no máximo 500 caracteres) e tem sentido sozinho
- No máximo {MAX_PAIRS_PER_POST} itens por post; escolha os mais relevantes
- Use apenas variáveis da tabela; nunca invente variáveis
- Se o post não trouxer nada aproveitável, responda vazio
- A resposta contém SOMENTE os pares variável/conteúdo, sem explicação, introdução, conclusão ou comentário

Formato de saída (ÚNICO permitido):
{{{{VARIAVEL}}}}
[trecho literal do post]

{{{{VARIAVEL}}}}
[trecho literal do post]

Uma linha em branco separa cada par. Se incluir QUALQUER texto além dos pares, a resposta está ERRADA."""

_PLATAFORMAS = {
    "instagram_media": "Instagram",
    "youtube_video": "YouTube",
    "mc_post": "Post criado",
}


def _fmt(v: Any) -> str:
    return "—" if v is None else str(v)


def build_post_user_message(post: Any) -> str:
    """Metrics header + the post text (shared by both extractors).

    ``post`` is a ``pesquisa_fontes.PostFonte`` (duck-typed). A metric the
    platform did not report prints "—", never 0.
    """
    published = (post.published_at or "")[:10] or "—"
    header = (
        f"Plataforma: {_PLATAFORMAS.get(post.kind, post.kind)} · Publicado em: {published} · "
        f"Views: {_fmt(post.plays)} · Likes: {_fmt(post.likes)} · Comentários: {_fmt(post.comments)}"
    )
    return f"{header}\n\nTexto do post:\n{post.texto}"


build_extractor_user_message = build_post_user_message

_SLUG_LINE = re.compile(r"^\s*\{\{\s*([A-Za-z0-9_-]+)\s*\}\}\s*$")
_EDGE_PUNCT = " \t\r\n.,;:!?…\"'“”‘’()[]{}-–—*_`"


def normalize(s: str) -> str:
    """casefold, collapse whitespace, strip edge punctuation."""
    return re.sub(r"\s+", " ", s.casefold()).strip(_EDGE_PUNCT)


def _unwrap(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    return s


def truncate_headline(texto: str, content: str) -> str:
    """CoreStudio ``truncateHeadline``: the source sentence of ``content``.

    Cut left at the last ``.?!`` before the match; cut right at the first
    ``.?!`` after ``max(matchEnd, leftCut + 30)`` (punctuation kept). A span
    that cannot be located verbatim falls back to a whitespace-flexible match,
    then to the first 200 characters of the text.
    """
    m = re.search(re.escape(content), texto, re.IGNORECASE)
    if m is None:
        words = [re.escape(w) for w in content.split()]
        m = re.search(r"\s+".join(words), texto, re.IGNORECASE) if words else None
    if m is None:
        return texto.strip()[:200]
    start, end = m.span()
    left = max((texto.rfind(c, 0, start) for c in ".?!"), default=-1) + 1
    probe = max(end, left + 30)
    rights = [i for i in (texto.find(c, probe) for c in ".?!") if i != -1]
    right = min(rights) + 1 if rights else len(texto)
    return texto[left:right].strip()


def parse_extractor_output(
    reply: str, texto: str,
) -> tuple[list[tuple[str, str]], dict[tuple[str, str], str], int]:
    """``(pairs, excerpt_by_pair, descartados)`` — never raises on chatter."""
    haystack = normalize(texto)
    pairs: list[tuple[str, str]] = []
    excerpts: dict[tuple[str, str], str] = {}
    seen: set[tuple[str, str]] = set()
    descartados = 0
    pending: str | None = None
    for line in reply.splitlines():
        if not line.strip():
            continue
        m = _SLUG_LINE.match(line)
        if m:
            if pending is not None:  # a slug with no content line
                descartados += 1
            pending = m.group(1).upper()
            continue
        if pending is None:  # chatter outside a pair
            descartados += 1
            continue
        slug, pending = pending, None
        content = _unwrap(line)
        norm = normalize(content)
        if (
            slug not in CLASSIFIABLE_SLUGS
            or not content
            or len(content) > CONTENT_MAX_CHARS
            or not norm
            or norm not in haystack
        ):
            descartados += 1
            continue
        key = (slug, norm)
        if key in seen:
            continue  # same span twice in one reply: not an error, not a second item
        seen.add(key)
        if len(pairs) >= MAX_PAIRS_PER_POST:
            descartados += 1
            continue
        pairs.append((slug, content))
        excerpts[(slug, content)] = truncate_headline(texto, content)
    if pending is not None:
        descartados += 1
    return pairs, excerpts, descartados
