"""Agent Studio value types + cross-slice seams (contract §C, §J2).

Pure data: no IO, no store imports. The compiler consumes the ``*Bundle`` /
``CollectionSummary`` types; the routers build them from the store.

Seams (§J2 — pinned so wave-1 slices never import each other's code):

* ``EvalGate`` / ``GateRun`` / ``FakeEvalGate`` — §J2.1, verbatim. BE-KE's
  ``SupabaseEvalGate`` satisfies the Protocol; BE-RT binds it.
* ``KnowledgeCatalog`` / ``FakeKnowledgeCatalog`` — the knowledge summary the
  compiler needs (§C ``CompileInput.knowledge``). Knowledge is BE-KE's
  (013 tables); this Protocol is the same shape of seam as ``EvalGate`` so
  the compile/publish routes never import BE-KE's store. BE-RT binds it to
  BE-KE's store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

__all__ = [
    "SectionData",
    "SkillFileRef",
    "SkillData",
    "VersionBundle",
    "CollectionSummary",
    "ClientEntryData",
    "ClientBundle",
    "CompileInput",
    "ManifestOrigin",
    "ManifestSection",
    "OnDemandItem",
    "CompileWarning",
    "CompiledPrompt",
    "GateRun",
    "EvalGate",
    "FakeEvalGate",
    "KnowledgeCatalog",
    "FakeKnowledgeCatalog",
]


# ── Compiler input ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SectionData:
    id: UUID | None
    chave: str
    titulo: str
    ordem: int
    conteudo: str
    ativo: bool = True


@dataclass(frozen=True)
class SkillFileRef:
    """A skill's attached file — metadata only (the text is on-demand)."""

    caminho: str
    titulo: str | None
    chars: int


@dataclass(frozen=True)
class SkillData:
    id: UUID | None
    nome: str
    descricao: str
    corpo: str
    ordem: int = 0
    ativo: bool = True
    arquivos: tuple[SkillFileRef, ...] = ()


@dataclass(frozen=True)
class VersionBundle:
    """Settings + sections + skills of one version. The compiler filters
    ``ativo`` and orders itself, so a bundle may carry inactive rows."""

    model: str
    effort: str
    max_turns: int
    idioma: str
    tool_policy: dict[str, Any]
    secoes: tuple[SectionData, ...] = ()
    skills: tuple[SkillData, ...] = ()
    version_id: UUID | None = None
    versao: int | None = None


@dataclass(frozen=True)
class CollectionSummary:
    slug: str
    nome: str
    tag: str | None
    descricao: str
    doc_count: int
    #: Additive to §C's summary (default 0): the collection's display order,
    #: so the compiled list follows the UI order deterministically
    #: (sorted by ``(ordem, slug)`` — never by provider row order).
    ordem: int = 0


@dataclass(frozen=True)
class ClientEntryData:
    tipo: str
    titulo: str
    conteudo: str
    status: str = "ativo"


@dataclass(frozen=True)
class ClientBundle:
    nome: str
    resumo: str
    entradas: tuple[ClientEntryData, ...] = ()
    id: UUID | None = None


@dataclass(frozen=True)
class CompileInput:
    agent_nome: str
    version: VersionBundle
    knowledge: tuple[CollectionSummary, ...]
    client: ClientBundle | None
    tool_policy: dict[str, Any]


# ── Compiler output ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ManifestOrigin:
    tipo: str  # "secao" | "auto"
    id: UUID | None
    campo: str | None


@dataclass(frozen=True)
class ManifestSection:
    chave: str
    titulo: str
    origem: ManifestOrigin
    inicio: int
    fim: int
    chars: int
    tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "chave": self.chave,
            "titulo": self.titulo,
            "origem": {
                "tipo": self.origem.tipo,
                "id": str(self.origem.id) if self.origem.id is not None else None,
                "campo": self.origem.campo,
            },
            "inicio": self.inicio,
            "fim": self.fim,
            "chars": self.chars,
            "tokens": self.tokens,
        }


@dataclass(frozen=True)
class OnDemandItem:
    tipo: str  # "skill" | "arquivo_skill" | "colecao"
    nome: str
    caminho: str | None
    chars: int
    tokens: int
    gatilho: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "nome": self.nome,
            "caminho": self.caminho,
            "chars": self.chars,
            "tokens": self.tokens,
            "gatilho": self.gatilho,
        }


@dataclass(frozen=True)
class CompileWarning:
    codigo: str
    mensagem: str
    bloqueante: bool

    def to_dict(self) -> dict[str, Any]:
        return {"codigo": self.codigo, "mensagem": self.mensagem, "bloqueante": self.bloqueante}


@dataclass(frozen=True)
class CompiledPrompt:
    texto: str
    hash: str
    manifest: list[ManifestSection]
    tokens_estimados: int
    sob_demanda: list[OnDemandItem]
    #: Additive to §C's dataclass: the compile warnings the endpoint returns
    #: and publish blocks on (§C "Compile warnings").
    avisos: list[CompileWarning] = field(default_factory=list)

    @property
    def bloqueado(self) -> bool:
        return any(w.bloqueante for w in self.avisos)

    def manifest_json(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.manifest]


# ── §J2.1 Eval gate seam ────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateRun:
    id: UUID
    score: float | None
    limiar: float
    compiled_hash: str
    status: str


class EvalGate(Protocol):
    def latest_concluded_run(self, org_id: UUID, version_id: UUID) -> GateRun | None: ...


class FakeEvalGate:
    """In-memory :class:`EvalGate`; tests set runs with :meth:`set_run`."""

    def __init__(self) -> None:
        self._runs: dict[tuple[UUID, UUID], GateRun] = {}

    def set_run(self, org_id: UUID, version_id: UUID, run: GateRun | None) -> None:
        if run is None:
            self._runs.pop((org_id, version_id), None)
        else:
            self._runs[(org_id, version_id)] = run

    def latest_concluded_run(self, org_id: UUID, version_id: UUID) -> GateRun | None:
        return self._runs.get((org_id, version_id))


# ── Knowledge catalog seam (compile input from BE-KE's tables) ──────────────


class KnowledgeCatalog(Protocol):
    def collection_summaries(self, org_id: UUID, agent_id: UUID) -> list[CollectionSummary]:
        """Every collection of the agent with its ACTIVE document count."""
        ...


class FakeKnowledgeCatalog:
    """In-memory :class:`KnowledgeCatalog`; tests set summaries with :meth:`set`."""

    def __init__(self) -> None:
        self._by_agent: dict[tuple[UUID, UUID], list[CollectionSummary]] = {}

    def set(self, org_id: UUID, agent_id: UUID, summaries: list[CollectionSummary]) -> None:
        self._by_agent[(org_id, agent_id)] = list(summaries)

    def collection_summaries(self, org_id: UUID, agent_id: UUID) -> list[CollectionSummary]:
        return list(self._by_agent.get((org_id, agent_id), []))
