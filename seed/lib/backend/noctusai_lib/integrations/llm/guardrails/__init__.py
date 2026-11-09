"""LLM output guardrails -- the product-generic half of the prompt-leak / output-filter layer.

Promoted from agents ``channels/conformidade`` + social-wiring ``scheduling/sanitization`` (``KB § PATTERNS/security/llm-bot-security.md``).
Shape (``KB § PATTERNS/backend/seed-fake-real-adapter.md``): ``OutputGuard`` Protocol + ``FakeOutputGuard`` +
``RealOutputGuard`` + :func:`get_output_guard`. Pure detectors (``detectors``, ``fingerprint``, ``obfuscation``,
``redaction``, ``bounds``) are importable directly. Per-product policy is DATA (``GuardContext`` + ``GuardRule`` params);
tenant knowledge (a persona's canary text, org specs) stays in the product and is passed in.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .bounds import count_words, outside_enum, outside_word_band, unretrieved_sources
from .detectors import (
    CNPJ_PATTERN, CPF_PATTERN, LINK_PATTERN, PIX_PATTERN, contar_padroes, contato_nao_permitido, formato_suspeito, link_nao_permitido, lista_de_spec, padroes_proibidos,
    pii_na_resposta,
)
from .fake_guard import FakeOutputGuard
from .fingerprint import (
    SHINGLE_TOKENS, SHINGLE_TOKENS_DERIVADO, Fingerprint, canario, detectar_vazamento, fingerprint_of,
    mascarar_dados_da_org, sem_falas_de_exemplo, shingles_de,
)
from .obfuscation import caractere_proibido, esqueleto, limpar, tem_caractere_oculto
from .real_guard import RealOutputGuard, worst_of
from .redaction import REDACTION_PATTERNS, count_redactions, redact_payload, redact_pii
from .types import GENERIC_RULES, GuardContext, GuardFinding, GuardRule, OutputGuard

__all__ = [
    "CNPJ_PATTERN", "CPF_PATTERN", "LINK_PATTERN", "PIX_PATTERN", "GENERIC_RULES", "REDACTION_PATTERNS", "SHINGLE_TOKENS", "SHINGLE_TOKENS_DERIVADO", "FakeOutputGuard", "Fingerprint",
    "GuardContext", "GuardFinding", "GuardRule", "OutputGuard", "RealOutputGuard", "canario", "caractere_proibido",
    "contar_padroes", "contato_nao_permitido", "count_redactions", "count_words", "detectar_vazamento", "esqueleto",
    "fingerprint_of", "formato_suspeito", "get_output_guard", "limpar", "link_nao_permitido", "lista_de_spec",
    "mascarar_dados_da_org", "outside_enum", "outside_word_band", "padroes_proibidos", "pii_na_resposta",
    "redact_payload", "redact_pii", "sem_falas_de_exemplo", "shingles_de", "tem_caractere_oculto",
    "unretrieved_sources", "worst_of",
]


def get_output_guard(*, fake_findings: Mapping[str, dict[str, Any]] | None = None) -> OutputGuard:
    """The real guard; a :class:`FakeOutputGuard` scripted with ``fake_findings`` when that is given (tests)."""
    if fake_findings is not None:
        return FakeOutputGuard(fake_findings)
    return RealOutputGuard()
