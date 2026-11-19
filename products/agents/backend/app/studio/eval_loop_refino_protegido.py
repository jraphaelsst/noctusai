"""What the eval-loop refine step may NEVER edit (red-team hardening, owner 2026-11-19): the platform's protective rows.

The refine step proposes an edit of ONE draft row, and the model that proposes it reads failing transcripts written by anyone. A row
that carries the agent's obligations toward the lead (opt-out, hand-off to a person, AI disclosure and privacy, honesty, the platform's
own required texts, the tools that stop or hand off a conversation) is therefore never a target, whatever the model argues:

* sections: the canonical template's must-have sections (``KB § PATTERNS/backend/canonical-agent-template.md``: opt-out, seguranca,
  transferencia, identidade-e-privacidade, honestidade, obrigacoes) matched by KEY PATTERN, plus any section that declares a rule
  (``regras <> '{}'``, ``app.studio.regras_secao``);
* texts: DERIVED from the text registry (``app.studio.textos_registry.TEXTOS``): platform-locked (``fixo_plataforma``) or required
  (``obrigatoria``) outside the compiler's own layout strings; a key the registry does not know is protected (fail closed);
* tools: the hand-off / stop (opt-out) / consent / data-subject / alert tools, by name pattern.

The migration 093 RPC re-checks the SAME patterns in SQL (:data:`PADRAO_SECAO_SQL` / :data:`PADRAO_FERRAMENTA_SQL`, kept equal by a test)
and the registry-derived text list is handed to it by the caller (:func:`protegidas_para_rpc`): the validator and the database never
disagree about what is protected.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from noctusai_lib.primitives.accents import fold_accents_ascii

from app.studio.textos_registry import TEXTOS

__all__ = [
    "PADRAO_SECAO_SQL", "PADRAO_FERRAMENTA_SQL", "secao_protegida", "texto_protegido", "ferramenta_protegida", "linha_e_protegida",
    "textos_protegidos", "protegidas_para_rpc",
]

#: POSIX-ERE-compatible (Python ``re`` and Postgres ``~*`` read it the same way), applied to the accent-folded lower-case key.
PADRAO_SECAO_SQL = "opt[-_]?out|seguranca|transferencia|privacidade|honestidade|identidade|obrigac"  # noc-allow: prompt-text-in-code — a key regex, never read by a model
PADRAO_FERRAMENTA_SQL = "handoff|encerr|titular|consentimento|alerta|opt[-_]?out"

_SECAO = re.compile(PADRAO_SECAO_SQL)
_FERRAMENTA = re.compile(PADRAO_FERRAMENTA_SQL)


def _k(chave: str) -> str:
    return fold_accents_ascii(chave).casefold()


def secao_protegida(chave: str, regras: Iterable[str] = ()) -> bool:
    """A section the refine never edits: a must-have key (pattern) or one that declares platform rules."""
    return bool(tuple(regras)) or _SECAO.search(_k(chave)) is not None


def texto_protegido(chave: str) -> bool:
    """A text row the refine never edits: platform-locked or required by the registry (layout strings of the compiler excepted); an
    unregistered key is protected (fail closed)."""
    spec = TEXTOS.get(chave)
    if spec is None:
        return True
    return spec.fixo_plataforma or (spec.obrigatoria and spec.categoria != "compilador")


def ferramenta_protegida(nome: str) -> bool:
    """A tool row the refine never edits: the hand-off, stop (opt-out), consent, data-subject and alert tools."""
    return _FERRAMENTA.search(_k(nome)) is not None


def linha_e_protegida(tipo: str, chave: str, regras: Iterable[str] = ()) -> bool:
    if tipo == "secao":
        return secao_protegida(chave, regras)
    if tipo == "texto":
        return texto_protegido(chave)
    if tipo == "ferramenta":
        return ferramenta_protegida(chave)
    return True


def textos_protegidos() -> frozenset[str]:
    """Every registry text key the refine may not edit (derived, never hand-kept)."""
    return frozenset(k for k in TEXTOS if texto_protegido(k))


def protegidas_para_rpc() -> list[str]:
    """``['texto:<chave>', ...]``: the registry-derived list the migration 093 RPC refuses on top of its own SQL patterns."""
    return sorted(f"texto:{k}" for k in textos_protegidos())
