"""Prompt-leak fingerprint (moved from agents ``channels/conformidade``): a per-org/version canary plus hashed shingles.

Hashes only: a fingerprint detects a leak, it cannot rebuild the prompt. Pure functions; the fingerprint object is
duck-typed (``.shingle_tokens`` + ``.shingles``) so a product keeps its own stored type (agents' ``Impressao``).
"""
from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .text import normalizar

__all__ = [
    "SHINGLE_TOKENS", "SHINGLE_TOKENS_DERIVADO", "Fingerprint", "canario", "detectar_vazamento", "fingerprint_of",
    "mascarar_dados_da_org", "sem_falas_de_exemplo", "shingles_de", "tokens_of",
]

#: Consecutive normalised tokens that make a reply "the prompt".
SHINGLE_TOKENS = 12


def tokens_of(texto: str) -> list[str]:
    return normalizar(texto).split()


def _h(window: Sequence[str]) -> int:
    digest = hashlib.sha256(" ".join(window).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def shingles_de(texto: str, k: int = SHINGLE_TOKENS) -> frozenset[int]:
    toks = tokens_of(texto)
    if len(toks) < k:
        return frozenset()
    return frozenset(_h(toks[i:i + k]) for i in range(len(toks) - k + 1))


def canario(org_id: UUID, version_id: UUID, *, segredo: str = "") -> str:
    """The per-org / per-version canary appended to the system prompt. Deterministic (HMAC over the two
    ids with the platform secret), so nothing is stored; it appears in a reply only if the prompt was
    reproduced. 20 hex chars: not a word, never produced by chance."""
    chave = (segredo or "noctus-canary").encode("utf-8")
    return hmac.new(chave, f"{org_id}:{version_id}".encode("utf-8"), hashlib.sha256).hexdigest()[:20]


#: A quoted span on ONE line ("..." or curly quotes), at most this long. The prompt marks the sentences the agent is MEANT to say
#: to the lead as quoted examples ('diga, por exemplo: "Quem marca a visita e o corretor: vou passar pra ele..."'). The lead is
#: the audience of those lines, so repeating one is not a leak -- and it measurably blocked normal replies (visit flow, the
#: "prefere falar com uma pessoa ou seguir comigo" question, the CPF request), then handed the lead off. The instructions AROUND
#: the quotes stay fingerprinted, and so does the canary: a reply that dumps a section still matches on the unquoted text.
_FALA_ENTRE_ASPAS = re.compile(r'"[^"\n]{1,500}"|\u201c[^\u201d\n]{1,500}\u201d')


def sem_falas_de_exemplo(texto: str) -> str:
    """``texto`` without its quoted example speech (see :data:`_FALA_ENTRE_ASPAS`); a space replaces each span so the tokens
    on its two sides never fuse into one window."""
    return _FALA_ENTRE_ASPAS.sub(" . ", texto)


#: Window of the fingerprint of SKILL text handed to the model in a turn. Longer than the prompt's: a skill teaches example
#: sentences the agent legitimately says ("Pronto, registrei sua preferencia..."), and a 12-token window blocked those replies
#: (measured: ``mec-visita-nao-agenda``). A dump of the procedure still reproduces runs far longer than 24 tokens.
SHINGLE_TOKENS_DERIVADO = 24


_DADO_DA_ORG = "dadodaorg"  # a token that is in no prompt


def mascarar_dados_da_org(resposta: str, valores: Iterable[str]) -> str:
    """``resposta`` (normalised) with every occurrence of an org spec value (opening hours, agency name, regions...) replaced by one
    neutral token. The prompt carries those values as data precisely so the agent can tell the lead: quoting the org's own hours
    is not a prompt leak (measured: it blocked a legitimate 'when do they call back' answer twice and handed the lead off). Done
    on the REPLY, because the fingerprint windows that straddle the data (key name + value) cannot be subtracted afterwards."""
    toks = tokens_of(resposta)
    for v in sorted((x for x in valores if isinstance(x, str)), key=len, reverse=True):
        vt = tokens_of(v)
        if len(vt) < 2:
            continue
        i, out = 0, []
        while i < len(toks):
            if toks[i:i + len(vt)] == vt:
                out.append(_DADO_DA_ORG)
                i += len(vt)
            else:
                out.append(toks[i])
                i += 1
        toks = out
    return " ".join(toks)


def detectar_vazamento(
    resposta: str, *, canario_do_prompt: str | None, impressao: Any | None,
) -> dict[str, Any] | None:
    """The reply reproduces the prompt: the canary appears, or >= ``impressao.shingle_tokens`` consecutive
    tokens match the fingerprint. ``detalhe`` carries the matched-window count only."""
    if not resposta or not resposta.strip():
        return None
    achado: dict[str, Any] = {}
    if canario_do_prompt and canario_do_prompt in resposta:
        achado["canario"] = True
    if impressao is not None and impressao.shingles:
        casados = shingles_de(resposta, impressao.shingle_tokens) & impressao.shingles
        if casados:
            achado["janelas"] = len(casados)
    return achado or None


@dataclass(frozen=True)
class Fingerprint:
    """The hashed shingles of one text at one window length (the product-neutral fingerprint)."""

    shingle_tokens: int
    shingles: frozenset[int]


def fingerprint_of(texto: str, k: int = SHINGLE_TOKENS) -> Fingerprint:
    return Fingerprint(k, shingles_de(texto, k))
