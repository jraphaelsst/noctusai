"""The ``trecho`` matcher (CONTRACT §3.4 / risk 3): a recorded criterion value
must be backed by words the lead actually wrote.

Normalised containment — Unicode accents stripped, case folded, punctuation
and whitespace collapsed — across the last N lead messages the caller passes in
(each message alone, plus the messages joined, so an answer split over two
bubbles still matches). Pure.
"""
from __future__ import annotations

from typing import Sequence

#: Longest quote a record stores (matches the column CHECK).
MAX_TRECHO = 160
#: Shortest normalised quote accepted; one character would match almost anything.
MIN_TRECHO = 2
#: Default window of lead messages searched.
ULTIMAS = 8

from noctusai_lib.integrations.llm.guardrails.text import normalizar  # noqa: F401  (one definition, shared by the guardrails)


def conferir_trecho(
    trecho: str | None, mensagens_lead: Sequence[str], *, ultimas: int = ULTIMAS,
) -> tuple[bool, str | None]:
    """``(ok, codigo)``; ``codigo`` is ``trecho_ausente`` / ``trecho_longo`` /
    ``trecho_curto`` / ``trecho_nao_confere`` (codes only, wording lives in DB)."""
    if trecho is None or not str(trecho).strip():
        return False, "trecho_ausente"
    if len(trecho) > MAX_TRECHO:
        return False, "trecho_longo"
    alvo = normalizar(trecho)
    if len(alvo) < MIN_TRECHO:
        return False, "trecho_curto"
    janela = [normalizar(m) for m in list(mensagens_lead)[-max(ultimas, 1):] if isinstance(m, str)]
    janela = [m for m in janela if m]
    candidatos = janela + ([" ".join(janela)] if len(janela) > 1 else [])
    if any(alvo in c for c in candidatos):
        return True, None
    return False, "trecho_nao_confere"
