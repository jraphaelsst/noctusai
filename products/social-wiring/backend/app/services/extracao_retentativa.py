"""The D3 retry policy for detached document extractions — one definition.

Owner decision D3 (2026-09-22, roadmap `sw-extraction-contract-gate-2026-09`):
"Automatic retry after a failed extraction happens at most 2 times, then the
row stays in `erro` for a human. No long loops."

Every sweep that retries a failed extraction (`matriculas.service`,
`imovel_hub.matricula_extracao_service`, `imovel_hub.documentos_service`'s
structured read) asks THIS module two questions — how many retries, and is
this failure worth one — so the answer cannot drift between surfaces.

WHAT IS NOT RETRIED
-------------------
A failure that a second identical attempt cannot fix: the document itself is
empty/unreadable/too long, or its bytes are gone. Everything else — an
exhausted provider account, a rate limit, a missing/invalid key, a network
blip, an unexpected exception, or an unknown (pre-154, NULL) code — is
retried, because each of those can be fixed OUTSIDE the document (credits
added, key saved) between sweeps. D3's cap is what stops a genuinely stuck
one from looping: after two retries it stays `erro`, visibly, for a human.
"""
from __future__ import annotations

from typing import Optional

#: Automatic retries allowed after the first attempt (D3).
MAX_RETENTATIVAS = 2

#: Total attempts (first + retries) — for surfaces that count attempts.
MAX_TENTATIVAS = 1 + MAX_RETENTATIVAS

#: Machine error codes a retry cannot fix (the seed transcriber's / ladder's
#: codes, plus this product's storage outcomes).
ERROS_PERMANENTES: frozenset[str] = frozenset(
    {
        "no_pages",
        "empty_document",
        "too_many_vision_pages",
        "rasterize_failed",
        "objeto_ausente",
        "tipo_nao_extraivel",
        "documento_removido",
        "documento_nao_encontrado",
        # S2 contract §D.5/H8 — a DPS misfiled under another tipo. A retry
        # reads the exact same sensitive document; the refusal cannot move.
        "documento_sensivel_dps",
        # S2 contract §D.4 — the Quadro Resumo genuinely isn't in the
        # deterministic pass-1(1..4)/pass-2(5..8) window. A retry re-reads
        # the same pages and finds the same nothing.
        "quadro_resumo_nao_encontrado",
    }
)


def codigo_de_erro(texto: Optional[str]) -> Optional[str]:
    """The machine code at the head of a stored `"<code>: <message>"`."""
    if not texto:
        return None
    return texto.split(":", 1)[0].strip() or None


def retentavel(codigo: Optional[str]) -> bool:
    """Is a failure with this code worth an automatic retry? `None`
    (unknown) is — see module docstring."""
    return codigo not in ERROS_PERMANENTES


__all__ = [
    "ERROS_PERMANENTES",
    "MAX_RETENTATIVAS",
    "MAX_TENTATIVAS",
    "codigo_de_erro",
    "retentavel",
]
