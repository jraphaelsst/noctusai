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
from typing import Collection, Iterable, Mapping

__all__ = [
    "ORG_PLACEHOLDER",
    "SPEC_CHAVE_RE",
    "placeholders_org",
    "SPEC_INDISPONIVEL",
    "completar_indisponiveis",
    "PLACEHOLDER_CRU",
    "placeholder_cru_em",
    "placeholders_org_crus",
    "marcador_dado",
    "resolver_texto",
    "conflitos_com_regras_fixas",
]

#: Same pattern as the migration 031 CHECK on ``agent_version_specs.chave`` / ``agent_org_specs.chave``.
SPEC_CHAVE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ORG_PLACEHOLDER = re.compile(r"\{\{\s*org\.([a-z][a-z0-9_]*)\s*\}\}")


#: ANY ``{{ ... }}`` (an org placeholder that never resolved, a typo'd one, a mustache the model invented) or a
#: ``[dado: chave]`` pointer (the compiler's data-fence marker): inert INSIDE the prompt, where the intro text
#: explains it, but never something a lead may read.
PLACEHOLDER_CRU = re.compile(r"\{\{.*?\}\}|\[dado:[^\]]*\]", re.DOTALL)
_ORG_CRU = re.compile(r"\{\{\s*org\.")


def placeholder_cru_em(texto: str | None) -> list[str]:
    """The raw placeholder forms a REPLY carries (``[]`` = clean). The one detector every output surface calls."""
    return [m.group(0)[:60] for m in PLACEHOLDER_CRU.finditer(texto or "")]


def placeholders_org_crus(texto: str | None) -> bool:
    """Does a text bound for a MODEL still carry an unresolved ``{{org.…}}``? (The ``[dado:]`` pointer is
    legitimate there: it is how a free-text spec travels, §E3.)"""
    return bool(_ORG_CRU.search(texto or ""))


#: The typed sentinel a REQUIRED spec with no (valid) value carries in the prompt's data block, in place of the value:
#: ``[dado: chave]`` points at it. A TOKEN, not prose -- what the model does when it reads it is the content's
#: section rule (``dado-indisponivel``), pinned to this literal by a test. Never a raw ``{{org.x}}``, never an empty hole.
SPEC_INDISPONIVEL = "INDISPONIVEL"


def completar_indisponiveis(
    obrigatorias: Iterable[str], valores: Mapping[str, str], fenced: Collection[str],
) -> tuple[dict[str, str], frozenset[str], tuple[str, ...]]:
    """``(valores, fenced, faltando)`` with every required spec that has no value set to :data:`SPEC_INDISPONIVEL` and
    fenced (so it reads ``[dado: chave]`` inline, the sentinel in the data block). ``faltando`` = those keys, sorted
    -- the caller alerts on it. The ONE place the missing-required policy lives (compiler + channel skills)."""
    valores = dict(valores)
    faltando = tuple(sorted(c for c in obrigatorias if not (valores.get(c) or "").strip()))
    for c in faltando:
        valores[c] = SPEC_INDISPONIVEL
    return valores, frozenset(fenced) | frozenset(faltando), faltando


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
