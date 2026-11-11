"""Rules a prompt section DECLARES (``agent_prompt_sections.regras``).

A rule is a behaviour the agent's text carries, named independently of the section key that holds it, so readiness
checks the RULE in the agent's effective sections and a template may put it inside any section (the canonical template
keeps respectful disagreement inside ``honestidade``). The set is closed: a tag nobody checks is noise, and a typo
would silently never match -- an unknown rule is refused.
"""

from __future__ import annotations

from collections.abc import Iterable

#: The agent disagrees respectfully and never agrees to please (the canonical template's must-have).
REGRA_DISCORDAR = "discordar-com-respeito"

REGRAS_SECAO: frozenset[str] = frozenset({REGRA_DISCORDAR})


def validar_regras(regras: Iterable[str]) -> tuple[str, ...]:
    """The rules, de-duplicated in order. Raises ``ValueError`` (a 422 at the routes) naming every unknown rule."""
    vistas: list[str] = []
    for r in regras:
        if r not in vistas:
            vistas.append(r)
    desconhecidas = [r for r in vistas if r not in REGRAS_SECAO]
    if desconhecidas:
        raise ValueError(
            f"Regra de seção desconhecida: {', '.join(desconhecidas)}. "
            f"Regras aceitas: {', '.join(sorted(REGRAS_SECAO))}."
        )
    return tuple(vistas)


def uniao(*grupos: Iterable[str]) -> tuple[str, ...]:
    """Ordered union (a child merged onto a parent section keeps the parent's rules)."""
    out: list[str] = []
    for g in grupos:
        for r in g:
            if r not in out:
                out.append(r)
    return tuple(out)
