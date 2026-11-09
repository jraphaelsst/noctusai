"""Agent LAYERS — BASE → SDR → agent (owner rules 2026-11-09, roadmap ``agent-templates-2026-11``).

A child agent's version holds only ITS OWN rows. What the compiler, the runtime turn, the eval driver and readiness
read are the EFFECTIVE rows: the parent chain's rows merged with the child's, per piece, by key:

* prose **section** (``chave``) with the same key in parent and child -> the child APPENDS: the parent's text stays
  (with the parent's title, order and active flag) and the child's text follows it after a blank line;
* **single-value** pieces -- text (``chave``), tool row (``ferramenta``), decision (``chave``), org-spec declaration
  (``chave``), own skill (``nome``) -- the child REPLACES the parent's and the replacement is reported as an
  override (:func:`sobreposicoes`).

Editors keep reading OWN rows (the raw store): a child's editor never writes a parent's piece. Two views, one rule:
:class:`EfetivoStore` overrides ONLY the row listings and delegates everything else to the wrapped store.

Pure merges (no IO); the parent of a version comes from an injected ``resolver_pai`` so the merge is testable
without a database. A cycle in the chain is refused (``CadeiaInvalida``), never silently cut.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, TypeVar
from uuid import UUID

__all__ = [
    "CadeiaInvalida",
    "EfetivoStore",
    "Sobreposicao",
    "SEPARADOR_APENSO",
    "apensar_secoes",
    "substituir_por_chave",
    "sobreposicoes",
]

#: What joins a parent section's text and the child's appended text.
SEPARADOR_APENSO = "\n\n"
#: Deepest chain allowed (BASE -> SDR -> agent is 3; one spare level for a market layer).
PROFUNDIDADE_MAXIMA = 4

T = TypeVar("T")


class CadeiaInvalida(ValueError):
    """The parent chain loops or is deeper than :data:`PROFUNDIDADE_MAXIMA`."""


@dataclass(frozen=True)
class Sobreposicao:
    """A child piece that changes a parent piece with the same key."""

    tipo: str  # secao | texto | ferramenta | decisao | spec | skill
    chave: str
    modo: str  # apenso (prose append) | substituicao (single value replaced)


def apensar_secoes(pai: Sequence[T], filho: Sequence[T]) -> list[T]:
    """Sections by ``chave``: union; same key -> the parent's row with the child's text appended."""
    filho_por_chave = {s.chave: s for s in filho}
    out: list[T] = []
    for p in pai:
        f = filho_por_chave.pop(p.chave, None)
        if f is None or not f.ativo or not f.conteudo.strip():
            out.append(p)
            continue
        base = p.conteudo.rstrip()
        out.append(replace(p, conteudo=(base + SEPARADOR_APENSO + f.conteudo.strip()) if base else f.conteudo.strip()))
    out.extend(filho_por_chave.values())  # the child's own new sections keep their position in its order
    return out


def substituir_por_chave(pai: Sequence[T], filho: Sequence[T], chave: Callable[[T], str]) -> list[T]:
    """Single-value pieces: union; same key -> the child's row replaces the parent's."""
    filho_chaves = {chave(f) for f in filho}
    return [p for p in pai if chave(p) not in filho_chaves] + list(filho)


def sobreposicoes(tipo: str, pai: Iterable[Any], filho: Iterable[Any], chave: Callable[[Any], str]) -> list[Sobreposicao]:
    """Every child piece whose key also exists in the parent (the editor lists them)."""
    pai_chaves = {chave(p) for p in pai}
    modo = "apenso" if tipo == "secao" else "substituicao"
    return [Sobreposicao(tipo, chave(f), modo) for f in filho if chave(f) in pai_chaves]


_CHAVES: dict[str, Callable[[Any], str]] = {
    "textos": lambda r: r.chave,
    "ferramentas": lambda r: r.ferramenta,
    "decisoes": lambda r: r.chave,
    "spec_defs": lambda r: r.chave,
    "skills": lambda r: r.nome,
}


class EfetivoStore:
    """The studio store as the compiler / runtime see a version: parent chain merged in.

    ``resolver_pai(org_id, version_id) -> (org_id, version_id) | None`` names the version whose rows a version
    inherits (a child draft: its parent's draft; a published child: its pinned parent version)."""

    def __init__(self, store: Any, resolver_pai: Callable[[UUID, UUID], "tuple[UUID, UUID] | None"]) -> None:
        self._store = store
        self._resolver_pai = resolver_pai

    def __getattr__(self, nome: str) -> Any:  # everything that is not a row listing is the store's own
        return getattr(self._store, nome)

    def _pai(self, org_id: UUID, version_id: UUID, vistos: frozenset[UUID]) -> "tuple[UUID, UUID] | None":
        pai = self._resolver_pai(org_id, version_id)
        if pai is None:
            return None
        if pai[1] in vistos or pai[1] == version_id:
            raise CadeiaInvalida(f"a cadeia de camadas da versão {version_id} volta para {pai[1]}")
        if len(vistos) + 1 >= PROFUNDIDADE_MAXIMA:
            raise CadeiaInvalida(f"a cadeia de camadas da versão {version_id} passa de {PROFUNDIDADE_MAXIMA} níveis")
        return pai

    def _efetivas(self, metodo: str, org_id: UUID, version_id: UUID, vistos: frozenset[UUID] = frozenset()) -> list:
        proprias = list(getattr(self._store, metodo)(org_id, version_id))
        pai = self._pai(org_id, version_id, vistos)
        if pai is None:
            return proprias
        do_pai = self._efetivas(metodo, pai[0], pai[1], vistos | {version_id})
        if metodo == "list_sections":
            return apensar_secoes(do_pai, proprias)
        return substituir_por_chave(do_pai, proprias, _CHAVES[metodo.removeprefix("list_")])

    def list_sections(self, org_id: UUID, version_id: UUID) -> list:
        return self._efetivas("list_sections", org_id, version_id)

    def list_textos(self, org_id: UUID, version_id: UUID) -> list:
        return self._efetivas("list_textos", org_id, version_id)

    def list_ferramentas(self, org_id: UUID, version_id: UUID) -> list:
        return self._efetivas("list_ferramentas", org_id, version_id)

    def list_decisoes(self, org_id: UUID, version_id: UUID) -> list:
        return self._efetivas("list_decisoes", org_id, version_id)

    def list_spec_defs(self, org_id: UUID, version_id: UUID) -> list:
        return self._efetivas("list_spec_defs", org_id, version_id)

    def list_skills(self, org_id: UUID, version_id: UUID) -> list:
        return self._efetivas("list_skills", org_id, version_id)

    def list_version_skill_files(self, org_id: UUID, version_id: UUID, vistos: frozenset[UUID] = frozenset()) -> list:
        """Files follow their skill: a parent skill the child replaced brings none of its files."""
        proprios = list(self._store.list_version_skill_files(org_id, version_id))
        pai = self._pai(org_id, version_id, vistos)
        if pai is None:
            return proprios
        substituidas = {s.nome for s in self._store.list_skills(org_id, version_id)}
        ids_pai_mantidos = {s.id for s in self.list_skills(pai[0], pai[1]) if s.nome not in substituidas}
        do_pai = self.list_version_skill_files(pai[0], pai[1], vistos | {version_id})
        return [f for f in do_pai if f.skill_id in ids_pai_mantidos] + proprios
