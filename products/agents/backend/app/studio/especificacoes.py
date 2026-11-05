"""Org specs — the per-org context a platform-defined agent is specified with (Julia v2, Q2).

The DEFINITION of an agent (sections, skills, textos, tool descriptions, decisions) is one for
every org. What differs per org — the agency's name, the regions it serves, price bands, the
listing-link pattern, its knowledge — is DATA the org fills in-app, and the definition refers to
it with a VISIBLE placeholder ``{{org.<chave>}}`` written in the very text the model reads. The
definition version DECLARES each placeholder it uses (``agent_version_specs``: label, help,
type, required); the org supplies the values (``agent_org_specs``). Compiling the definition
FOR an org replaces every placeholder with that org's value — the compiled view per org shows
the text with the values in place, nothing hidden, and the hash covers what the model gets.

Pure functions, no IO.
"""
from __future__ import annotations

import re
from typing import Collection, Mapping

__all__ = [
    "ORG_PLACEHOLDER",
    "SPEC_CHAVE_RE",
    "placeholders_org",
    "marcador_dado",
    "resolver_texto",
    "conflitos_com_regras_fixas",
]

#: Same pattern as the migration 031 CHECK on ``agent_version_specs.chave`` / ``agent_org_specs.chave``.
SPEC_CHAVE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ORG_PLACEHOLDER = re.compile(r"\{\{\s*org\.([a-z][a-z0-9_]*)\s*\}\}")


def placeholders_org(texto: str | None) -> set[str]:
    """The org-spec keys a text refers to."""
    return set(ORG_PLACEHOLDER.findall(texto or ""))


def marcador_dado(chave: str) -> str:
    """What a FREE-TEXT org value looks like inside the definition's text (CONTRACT §E3): a visible, inert pointer."""
    return f"[dado: {chave}]"


def resolver_texto(texto: str, valores: Mapping[str, str], fenced: Collection[str] = ()) -> str:
    """``texto`` with every ``{{org.chave}}`` replaced by ``valores[chave]`` (``""`` when the org
    has no value — whether that is allowed is the declaration's ``obrigatoria``, checked by the
    caller, never papered over here). A key in ``fenced`` (free text, untrusted — §E3) that HAS a value is never
    inlined: it becomes ``[dado: chave]`` and the value travels in the compiler's data section."""
    if not texto or "{{" not in texto:
        return texto

    def sub(m: re.Match[str]) -> str:
        chave = m.group(1)
        valor = valores.get(chave, "")
        return marcador_dado(chave) if valor and chave in fenced else valor

    return ORG_PLACEHOLDER.sub(sub, texto)


#: Deterministic lint of an org's text against the platform-locked rules (AI disclosure, opt-out,
#: escalation to a human, the real-estate-only scope). Detection patterns, not prompt text.
_REGRAS_FIXAS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("divulgacao_ia", re.compile(
        r"((n[aã]o|nunca|jamais)\s+(diga|fale|revele|informe|admita)[^.\n]{0,40}(ia\b|rob[oô]|assistente virtual|artificial)"
        r"|finj[ae]\s+(ser|que)[^.\n]{0,30}(humano|pessoa)|(diga|fale)\s+que\s+(voc[eê]\s+)?[eé]\s+(um\s+)?(humano|pessoa))",
        re.I)),
    ("opt_out", re.compile(
        r"(ignor[ae]|n[aã]o\s+(atenda|respeite|aceite))[^.\n]{0,40}(parar|sair|descadastr|opt-?out|n[aã]o\s+quero)", re.I)),
    ("escalonamento_humano", re.compile(
        r"(nunca|jamais|n[aã]o)\s+(transfira|passe|encaminhe|chame)[^.\n]{0,40}(humano|atendente|corretor|pessoa)", re.I)),
    ("escopo_imobiliario", re.compile(
        r"(responda|atenda|ajude)[^.\n]{0,30}(qualquer|todo)\s+(assunto|pergunta|tema|coisa)", re.I)),
)


def conflitos_com_regras_fixas(valor: str) -> list[str]:
    """Codes of the platform-locked rules ``valor`` tries to override (``[]`` = clean)."""
    return [codigo for codigo, rx in _REGRAS_FIXAS if rx.search(valor or "")]
