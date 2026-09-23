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
    "LIMITS",
    "OVERRIDE_REASON_MIN_CHARS",
    "PUBLICACAO_LIMIAR_MIN",
    "SEARCH_QUERY_MAX",
    "LIST_QUERY_MAX",
    "RUN_CASE_IDS_MAX",
    "DOCUMENTS_BATCH_MAX",
    "SKILL_FILES_BATCH_MAX",
    "EVAL_RUN_MODEL_ALLOWLIST",
    "EVAL_RUN_BUDGET_USD_MIN",
    "EVAL_RUN_BUDGET_USD_MAX",
    "BUDGET_EXCEEDED_NOTA",
    "override_reason_ok",
]


# ── Size caps (wave-1 security review M3) ───────────────────────────────────
#
# ONE source for the three layers that enforce them: the HTTP schemas
# (``app/schemas/studio*.py`` — 422 at the boundary), the stores (Fake AND
# Real validate before writing — the importer reaches the stores without
# the HTTP schemas), and the ``CHECK (length(...) <= N)`` constraints of
# migrations 012/013 (the backstop). Collection metadata and the client
# brain are LIVE prompt inputs (compiled into every turn, never frozen by a
# published version, never behind the eval gate) — so they are capped
# tightest.

LIMITS: dict[str, int] = {
    "collection.nome": 120,
    "collection.tag": 12,
    "collection.descricao": 600,
    "client.resumo": 8_000,
    "entry.titulo": 200,
    "entry.conteudo": 4_000,
    "client.active_entries": 200,
    "section.conteudo": 40_000,
    "skill.corpo": 60_000,
    "skill_file.conteudo": 120_000,
    "document.conteudo": 2_000_000,
}

#: L1 — an override reason needs this many NON-whitespace characters.
OVERRIDE_REASON_MIN_CHARS = 20
#: H2 — DB CHECK floor on ``agents.publicacao_limiar`` (a threshold of 0.1
#: would make the gate decorative).
PUBLICACAO_LIMIAR_MIN = 0.5
#: L5 — ``q`` cap of the ranked knowledge search (router + SQL function).
SEARCH_QUERY_MAX = 512
#: L4 — ``q`` cap of the document list filter (router + SQL function).
LIST_QUERY_MAX = 200
#: L6 — an explicit eval-run case list is deduped and capped at this size.
RUN_CASE_IDS_MAX = 200
#: UI-KB-BACKEND batch endpoints — bulk knowledge ingest for the Studio UI
#: (382-document / 12-skill corpora can't go through one-document-per-call).
#: `documents:batch` items per call (each still capped at
#: `document.conteudo`, §H4 body-size override below).
DOCUMENTS_BATCH_MAX = 100
#: `skills/{id}/files:batch` items per call (each capped at
#: `skill_file.conteudo`).
SKILL_FILES_BATCH_MAX = 50

# ── Cost control (contract §L) ──────────────────────────────────────────────

#: The cheaper-iteration model override an eval run may request instead of
#: the version's own model (contract §L). Deliberately NARROWER than
#: `agents.agent_versions.model`'s allowlist (012, widened by 015 to add
#: `claude-haiku-4-5` alongside `claude-opus-5`/`claude-sonnet-5`) — this
#: exists to let an iteration run cost LESS than the version's own model,
#: never more, so it stays the two cheapest models even after 015. Mirrored
#: by the migration 014 CHECK (`eval_runs_modelo_geracao_check`) — this
#: tuple is the single source the HTTP schema and the store both validate
#: against.
EVAL_RUN_MODEL_ALLOWLIST: tuple[str, ...] = ("claude-sonnet-5", "claude-haiku-4-5")
#: Migration 014 CHECK floor/ceiling on `eval_runs.limite_usd`.
EVAL_RUN_BUDGET_USD_MIN = 0.0
EVAL_RUN_BUDGET_USD_MAX = 50.0
#: `eval_results.notas_juiz` for a case the runner never started because the
#: run's cumulative `custo_usd` had already reached `limite_usd` (contract
#: §L). A fixed string — never composed from the limit's exact value — so a
#: `LIKE`/equality check in a test or the UI stays stable across limits.
BUDGET_EXCEEDED_NOTA = "limite de custo atingido"


def override_reason_ok(reason: str | None) -> bool:
    """``True`` iff ``reason`` carries at least
    :data:`OVERRIDE_REASON_MIN_CHARS` non-whitespace characters (L1)."""
    if reason is None:
        return False
    return sum(1 for ch in reason if not ch.isspace()) >= OVERRIDE_REASON_MIN_CHARS


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
    #: Additive (H1): ``True`` only for a run over EVERY active case at run
    #: time (``case_ids`` omitted). A subset run never satisfies the gate.
    #: Defaults to ``False`` — fail closed for any constructor that predates it.
    completa: bool = False
    #: Additive (H1): number of cases the run covered; the gate needs >= 1.
    total: int = 0


class EvalGate(Protocol):
    def latest_concluded_run(self, org_id: UUID, version_id: UUID) -> GateRun | None:
        """The newest ``concluida`` run of the version that is ``completa``
        (H1 — a later subset run must never hide the complete one)."""
        ...


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
